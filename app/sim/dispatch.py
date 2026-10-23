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
from app.core.inbound import classify_inbound, flags_third_party_documents
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
    CANDIDATE_FACING_TEMPLATES,
    INTERNAL_FALLBACK_BODY,
    _event_type_or_none,
    candidate_body,
    candidate_language,
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
            snapshot, event, actor, now=now, payload=_tracker_payload(
                event, application, payload
            )
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
    """Persist a conversation-only inbound message (no core event).

    A candidate message is classified first, deterministically and without
    any model call (G5 and the third-party document guard, F11 T4/S4,
    app/core/inbound.py):

    - an abusive or distressed classification appends a typed
      ESCALATION_CREATED event and an ``inbound_escalation_created`` audit
      row carrying the classification, and sends the canned kind reply from
      the versioned message catalog (template ``escalation``); it never
      rejects autonomously and never calls a tool,
    - a third-party document claim flags the record for human review
      (``documents_flagged_for_review`` audit row plus the
      ``document_review_required`` column) and sends the canned catalog
      notification; the row-21 tracker guard holds until People Ops clears
      the review (clear_document_review).

    The message.in row always lands first (rule 7); the escalation artifacts
    follow at +1us and +2us so the stream order stays coherent.
    """
    is_candidate = actor.kind.value == "candidate"
    classification = classify_inbound(text) if is_candidate else None
    third_party_documents = flags_third_party_documents(text) if is_candidate else False
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
        if classification is None and not third_party_documents:
            return
        candidate = session.get(Candidate, run.candidate_id)
        assert candidate is not None, f"candidate vanished: {run.candidate_id}"
        if classification is not None:
            _record_inbound_escalation(session, run, candidate, classification, actor, now)
        if third_party_documents:
            _flag_documents_for_review(session, run, candidate, now)


def clear_document_review(
    engine: Any, application_id: Any, *, cleared_by: str, at: datetime
) -> None:
    """People Ops clearance (F11 T4/S4): a named human records that the
    flagged document submission was reviewed, releasing the row-21 tracker
    hold. The clearance is the only way ``document_review_required`` stops
    blocking tracker_completed."""
    if not cleared_by or not cleared_by.strip():
        raise ValueError("a named People Ops reviewer is required")
    with Session(engine) as session, session.begin():
        application = session.get(Application, application_id)
        assert application is not None, f"application vanished: {application_id}"
        if not application.document_review_required:
            raise ValueError("the application has no document review to clear")
        application.document_review_cleared_at = at
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=at,
                actor_type="system",
                actor_id=cleared_by.strip(),
                application_id=application.id,
                candidate_id=None,
                event_type="document_review_cleared",
                state_from=None,
                state_to=None,
                payload={
                    "cleared_by": cleared_by.strip(),
                    "details": "People Ops reviewed the flagged document submission",
                },
            )
        )


# ------------------------------------------------------------- internals


def _tracker_payload(
    event: str, application: Application, payload: dict[str, Any] | None
) -> dict[str, Any]:
    """Dispatch payload for one event, with the row-21 tracker hold flag
    injected when a third-party document review is outstanding (F11 T4/S4).
    The core guard (documents_and_csv_confirmed) reads these flags; the
    caller's payload is never mutated."""
    dispatch_payload = dict(payload or {})
    if event == "tracker_completed" and application.document_review_required:
        dispatch_payload["document_review_required"] = True
        dispatch_payload["document_review_cleared"] = (
            application.document_review_cleared_at is not None
        )
    return dispatch_payload


