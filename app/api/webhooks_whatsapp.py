"""Twilio WhatsApp inbound webhook (twilio-channel T1, S3/S5/S6).

POST /webhooks/whatsapp receives the Twilio sandbox's form-encoded inbound
message (From, To, Body, MessageSid, optional ProfileName). The handler
mirrors the HireDesk webhook (app/api/webhooks.py) semantics:

- S5 first: X-Twilio-Signature is validated against the full request URL and
  the form params with the subaccount auth token, before any processing. The
  check is skipped only when TWILIO_VALIDATE_SIGNATURE is explicitly false.
- S3 idempotency: the delivery is deduplicated on the provider message id
  (Twilio MessageSid) through the append-only events table, so a replayed
  delivery returns 200 "replayed" and creates nothing.
- S6 lookup: the sender is matched to a Candidate by phone (E.164
  normalized; the From value strips its whatsapp: prefix). An unknown phone
  gets a polite holding reply queued through the outbox whatsapp port and an
  unmatched_inbound event; it never creates a candidate, because candidate
  creation stays behind the HireDesk webhook.
- A matched candidate's message is persisted as message.in with the body
  text and dispatched through the deterministic core on the same persisted
  path as sim messages (audit rows, typed events, state mirror). Sandbox
  scope: the event is mapped from the message text by a small deterministic
  keyword table (consent yes/no); the LLM agent loop will replace this
  mapping in a later feature, and the LLM never decides transitions
  (architecture rule 1). A message that maps to nothing is recorded
  chat-only and answered with a scripted reply that discloses the AI (S4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.adapters.twilio import (
    TwilioChannelError,
    select_whatsapp_channel,
)
from app.api.deps import get_session
from app.core.state_machine import (
    Actor,
    ActorKind,
    State,
    StateMachine,
)
from app.core.state_machine import (
    Application as CoreApplication,
)
from app.db.events import Event, EventEnvelope, EventType, append_event
from app.db.models import (
    Application,
    AuditEvent,
    Candidate,
    Consent,
    OutboxMessage,
)
from app.ports.messaging import OutboundMessage
from app.services.scripted import _event_type_or_none
from app.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

NOTICE_VERSION = "v1"

# Scripted holding reply for any message the sandbox cannot act on: it is
# the first thing this channel says to the person, so it carries the AI
# disclosure (S4/G1). Spanish, the pilot default language.
HOLDING_REPLY_TEMPLATE = (
    "Hola: soy el asistente virtual (IA) de contratación de Lumbre Burger. "
    "Recibimos tu mensaje. Si enviaste tu postulación por el QR del "
    "restaurante, te escribiremos desde este canal con el siguiente paso. "
    "Responde Sí para dar tu consentimiento o No para detener el "
    "tratamiento de tus datos."
)

# Deterministic sandbox mapping from message text to core events (S6): only
# exact, normalized matches dispatch; everything else is chat-only. The
# consent guard requires the notice version (shown by the first contact) and
# the channel, both supplied below.
SANDBOX_TEXT_EVENTS = {
    "si": "candidate_consents",
    "sí": "candidate_consents",
    "yes": "candidate_consents",
    "no": "candidate_opted_out",
}

# Scripted replies per reached state (specs/04 §2: scripted replies before
# agents; the F08+ eval loop replaces these with real agent turns).
STATE_REPLIES: dict[str, str] = {
    "consented": (
        "Gracias, {name}. Para buscarte el turno que mejor te va, tres preguntas"
        " rápidas: 1) ¿Tienes derecho a trabajar en España? 2) ¿Cómo llegarías al"
        " restaurante? 3) ¿Qué idiomas hablas y qué turnos te van mejor?"
    ),
    "withdrawn": (
        "Entendido, {name}: dejamos de tratarte y tus datos se eliminan según la"
        " política de conservación. Gracias por tu tiempo."
    ),
}


def _canonical_url(request: Request) -> str:
    """The full request URL as Twilio signed it.

    Behind the cloudflared tunnel the app sees proxy headers, so forwarded
    proto/host win over the local URL when present.
    """
    url = request.url
    query = f"?{url.query}" if url.query else ""
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")
    if proto and host:
        return f"{proto}://{host}{url.path}{query}"
    if proto:
        return f"{proto}://{url.netloc}{url.path}{query}"
    return str(url)


def _normalize_phone(raw: str) -> str:
    """E.164 normalize a Twilio From/To value: strip the whatsapp: prefix,
    whitespace and separators, keep a single leading +."""
    number = raw.strip()
    if number.lower().startswith("whatsapp:"):
        number = number[len("whatsapp:") :]
    for char in " -.()":
        number = number.replace(char, "")
    if not number.startswith("+"):
        number = f"+{number}"
    return number


def _sandbox_event_for(text: str) -> str | None:
    return SANDBOX_TEXT_EVENTS.get(text.strip().lower())


def _queue_reply(
    session: Session,
    *,
    recipient_ref: str,
    body: str,
    trace_id: str,
    scope: str,
    object_id: str,
    related_entity_id: Any = None,
) -> tuple[OutboxMessage, OutboundMessage]:
    """Queue one outbound channel message through the outbox whatsapp port
    (ADR-003) with the C-T5 idempotency key scheme."""
    outbox_id = uuid4()
    outbound = OutboundMessage(
        recipient_ref=recipient_ref,
        body=body,
        quick_replies=[],
        correlation_id=trace_id,
    )
    row = OutboxMessage(
        id=outbox_id,
        port="whatsapp",
        operation="send",
        payload={
            "recipient_ref": outbound.recipient_ref,
            "body": outbound.body,
            "quick_replies": outbound.quick_replies,
            "correlation_id": outbound.correlation_id,
            "template": "holding_reply",
        },
        idempotency_key=f"fs/whatsapp/send/{scope}/{object_id}/{outbox_id}",
        # The selected channel adapter delivers inline right after this
        # insert (like the HireDesk webhook's simulator path); a delivery
        # failure leaves the row pending for the outbox relay.
        status="pending",
        related_entity_id=related_entity_id,
    )
    session.add(row)
    return row, outbound


def _deliver_queued(rows: list[tuple[OutboxMessage, Any]]) -> None:
    """Deliver the queued replies through the selected whatsapp adapter and
    confirm the rows, mirroring the HireDesk webhook's inline simulator
    delivery. A channel failure leaves the row pending for the relay."""
    adapter = select_whatsapp_channel()
    for row, outbound in rows:
        try:
            adapter.send_message(outbound)
        except TwilioChannelError:
            logger.warning(
                "whatsapp reply delivery deferred to the relay",
                outbox_id=str(row.id),
            )
            continue
        row.status = "api_confirmed"


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    # S5: signature validation happens before any processing. The whole raw
    # form is validated, not just the fields this handler names.
    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}

    if settings.require_twilio_signature:
        token = settings.twilio_auth_token
        if not token:
            raise HTTPException(
                status_code=500,
                detail="twilio signature validation is on but TWILIO_AUTH_TOKEN is not set",
            )
        validator = RequestValidator(token)
        signature = request.headers.get("x-twilio-signature", "")
        if not validator.validate(_canonical_url(request), params, signature):
            raise HTTPException(status_code=403, detail="invalid twilio signature")

    message_sid = params.get("MessageSid", "")
    from_number = params.get("From", "")
    body_text = params.get("Body", "")
    profile_name = params.get("ProfileName") or None
    if not message_sid or not from_number or not body_text:
        raise HTTPException(
            status_code=400, detail="missing MessageSid, From or Body"
        )

    # S3 idempotency: dedup on the provider message id through the
    # append-only event stream; a replayed delivery creates nothing.
    seen = session.scalar(
        select(Event.id).where(
            Event.type.in_(
                [EventType.MESSAGE_IN.value, EventType.UNMATCHED_INBOUND.value]
            ),
            Event.payload["provider_message_id"].astext == message_sid,
        )
    )
    if seen is not None:
        return JSONResponse(status_code=200, content={"status": "replayed"})

    now = datetime.now(UTC)
    phone = _normalize_phone(from_number)
    trace_id = f"wa-{message_sid}"
    candidate = session.scalar(select(Candidate).where(Candidate.phone == phone))

    if candidate is None:
        # S6: never a new candidate from an inbound message. The unmatched
        # arrival is observable (rule 7) without the body text (data
        # minimization: the sender is unverified), and a polite holding
        # reply is queued.
        session.execute(
            insert(Event).values(
                id=uuid4(),
                type=EventType.UNMATCHED_INBOUND.value,
                occurred_at=now,
                candidate_id=None,
                trace_id=trace_id,
                payload={
                    "channel": "whatsapp",
                    "provider_message_id": message_sid,
                    "from": phone,
                    "profile_name": profile_name,
                },
            )
        )
        logger.warning("whatsapp unmatched inbound", phone=phone, message_sid=message_sid)
        row, outbound = _queue_reply(
            session,
            recipient_ref=phone,
            body=HOLDING_REPLY_TEMPLATE,
            trace_id=trace_id,
            scope="unmatched",
            object_id=message_sid,
        )
        _deliver_queued([(row, outbound)])
        return JSONResponse(status_code=200, content={"status": "unmatched_inbound"})

    # Sandbox scope: the most recent application carries the conversation.
    application = session.scalar(
        select(Application)
        .where(Application.candidate_id == candidate.id)
        .order_by(Application.entered_at.desc())
        .limit(1)
    )

    inbound_payload: dict[str, Any] = {
        "channel": "whatsapp",
        "provider_message_id": message_sid,
        "from": phone,
        "profile_name": profile_name,
        "text": body_text,
    }

    # The message.in event precedes the transition it caused (rule 7).
    dispatched_event = _sandbox_event_for(body_text) if application is not None else None
    result = None
    if application is not None and dispatched_event is not None:
        snapshot = CoreApplication(
            application_id=str(application.id),
            state=State(application.state),
            notice_version=NOTICE_VERSION,
        )
        result = StateMachine().dispatch(
            snapshot,
            dispatched_event,
            Actor(ActorKind.CANDIDATE, candidate.first_name),
            now=now,
            payload={"channel": "whatsapp", "language": candidate.preferred_language},
        )
        if result.transitioned and result.to_state is not None:
            inbound_payload["event"] = dispatched_event
        else:
            # The core rejected the event: the message stays recorded, the
            # state does not move (same semantics as the sim path).
            result = None
            logger.warning(
                "whatsapp inbound dispatch rejected",
                event=dispatched_event,
                state=application.state,
            )

    append_event(
        session,
        EventEnvelope(
            type=EventType.MESSAGE_IN,
            candidate_id=candidate.id,
            trace_id=trace_id,
            occurred_at=now,
            payload=inbound_payload,
        ),
    )

    if result is not None and result.to_state is not None:
        assert application is not None  # result only exists with an application
        _persist_dispatch_effects(
            session,
            application=application,
            candidate=candidate,
            result=result,
            now=now,
            trace_id=trace_id,
            consent_requested=dispatched_event == "candidate_consents",
        )
        scripted = STATE_REPLIES.get(result.to_state.value)
        if scripted:
            row, outbound = _queue_reply(
                session,
                recipient_ref=phone,
                body=scripted.format(name=candidate.first_name),
                trace_id=trace_id,
                scope="candidate",
                object_id=message_sid,
                related_entity_id=candidate.id,
            )
            _deliver_queued([(row, outbound)])
    else:
        # Nothing could be dispatched: answer with the scripted holding
        # reply so the conversation never dead-ends.
        row, outbound = _queue_reply(
            session,
            recipient_ref=phone,
            body=HOLDING_REPLY_TEMPLATE,
            trace_id=trace_id,
            scope="unmatched" if application is None else "candidate",
            object_id=message_sid,
            related_entity_id=candidate.id,
        )
        _deliver_queued([(row, outbound)])

    return JSONResponse(
        status_code=200,
        content={
            "status": "processed",
            "candidate_id": str(candidate.id),
            "application_id": str(application.id) if application is not None else None,
            "event": inbound_payload.get("event"),
            "state": result.to_state.value if result and result.to_state else None,
        },
    )


def _persist_dispatch_effects(
    session: Session,
    *,
    application: Application,
    candidate: Candidate,
    result: Any,
    now: datetime,
    trace_id: str,
    consent_requested: bool,
) -> None:
    """Persist one dispatch result on the same path as sim messages: audit
    rows (INV-5) with the folded custom event types, typed envelope events,
    the Consent row when consent was granted, and the state mirror."""
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
                    "channel": "whatsapp",
                    "folded_events": [
                        {"type": event.type, "payload": event.payload} for event in folded
                    ],
                },
            )
        )

    for core_event in result.events:
        event_type = _event_type_or_none(core_event.type)
        if event_type is None:
            continue  # folded into the audit payload above
        append_event(
            session,
            EventEnvelope(
                type=event_type,
                candidate_id=candidate.id,
                trace_id=trace_id,
                occurred_at=now,
                payload=dict(core_event.payload),
            ),
        )

    if result.outbox_messages:
        # Sandbox scope: consent and opt-out produce no channel writes; a
        # core effect the webhook cannot persist fails loudly (rule 4).
        kinds = [message.kind for message in result.outbox_messages]
        raise HTTPException(
            status_code=500,
            detail=f"outbox kinds not wired for the whatsapp webhook: {kinds}",
        )

    if consent_requested:
        session.add(
            Consent(
                id=uuid4(),
                candidate_id=candidate.id,
                channel="whatsapp",
                purpose="screening",
                notice_version=NOTICE_VERSION,
                granted_at=now,
            )
        )

    application.state = result.to_state.value
    application.state_changed_at = now
    candidate.state = result.to_state.value  # mirrored from Application
