"""Scripted event dispatch (F06, T7): the persisted dispatch path without the LLM.

The HireDesk webhook handler (app/api/webhooks.py) owns the first contact:
it loads the payload, dispatches intake_processed through the pure core and
persists the effects (audit, typed events, outbox) in one transaction. Every
later candidate/manager/system event of the walking skeleton needs exactly
the same dispatch-and-persist path, driven by scripted inputs instead of an
agent (specs/04 section 1, Milestone A: "a scripted candidate reaches
first_shift_scheduled using only mocks").

This module is that path as a thin wrapper, mirroring the webhook handler's
persistence semantics row for row:

- one transaction per event (like one request-scoped session),
- the pure StateMachine.dispatch result becomes AuditEvent rows (INV-5),
  EventEnvelope appends (S6) and OutboxMessage rows (ADR-003),
- application and candidate state move forward together (mirror rule).

Core facts that guards read (notice version, offer timestamps, manager
approval, interview slot, document and hygiene flags) live on the pure
Application snapshot and are kept in memory per journey: the skeleton has no
column store for them yet, and the agents feature (F07) replaces this
wrapper with the real agent loop.

No business logic here: guards, effects and state names come from the core;
this file only persists what dispatch returns and raises on any rejection so
a scripted flow fails loudly instead of silently stalling.
"""