def _record_inbound_escalation(
    session: Session,
    run: RunRef,
    candidate: Candidate,
    classification: str,
    actor: Actor,
    now: datetime,
) -> None:
    """G5 (F11 T4/S4): a classified abusive or distressed candidate message
    escalates to a human: a typed escalation event with the reason, an audit
    row carrying the classification, and the canned kind reply from the
    message catalog. No autonomous rejection, no tool call."""
    append_event(
        session,
        EventEnvelope(
            type=EventType.ESCALATION_CREATED,
            candidate_id=candidate.id,
            trace_id=run.trace_id,
            occurred_at=now + timedelta(microseconds=1),
            payload={
                "classification": classification,
                "source": "inbound_classifier",
                "actor_role": actor.kind.value,
            },
        ),
    )
    session.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=now + timedelta(microseconds=1),
            actor_type="system",
            actor_id="firstshift",
            application_id=run.application_id,
            candidate_id=candidate.id,
            event_type="inbound_escalation_created",
            state_from=None,
            state_to=None,
            payload={
                "classification": classification,
                "details": (
                    f"candidate message classified {classification} by the "
                    "inbound classifier; a human picks the conversation up (G5)"
                ),
            },
        )
    )
    _send_canned_candidate_reply(session, run, candidate, "escalation", now)


def _flag_documents_for_review(
    session: Session, run: RunRef, candidate: Candidate, now: datetime
) -> None:
    """Third-party document guard (F11 T4/S4): the submission claims the
    documents belong to another person, so the record is flagged for human
    review and the candidate is told, from the catalog. The row-21 tracker
    guard holds until People Ops clears the review."""
    application = session.get(Application, run.application_id)
    assert application is not None, f"application vanished: {run.application_id}"
    if not application.document_review_required:
        application.document_review_required = True
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=now + timedelta(microseconds=1),
                actor_type="system",
                actor_id="firstshift",
                application_id=application.id,
                candidate_id=candidate.id,
                event_type="documents_flagged_for_review",
                state_from=None,
                state_to=None,
                payload={
                    "reason": "third_party_documents",
                    "details": (
                        "the submission claims the documents belong to another "
                        "person; the tracker holds until People Ops clearance"
                    ),
                },
            )
        )
    _send_canned_candidate_reply(session, run, candidate, "document_review", now)


def _send_canned_candidate_reply(
    session: Session, run: RunRef, candidate: Candidate, template: str, now: datetime
) -> None:
    """Send one canned reply from the versioned message catalog to the
    candidate and record it as a message.out event (rule 7)."""
    body = candidate_body(template, candidate.preferred_language)
    language = candidate_language(candidate.preferred_language)
    if body is None:
        # A candidate-facing guard template without configured copy is a
        # programming error: fail loudly instead of sending anything else.
        raise RuntimeError(f"no catalog copy for guard template '{template}'")
    simulator_channel.send_message(
        OutboundMessage(
            recipient_ref=candidate.phone,
            body=body,
            correlation_id=run.trace_id,
            quick_replies=[],
        )
    )
    append_event(
        session,
        EventEnvelope(
            type=EventType.MESSAGE_OUT,
            candidate_id=candidate.id,
            trace_id=run.trace_id,
            occurred_at=now + timedelta(microseconds=2),
            payload={
                "template": template,
                "recipient_ref": candidate.phone,
                "body": body,
                "correlation_id": run.trace_id,
                "language": language,
            },
        ),
    )


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
                        **(
                            {"language": outbound.language}
                            if outbound.language is not None
                            else {}
                        ),
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
                        **(
                            {"language": matched.language}
                            if matched.language is not None
                            else {}
                        ),
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
                    **(
                        {"language": outbound.language}
                        if outbound.language is not None
                        else {}
                    ),
                },
            ),
        )
        appended += 1


class _PendingOutbound:
    """A channel message built from one core outbox effect."""

    def __init__(
        self, message: OutboundMessage, template: str, language: str | None = None
    ) -> None:
        self.message = message
        self.template = template
        # Language the body was written in; None for internal-recipient copy,
        # which is not candidate-facing (iteration-2 instrumentation: the tag
        # feeds the outbound_language_matches guardrail).
        self.language = language


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

    if template in CANDIDATE_FACING_TEMPLATES:
        # Candidate-facing copy follows the candidate's stated preferred
        # language (C-O4, iteration-2); the resolved language is carried on
        # the outbound so the language guardrail can verify it.
        body = candidate_body(template, candidate.preferred_language)
        language: str | None = candidate_language(candidate.preferred_language)
    else:
        body = (
            SIM_BODIES.get(template)
            or SIM_BODIES.get(template.replace(".", "_"))
            or SCRIPTED_BODIES.get(template)
        )
        language = None
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
        language=language,
    )
