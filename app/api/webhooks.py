"""Inbound webhooks from the client-system mocks (S3, T5).

POST /webhooks/hiredesk receives the HireDesk "new application" webhook
emitted by mocks/services/routers/hiredesk.py. Delivery is at-least-once, so
the endpoint deduplicates on the HireDesk application id: a replayed delivery
returns 200 replayed and creates nothing (S5 spirit: idempotent inbound).

Deterministic core, LLM at the edge: the first contact is a scripted Spanish
template, no LLM in F06. The handler persists, in one transaction:
message.in (the webhook arrival), the state machine dispatch effects
(audit entry, state.transition, message.out) and the outbox row
(port whatsapp, C-T5 idempotency key), then hands the message to the
simulator channel adapter.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.deps import get_session
from app.core.degraded import known_statuses, pause_for_event
from app.core.state_machine import (
    Actor,
    ActorKind,
    State,
    StateMachine,
)
from app.core.state_machine import (
    Application as CoreApplication,
)
from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import Application, AuditEvent, Candidate, OutboxMessage, Restaurant
from app.ports.messaging import OutboundMessage
from app.services.scripted import candidate_language

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

NOTICE_VERSION = "v1"

# Scripted first contact (design row 2): carries the AI disclosure and the
# notice version. The body is the Spanish intake default: it is sent before
# the candidate has stated any preference in-channel, so C-O4's temporal rule
# cannot be violated; every composition after the candidate's first inbound
# follows the candidate's stated preferred language.
FIRST_MESSAGE_TEMPLATE = (
    "Hola {first_name}: soy el asistente virtual de contratación de Lumbre Burger "
    "para {restaurant_name}. Soy una IA y trato tus datos según el aviso de "
    "privacidad versión {notice_version}. ¿Nos das tu consentimiento para "
    "continuar por este canal? Responde Sí o No."
)


class HireDeskNewApplication(BaseModel):
    """Payload emitted by mocks/services/routers/hiredesk.py.

    first_name and phone are optional enrichment fields: the mock webhook
    carries only ids today, so neutral defaults keep the skeleton
    deterministic. FirstShift is the system of record; the candidate
    corrects these by chat.
    """

    event: str
    event_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    restaurant_id: str = Field(min_length=1)
    applied_at: datetime | None = None
    first_name: str | None = None
    phone: str | None = None
    source: str = "qr"
    # The application's stated language, when HireDesk knows it. None (the
    # real webhook today) keeps the Spanish intake default. It is the
    # candidate's preferred language from creation, so every later
    # composition (timer nudges, canned guard replies) uses it without
    # waiting for save_language_tag.
    language: str | None = None


def _pause_first_contact(
    session: Session,
    *,
    application: Application,
    candidate: Candidate,
    flow: str,
    system: str,
    trace_id: str,
    now: datetime,
    language: str,
) -> None:
    """Persist one paused first contact (F12 T2, S4): the audit record, the
    message.out event and the holding message from the versioned catalog as a
    confirmed outbox row. The application state is not touched."""
    from app.services.scripted import candidate_body, candidate_language

    tag = candidate_language(language)
    body = candidate_body("holding", tag)
    if body is None:  # pragma: no cover - catalog is versioned and complete
        raise HTTPException(status_code=500, detail="no holding copy configured")
    outbox_id = uuid4()
    session.add(
        OutboxMessage(
            id=outbox_id,
            port="whatsapp",
            operation="send",
            payload={
                "recipient_ref": candidate.phone,
                "body": body,
                "quick_replies": [],
                "correlation_id": trace_id,
                "template": "holding",
                "language": tag,
            },
            idempotency_key=(
                f"fs/whatsapp/send/{candidate.id}/{application.id}/{outbox_id}"
            ),
            status="api_confirmed",
            related_entity_id=candidate.id,
        )
    )
    session.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=now,
            actor_type="system",
            actor_id="firstshift.degraded_mode",
            application_id=application.id,
            candidate_id=candidate.id,
            event_type="flow.paused",
            payload={
                "flow": flow,
                "required_system": system,
                "reason": f"required client system '{system}' is degraded; flow '{flow}' paused",
                "template": "holding",
            },
        )
    )
    append_event(
        session,
        EventEnvelope(
            type=EventType.MESSAGE_OUT,
            candidate_id=candidate.id,
            trace_id=trace_id,
            occurred_at=now,
            payload={
                "template": "holding",
                "recipient_ref": candidate.phone,
                "body": body,
                "language": tag,
                "correlation_id": trace_id,
            },
        ),
    )


@router.post("/hiredesk", status_code=201, response_model=None)
def hiredesk_webhook(
    payload: HireDeskNewApplication,
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse | dict[str, str]:
    restaurant = session.scalar(
        select(Restaurant).where(Restaurant.code == payload.restaurant_id)
    )
    if restaurant is None:
        raise HTTPException(status_code=404, detail=f"unknown restaurant {payload.restaurant_id}")

    # Dedup on the payload id (the unique HireDesk application id): a
    # replayed delivery creates nothing.
    existing = session.scalar(
        select(Application).where(Application.hiredesk_application_id == payload.application_id)
    )
    if existing is not None:
        return JSONResponse(
            status_code=200,
            content={
                "status": "replayed",
                "candidate_id": str(existing.candidate_id),
                "application_id": str(existing.id),
            },
        )

    now = datetime.now(UTC)
    applied_at = payload.applied_at or now

    # The language source of truth: the stated intake language when supported,
    # the Spanish intake default when nothing states otherwise (candidate_language
    # normalizes unsupported values to the documented last resort).
    language = candidate_language(payload.language)

    candidate = Candidate(
        id=uuid4(),
        brand_id=restaurant.brand_id,
        first_name=payload.first_name or "Candidato",
        phone=payload.phone or "+34600000000",
        preferred_language=language,
        hiredesk_candidate_id=payload.candidate_id,
        state=State.NEW.value,
        source=payload.source,
    )
    application = Application(
        id=uuid4(),
        candidate_id=candidate.id,
        restaurant_id=restaurant.id,
        hiredesk_application_id=payload.application_id,
        state=State.NEW.value,
        entered_at=applied_at,
        state_changed_at=now,
    )
    session.add(candidate)
    # No mapper-level relationship() links the two models, so the unit of
    # work does not order these inserts by FK: flush the candidate before
    # the application that references it.
    session.flush()
    session.add(application)
    session.flush()

    trace_id = payload.event_id
    append_event(
        session,
        EventEnvelope(
            type=EventType.MESSAGE_IN,
            candidate_id=candidate.id,
            trace_id=trace_id,
            payload={
                "channel": "hiredesk.webhook",
                "event": payload.event,
                "event_id": payload.event_id,
                "hiredesk_application_id": payload.application_id,
                "restaurant_id": payload.restaurant_id,
                "applied_at": applied_at.isoformat(),
            },
        ),
    )

    # S4 degraded mode: when the channel is degraded, first contact pauses.
    # The candidate is created (the application row is the client's record),
    # the state does not advance, and the candidate receives the holding
    # message instead of silence.
    pause = pause_for_event("intake_processed", known_statuses())
    if pause is not None:
        flow, system = pause
        _pause_first_contact(
            session,
            application=application,
            candidate=candidate,
            flow=flow,
            system=system,
            trace_id=trace_id,
            now=now,
            language=language,
        )
        return {
            "status": "paused",
            "candidate_id": str(candidate.id),
            "application_id": str(application.id),
            "paused_by": system,
        }

    result = StateMachine().dispatch(
        CoreApplication(application_id=str(application.id), state=State.NEW),
        "intake_processed",
        Actor(ActorKind.SYSTEM, "firstshift-webhook"),
        now=now,
        payload={"notice_version": NOTICE_VERSION, "ai_disclosed": True, "language": language},
    )
    if not result.transitioned or result.to_state is None:
        # Unreachable while the guard payload is fixed above; fail loudly
        # rather than persist a half-created candidate.
        raise HTTPException(status_code=500, detail=f"dispatch rejected: {result.rejection_reason}")

    body = FIRST_MESSAGE_TEMPLATE.format(
        first_name=candidate.first_name,
        restaurant_name=restaurant.name,
        notice_version=NOTICE_VERSION,
    )
    outbound = OutboundMessage(
        recipient_ref=candidate.phone,
        body=body,
        quick_replies=["Sí", "No"],
        correlation_id=trace_id,
    )

    outbox_id = uuid4()
    session.add(
        OutboxMessage(
            id=outbox_id,
            port="whatsapp",
            operation="send",
            payload={
                "recipient_ref": outbound.recipient_ref,
                "body": outbound.body,
                "quick_replies": outbound.quick_replies,
                "correlation_id": outbound.correlation_id,
                "template": "first_message",
                "notice_version": NOTICE_VERSION,
            },
            idempotency_key=f"fs/whatsapp/send/{restaurant.code}/{application.id}/{outbox_id}",
            # The simulator adapter is in-process: delivery is observed
            # synchronously. The T6 relay owns status handling for adapters
            # that deliver asynchronously.
            status="api_confirmed",
            related_entity_id=candidate.id,
        )
    )

    for event in result.events:
        event_payload = dict(event.payload)
        if event.type == EventType.MESSAGE_OUT.value:
            event_payload.update(
                {
                    "recipient_ref": outbound.recipient_ref,
                    "body": outbound.body,
                    "correlation_id": outbound.correlation_id,
                }
            )
        append_event(
            session,
            EventEnvelope(
                type=EventType(event.type),
                candidate_id=candidate.id,
                trace_id=trace_id,
                payload=event_payload,
            ),
        )

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
                    "hiredesk_application_id": payload.application_id,
                },
            )
        )

    application.state = result.to_state.value
    application.state_changed_at = now
    candidate.state = result.to_state.value  # mirrored from Application

    simulator_channel.send_message(outbound)

    return {
        "status": "created",
        "candidate_id": str(candidate.id),
        "application_id": str(application.id),
    }