import logging
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.core.state_machine import (
    Actor,
    ActorKind,
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

DEFAULT_NOTICE_VERSION = "v1"
CONVERSATIONAL_ACTORS = frozenset({ActorKind.CANDIDATE, ActorKind.MANAGER})

# Outbox kinds that are channel messages: delivered in-process through the
# simulator adapter and confirmed immediately, like the webhook's first
# message. Everything else is an async port write claimed by the relay.
WHATSAPP_KINDS = frozenset({"whatsapp.out", "trainer.notify", "bench.reserve_backup"})

# Recipient of each scripted channel message; the skeleton's messages go to
# the candidate, the manager, or (row 23) the trainer and the bench backup.
_RECIPIENT_BY_KIND = {
    "whatsapp.out": None,  # resolved per payload ("to": "manager" or the candidate)
    "trainer.notify": "trainer-sim",
    "bench.reserve_backup": "bench-backup-sim",
}

# Scripted bodies per template (Spanish, the pilot default language).
_SCRIPTED_BODIES = {
    "decision_request": (
        "Resumen del candidato y decision pendiente: revisa el resumen y "
        "responde aprobar o no seguir."
    ),
    "offer": "Oferta de empleo de Lumbre Burger: responde SI para aceptar.",
    "nudge_1": "¿Seguimos con tu solicitud? Responde para continuar.",
    "nudge_2": "Tu solicitud sigue abierta: responde para continuar.",
    "interview_reminder": "Recordatorio de tu entrevista en Lumbre Burger.",
    "bench_reengagement": "Tenemos una nueva vacante para ti en Lumbre Burger.",
    "bench_offer": "¿Quieres quedar en nuestra bolsa de empleo?",
    "rejection": "Gracias por tu interes: en esta ocasion no seguimos.",
}


# F10 iteration-2 language-aware candidate-facing copy (specs/05 section 4,
# one measured change; C-O4 language matches candidate).
#
# Per-language variants of the seven CANDIDATE_FACING_TEMPLATES. The Spanish
# entries reuse the Spanish map above (single source of the original copy);
# Spanish is also the documented last-resort fallback, used only when the
# candidate's language is genuinely unknown or unsupported. The variants keep
# the meaning of the Spanish originals, stay WhatsApp-sized and add no
# promises. Internal-recipient bodies (decision_request and the SIM_BODIES
# templates) are not candidate-facing and are not translated.
CANDIDATE_BODY_LANGUAGES = ("es", "pt", "en")
DEFAULT_CANDIDATE_LANGUAGE = "es"

_CANDIDATE_BODIES: dict[str, dict[str, str]] = {
    "es": {
        "offer": _SCRIPTED_BODIES["offer"],
        "nudge_1": _SCRIPTED_BODIES["nudge_1"],
        "nudge_2": _SCRIPTED_BODIES["nudge_2"],
        "interview_reminder": _SCRIPTED_BODIES["interview_reminder"],
        "bench_reengagement": _SCRIPTED_BODIES["bench_reengagement"],
        "bench_offer": _SCRIPTED_BODIES["bench_offer"],
        "rejection": _SCRIPTED_BODIES["rejection"],
    },
    "pt": {
        "offer": "Oferta de emprego da Lumbre Burger: responde SIM para aceitar.",
        "nudge_1": "Continuamos com a tua candidatura? Responde para continuar.",
        "nudge_2": "A tua candidatura continua aberta: responde para continuar.",
        "interview_reminder": "Lembrete da tua entrevista na Lumbre Burger.",
        "bench_reengagement": "Temos uma nova vaga para ti na Lumbre Burger.",
        "bench_offer": "Queres ficar na nossa bolsa de emprego?",
        "rejection": "Obrigado pelo teu interesse: nesta ocasião não continuamos.",
    },
    "en": {
        "offer": "Job offer from Lumbre Burger: reply YES to accept.",
        "nudge_1": "Shall we continue with your application? Reply to keep going.",
        "nudge_2": "Your application is still open: reply to keep going.",
        "interview_reminder": "Reminder of your interview at Lumbre Burger.",
        "bench_reengagement": "We have a new vacancy for you at Lumbre Burger.",
        "bench_offer": "Would you like to stay in our talent pool?",
        "rejection": "Thank you for your interest: this time we will not move forward.",
    },
}


def candidate_language(preferred_language: str | None) -> str:
    """The language candidate-facing copy is written in for this candidate:
    the stated preferred language when supported, Spanish as the documented
    last resort when it is genuinely unknown or unsupported."""
    if preferred_language is not None and preferred_language in _CANDIDATE_BODIES:
        return preferred_language
    return DEFAULT_CANDIDATE_LANGUAGE


def candidate_body(template: str, preferred_language: str | None) -> str | None:
    """Candidate-facing copy for one template in the candidate's language."""
    return _CANDIDATE_BODIES[candidate_language(preferred_language)].get(template)


# F09 iteration-1 channel-body guard (specs/05 section 4, one measured change).
#
# CANDIDATE_FACING_TEMPLATES is the explicit whitelist of outbox templates that
# have real candidate-facing human copy. INTERNAL_RECIPIENT_KINDS are the
# outbox kinds whose recipients are internal roles, never the candidate, and
# INTERNAL_RECIPIENT_REFS are the simulated internal recipient refs the two
# dispatch paths route them to. Body resolution order:
#   1. configured template copy,
#   2. internal-recipient safe body (internal recipients only),
#   3. never a candidate-facing fallback identifier: an unknown kind addressed
#      to a candidate is not delivered as a message; it is recorded (warning
#      log, rule 7) and no pending outbound is returned.
CANDIDATE_FACING_TEMPLATES = frozenset(
    {
        "offer",
        "rejection",
        "nudge_1",
        "nudge_2",
        "interview_reminder",
        "bench_offer",
        "bench_reengagement",
    }
)

INTERNAL_RECIPIENT_KINDS = frozenset(
    {"trainer.notify", "bench.reserve_backup", "backup.activate"}
)

INTERNAL_RECIPIENT_REFS = frozenset(
    {"manager-sim", "hrbp-sim", "trainer-sim", "bench-backup-sim"}
)

# Safe body for an internal recipient when no configured copy exists: a
# human-readable notice, never the raw outbox kind.
INTERNAL_FALLBACK_BODY = (
    "Aviso interno del sistema de contratacion: revisa el panel de operaciones."
)

LOGGER = logging.getLogger(__name__)


def is_internal_recipient(kind: str, recipient_ref: str) -> bool:
    """True when the message goes to an internal role, never to a candidate."""
    return kind in INTERNAL_RECIPIENT_KINDS or recipient_ref in INTERNAL_RECIPIENT_REFS


class ScriptedDispatchError(RuntimeError):
    """A scripted event was rejected by the core: the journey cannot continue."""


@dataclass(frozen=True)
class _PendingOutbound:
    """A channel message built from one core outbox effect."""

    message: OutboundMessage
    template: str
    # Language the body was written in; None for internal-recipient copy,
    # which is not candidate-facing (iteration-2 instrumentation: the tag
    # feeds the outbound_language_matches guardrail).
    language: str | None = None


class ScriptedJourney:
    """Drives one application through scripted events to a target state."""

    def __init__(
        self,
        engine: Engine,
        *,
        application_id: UUID,
        candidate_id: UUID,
        trace_id: str,
        notice_version: str = DEFAULT_NOTICE_VERSION,
    ) -> None:
        self._engine = engine
        self._application_id = application_id
        self._candidate_id = candidate_id
        self._trace_id = trace_id
        self._notice_version = notice_version
        self._snapshots: dict[str, CoreApplication] = {}

    def apply(
        self,
        *,
        event: str,
        actor: Actor,
        payload: dict[str, Any] | None = None,
        snapshot_updates: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> DispatchResult:
        """Dispatch one scripted event and persist its effects in one transaction."""
        with Session(self._engine) as session, session.begin():
            application = session.scalars(
                select(Application).where(Application.id == self._application_id)
            ).one()
            candidate = session.get(Candidate, self._candidate_id)
            assert candidate is not None, f"candidate vanished: {self._candidate_id}"

            snapshot = self._snapshot_for(application)
            if snapshot_updates:
                snapshot = self._with_updates(snapshot, snapshot_updates)

            result = StateMachine().dispatch(
                snapshot, event, actor, now=now, payload=payload or {}
            )
            if not result.transitioned or result.to_state is None:
                raise ScriptedDispatchError(
                    f"event '{event}' rejected in state "
                    f"'{application.state}': {result.rejection_reason}"
                )
            self._snapshots[str(application.id)] = result.application

            # An inbound channel message precedes every human-driven event
            # (rule 7: the conversation, not just the outcome, is observable).
            if actor.kind in CONVERSATIONAL_ACTORS:
                append_event(
                    session,
                    EventEnvelope(
                        type=EventType.MESSAGE_IN,
                        candidate_id=candidate.id,
                        trace_id=self._trace_id,
                        payload={"channel": "simulator", "event": event},
                    ),
                )

            self._persist_audit(session, application, candidate, result)
            self._persist_outbox_and_events(session, application, candidate, result)

            application.state = result.to_state.value
            application.state_changed_at = now or datetime.now(UTC)
            candidate.state = result.to_state.value  # mirrored from Application
        return result

    # ------------------------------------------------------------- internals

    def _snapshot_for(self, application: Application) -> CoreApplication:
        cached = self._snapshots.get(str(application.id))
        if cached is not None:
            return cached
        return CoreApplication(
            application_id=str(application.id),
            state=State(application.state),
            notice_version=self._notice_version,
            shift_type="food_handling",
        )

    @staticmethod
    def _with_updates(
        snapshot: CoreApplication, updates: dict[str, Any]
    ) -> CoreApplication:
        valid = {f.name for f in fields(CoreApplication)}
        unknown = set(updates) - valid
        if unknown:
            raise ScriptedDispatchError(
                f"unknown snapshot fields: {sorted(unknown)}; "
                f"valid fields are {sorted(valid)}"
            )
        return replace(snapshot, **updates)

    def _persist_audit(
        self,
        session: Session,
        application: Application,
        candidate: Candidate,
        result: DispatchResult,
    ) -> None:
        folded = [event for event in result.events if _event_type_or_none(event.type) is None]
        for entry in result.audit_entries:
            session.add(
                AuditEvent(
                    id=uuid4(),
                    occurred_at=entry.at or datetime.now(UTC),
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
        self,
        session: Session,
        application: Application,
        candidate: Candidate,
        result: DispatchResult,
    ) -> None:
        restaurant_code = session.scalar(
            select(Restaurant.code).where(Restaurant.id == application.restaurant_id)
        )
        assert restaurant_code is not None, "application without restaurant scope"

        outbounds: dict[str, _PendingOutbound] = {}
        for core_message in result.outbox_messages:
            kind = core_message.kind
            row_id = uuid4()
            if kind in WHATSAPP_KINDS:
                outbound = self._whatsapp_outbound(
                    kind, core_message.payload, candidate
                )
                if outbound is None:
                    # The body guard suppressed a candidate-facing send
                    # without configured copy; the warning log keeps the
                    # suppression observable (rule 7).
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
                raise ScriptedDispatchError(f"unmapped outbox kind: {kind}")

        for core_event in result.events:
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
                    trace_id=self._trace_id,
                    payload=payload,
                ),
            )

    def _whatsapp_outbound(
        self, kind: str, core_payload: dict[str, object], candidate: Candidate
    ) -> _PendingOutbound | None:
        template = str(core_payload.get("template") or kind)
        recipient_ref = _RECIPIENT_BY_KIND.get(kind)
        if recipient_ref is None:
            recipient_ref = (
                "manager-sim" if core_payload.get("to") == "manager" else candidate.phone
            )
        body: str | None
        language: str | None = None
        if template in CANDIDATE_FACING_TEMPLATES:
            # Candidate-facing copy follows the candidate's stated preferred
            # language (C-O4, iteration-2); the resolved language is carried
            # on the outbound so the language guardrail can verify it.
            body = candidate_body(template, candidate.preferred_language)
            language = candidate_language(candidate.preferred_language)
        else:
            body = _SCRIPTED_BODIES.get(template)
        if body is None:
            if is_internal_recipient(kind, recipient_ref):
                body = INTERNAL_FALLBACK_BODY
            else:
                # Never a candidate-facing fallback identifier (F09 T2): the
                # kind stays observable through the warning log only.
                LOGGER.warning(
                    "suppressed candidate-facing outbound without configured copy: "
                    "kind=%s template=%s candidate=%s trace=%s",
                    kind,
                    template,
                    candidate.id,
                    self._trace_id,
                )
                return None
        return _PendingOutbound(
            message=OutboundMessage(
                recipient_ref=recipient_ref,
                body=body,
                correlation_id=self._trace_id,
                quick_replies=["Sí", "No"] if template == "first_message" else [],
            ),
            template=template,
            language=language,
        )


def _event_type_or_none(raw: str) -> EventType | None:
    """Envelope event types only; skeleton-domain events fold into the audit."""
    try:
        return EventType(raw)
    except ValueError:
        return None
