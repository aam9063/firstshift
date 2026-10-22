"""Persisted dispatch for the simulator (F07, T2): the sim side of the same
path the HireDesk webhook and the scripted wrapper (app/services/scripted.py)
use.

One transaction per event:
- an inbound message is appended as a message.in event first (the
  conversation, not just the outcome, is observable; rule 7),
- the pure StateMachine.dispatch result becomes AuditEvent rows (INV-5),
  envelope events and OutboxMessage rows, exactly like the webhook handler,
- Application and Candidate state move forward together (mirror rule),
- the run's serialized snapshot is refreshed so the next request continues
  from this exact point (fired timers, guard facts, counters).

Differences from app/services/scripted.py, forced by the request-scoped API:
the snapshot comes from the run row (not from an in-memory journey) and the
message.in payload carries the simulated message text. Outbox kinds beyond
the scripted set (backup.activate, D4's bench backup activation) are
delivered as manager channel messages. A rejected dispatch raises
SimDispatchRejected after the transaction rolled back; the runner keeps the
attempt observable by recording the message.in standalone.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.core.state_machine import (
    Actor,
    DispatchResult,
    State,
    StateMachine,
)
from app.core.state_machine import (
    Application as CoreApplication,
)
from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import Application, AuditEvent, Candidate, OutboxMessage, Restaurant
from app.ports.hiredesk import StageUpdate
from app.ports.messaging import OutboundMessage
from app.services.scripted import _SCRIPTED_BODIES as SCRIPTED_BODIES
from app.services.scripted import (
    INTERNAL_FALLBACK_BODY,
    _event_type_or_none,
    is_internal_recipient,
)
from app.sim.store import RunRef, SimRun, snapshot_from_json, snapshot_to_json

NOTICE_VERSION = "v1"

# Channel-delivered outbox kinds: confirmed in-process through the simulator
# adapter, like the webhook's first message. Everything else is an async
# port write left pending for the relay worker.
CHANNEL_KINDS = frozenset(
    {"whatsapp.out", "trainer.notify", "bench.reserve_backup", "backup.activate"}
)

# Scripted bodies for templates the skeleton wrapper does not cover (D4/D5/D6
# flows). Spanish, one action per message.
SIM_BODIES = {
    "decision_reminder": "Recordatorio: tienes una decisión pendiente sobre un candidato.",
    "decision_escalation": (
        "Escalación: la decisión sobre el candidato supera las 8 h de SLA. "
        "Revisa y responde."
    ),
    "no_show": "El candidato no se presentó. Revisa el estado del backup.",
    "interview_reoffer": "El candidato no asistió a la entrevista. Propón otra cita.",
    "backup_activate": (
        "Backup activado desde la bolsa de empleo para el primer turno; el "
        "candidato original sigue convocado."
    ),
}

BUTTON_LABELS = {"approve": "Aprobar", "decline": "No seguir"}

LOGGER = logging.getLogger(__name__)


class SimDispatchRejected(RuntimeError):
    """The core rejected the dispatch: no transition, nothing persisted."""


def dispatch_and_persist(
    engine: Any,
    run: RunRef,
    *,
    event: str,
    actor: Actor,
    now: datetime,
    payload: dict[str, Any] | None = None,
    snapshot_updates: dict[str, Any] | None = None,
    snapshot: CoreApplication | None = None,
    inbound: dict[str, Any] | None = None,
) -> DispatchResult:
    """Dispatch one event and persist every effect in one transaction."""
    with Session(engine) as session, session.begin():
        application = session.scalars(
            select(Application).where(Application.id == run.application_id)
        ).one()
        candidate = session.get(Candidate, run.candidate_id)
        assert candidate is not None, f"candidate vanished: {run.candidate_id}"

        if snapshot is None:
            snapshot = _current_snapshot(run, application)
        if snapshot_updates:
            snapshot = _apply_updates(snapshot, snapshot_updates)

        result = StateMachine().dispatch(
            snapshot, event, actor, now=now, payload=payload or {}
        )
        if not result.transitioned or result.to_state is None:
            raise SimDispatchRejected(
                f"event '{event}' rejected in state '{snapshot.state.value}': "
                f"{result.rejection_reason}"
            )

        # The inbound message precedes the transition it caused.
        if inbound is not None:
            append_event(
                session,
                EventEnvelope(
                    type=EventType.MESSAGE_IN,
                    candidate_id=candidate.id,
                    trace_id=run.trace_id,
                    occurred_at=now,
                    payload={
                        "channel": "simulator",
                        **inbound,
                        "event": event,
                    },
                ),
            )

        restaurant_code = session.scalar(
            select(Restaurant.code).where(Restaurant.id == application.restaurant_id)
        )
        assert restaurant_code is not None, "application without restaurant scope"

        _persist_audit(session, application, candidate, result, now)
        _persist_outbox_and_events(
            session, application, candidate, result, run, restaurant_code, now
        )

        application.state = result.to_state.value
        application.state_changed_at = now
        candidate.state = result.to_state.value  # mirrored from Application

        sim_row = session.get(SimRun, run.id)
        assert sim_row is not None, f"scenario run vanished: {run.id}"
        sim_row.snapshot = snapshot_to_json(result.application)
    return result


def record_chat_message(
    engine: Any, run: RunRef, *, actor: Actor, text: str, now: datetime, note: str | None = None
) -> None:
    """Persist a conversation-only inbound message (no core event)."""
    with Session(engine) as session, session.begin():
        payload: dict[str, Any] = {
            "channel": "simulator",
            "role": actor.kind.value,
            "actor_name": actor.name,
            "text": text,
        }
        if note is not None:
            payload["note"] = note
        append_event(
            session,
            EventEnvelope(
                type=EventType.MESSAGE_IN,
                candidate_id=run.candidate_id,
                trace_id=run.trace_id,
                occurred_at=now,
                payload=payload,
            ),
        )


# ------------------------------------------------------------- internals


def _current_snapshot(run: RunRef, application: Application) -> CoreApplication:
    if run.snapshot_json is not None:
        return snapshot_from_json(run.snapshot_json)
    return CoreApplication(
        application_id=str(application.id),
        state=State(application.state),
        notice_version=NOTICE_VERSION,
    )


def _apply_updates(
    snapshot: CoreApplication, updates: dict[str, Any]
) -> CoreApplication:
    """Apply validated snapshot updates (unknown fields fail loudly)."""
    from dataclasses import fields as dc_fields
    from dataclasses import replace as dc_replace

    valid = {f.name for f in dc_fields(CoreApplication)}
    unknown = set(updates) - valid
    if unknown:
        raise SimDispatchRejected(f"unknown snapshot fields: {sorted(unknown)}")
    return dc_replace(snapshot, **updates)


def _persist_audit(
    session: Session,
    application: Application,
    candidate: Candidate,
    result: DispatchResult,
    now: datetime,
) -> None:
    folded = [event for event in result.events if _event_type_or_none(event.type) is None]
    for entry in result.audit_entries:
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=entry.at or now,
                actor_type=entry.actor_kind,
                actor_id=entry.actor_name or "firstshift",
                application_id=application.id,
                candidate_id=candidate.id,
                event_type=entry.event,
                state_from=entry.from_state,
                state_to=entry.to_state,
                payload={
                    "details": entry.details,
                    "folded_events": [
                        {"type": event.type, "payload": event.payload} for event in folded
                    ],
                },
            )
        )


def _persist_outbox_and_events(
    session: Session,
    application: Application,
    candidate: Candidate,
    result: DispatchResult,
    run: RunRef,
    restaurant_code: str,
    now: datetime,
) -> None:
    outbounds: dict[str, _PendingOutbound] = {}
    for core_message in result.outbox_messages:
        kind = core_message.kind
        row_id = uuid4()
        if kind in CHANNEL_KINDS:
            outbound = _channel_message(kind, core_message.payload, candidate, run)
            if outbound is None:
                # The body guard suppressed a candidate-facing send without
                # configured copy; the warning log keeps the suppression
                # observable (rule 7).
                continue
            outbounds.setdefault(outbound.template, outbound)
            simulator_channel.send_message(outbound.message)
            session.add(
                OutboxMessage(
                    id=row_id,
                    port="whatsapp",
                    operation="send",
                    payload={
                        "recipient_ref": outbound.message.recipient_ref,
                        "body": outbound.message.body,
                        "quick_replies": outbound.message.quick_replies,
                        "correlation_id": outbound.message.correlation_id,
                        "template": outbound.template,
                    },
                    idempotency_key=(
                        f"fs/whatsapp/send/{restaurant_code}/{application.id}/{row_id}"
                    ),
                    status="api_confirmed",
                    related_entity_id=candidate.id,
                )
            )
        elif kind == "hiredesk.stage_update":
            assert application.hiredesk_application_id is not None
            stage = StageUpdate.model_validate(
                {
                    "hiredesk_application_id": application.hiredesk_application_id,
                    "stage": core_message.payload["stage"],
                    "rejection_reason": None,
                    "decision_id": str(uuid4()),
                }
            )
            session.add(
                OutboxMessage(
                    id=row_id,
                    port="hiredesk",
                    operation="update_stage",
                    payload=stage.model_dump(),
                    idempotency_key=(
                        f"fs/hiredesk/update_stage/{restaurant_code}"
                        f"/{stage.hiredesk_application_id}/{row_id}"
                    ),
                    status="pending",
                    related_entity_id=candidate.id,
                )
            )
        elif kind == "shiftgrid.write":
            session.add(
                OutboxMessage(
                    id=row_id,
                    port="shiftgrid",
                    operation="assign_shift",
                    payload=dict(core_message.payload),
                    idempotency_key=(
                        f"fs/shiftgrid/assign_shift/{restaurant_code}"
                        f"/{application.id}/{row_id}"
                    ),
                    status="pending",
                    related_entity_id=candidate.id,
                )
            )
        else:
            # Fail loudly rather than silently dropping a write (rule 4).
            raise SimDispatchRejected(f"unmapped outbox kind: {kind}")

    # Stream position ordering: result envelopes share the dispatch ``now``,
    # so each gets a deterministic microsecond increment after the inbound
    # message (occurred_at = now). The event payloads keep the true ``at``.
    emitted_out_templates = {
        str(event.payload.get("template", ""))
        for event in result.events
        if event.type == EventType.MESSAGE_OUT.value
    }
    appended = 0
    for index, core_event in enumerate(result.events):
        event_type = _event_type_or_none(core_event.type)
        if event_type is None:
            continue  # folded into the audit payload by _persist_audit
        payload = dict(core_event.payload)
        if event_type is EventType.MESSAGE_OUT:
            matched = outbounds.get(str(payload.get("template", "")))
            if matched is not None:
                payload.update(
                    {
                        "recipient_ref": matched.message.recipient_ref,
                        "body": matched.message.body,
                        "correlation_id": matched.message.correlation_id,
                    }
                )
        append_event(
            session,
            EventEnvelope(
                type=event_type,
                candidate_id=candidate.id,
                trace_id=run.trace_id,
                occurred_at=now + timedelta(microseconds=index + 1),
                payload=payload,
            ),
        )
        appended += 1

    # Channel messages the core did not announce as message.out (for example
    # activate_backup, D4) still appear in the transcript: one message.out
    # envelope per unannounced outbound.
    for template, outbound in outbounds.items():
        if template in emitted_out_templates:
            continue
        append_event(
            session,
            EventEnvelope(
                type=EventType.MESSAGE_OUT,
                candidate_id=candidate.id,
                trace_id=run.trace_id,
                occurred_at=now + timedelta(microseconds=len(result.events) + appended + 1),
                payload={
                    "template": template,
                    "recipient_ref": outbound.message.recipient_ref,
                    "body": outbound.message.body,
                    "correlation_id": outbound.message.correlation_id,
                },
            ),
        )
        appended += 1


class _PendingOutbound:
    """A channel message built from one core outbox effect."""

    def __init__(self, message: OutboundMessage, template: str) -> None:
        self.message = message
        self.template = template


def _channel_message(
    kind: str, core_payload: dict[str, Any], candidate: Candidate, run: RunRef
) -> _PendingOutbound | None:
    template = str(core_payload.get("template") or kind)
    to = core_payload.get("to")
    if kind == "trainer.notify":
        recipient_ref = "trainer-sim"
    elif kind == "bench.reserve_backup":
        recipient_ref = "bench-backup-sim"
    elif kind == "backup.activate":
        # D4: the bench backup activation informs the manager, who owns the
        # first shift; the candidate stays convoked (T4, H4).
        recipient_ref = "manager-sim"
    elif to == "manager":
        recipient_ref = "manager-sim"
    elif to == "area_hrbp":
        recipient_ref = "hrbp-sim"
    else:
        recipient_ref = candidate.phone

    body = (
        SIM_BODIES.get(template)
        or SIM_BODIES.get(template.replace(".", "_"))
        or SCRIPTED_BODIES.get(template)
    )
    if body is None:
        if is_internal_recipient(kind, recipient_ref):
            # Internal recipients keep receiving a message, but with the
            # safe internal body, never the raw outbox kind (F09 T2).
            body = INTERNAL_FALLBACK_BODY
        else:
            # Never a candidate-facing fallback identifier: the kind stays
            # observable through the warning log only (rule 7).
            LOGGER.warning(
                "suppressed candidate-facing outbound without configured copy: "
                "kind=%s template=%s candidate=%s trace=%s",
                kind,
                template,
                candidate.id,
                run.trace_id,
            )
            return None
    buttons = core_payload.get("buttons")
    if isinstance(buttons, list) and buttons:
        quick_replies = [BUTTON_LABELS.get(str(b), str(b)) for b in buttons]
    elif template == "first_message":
        quick_replies = ["Sí", "No"]
    else:
        quick_replies = []
    return _PendingOutbound(
        message=OutboundMessage(
            recipient_ref=recipient_ref,
            body=body,
            correlation_id=run.trace_id,
            quick_replies=quick_replies,
        ),
        template=template,
    )
