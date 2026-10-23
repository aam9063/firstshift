"""Console action endpoints (T6; every action audited with X-Actor-Role).

- POST /api/candidates/{id}/takeover and /release: the takeover state lives
  in the append-only audit log (helpers.agent_in_control derives it).
- POST /api/candidates/{id}/messages: a human message during takeover is a
  message.out event with sender_type "human"; when the candidate belongs to
  an active simulator run it is also delivered through the simulator channel
  so the demo candidate pane shows it.
- POST /api/restaurants/{id}/pause: pause (and resume) all agents for one
  restaurant, audited per restaurant code.
- POST /api/outbox/{id}/replay: reuses app/outbox/relay.relay_pending on a
  dead-lettered row; only failed hiredesk rows can be replayed in this
  milestone (the relay's async-port set).
- POST /api/erasure-requests: records the DPO's erasure request as an audit
  event; the endpoint never deletes data by itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.console.helpers import (
    RESTAURANT_PAUSED_EVENT,
    RESTAURANT_RESUMED_EVENT,
    agent_in_control,
    append_audit,
    audit_human_action,
    candidate_or_404,
    require_role,
)
from app.api.console.schemas import (
    ErasureBody,
    ErasureResponse,
    HumanMessageBody,
    MessageResponse,
    PauseBody,
    PauseResponse,
    ReleaseResponse,
    ReplayResponse,
    TakeoverResponse,
)
from app.api.deps import get_session
from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import OutboxMessage, Restaurant
from app.outbox.relay import relay_pending
from app.settings import settings

router = APIRouter(prefix="/api", tags=["console-actions"])

SessionDep = Annotated[Session, Depends(get_session)]
RoleDep = Annotated[str, Depends(require_role)]


@router.post("/candidates/{candidate_id}/takeover", response_model=TakeoverResponse)
def takeover(candidate_id: UUID, session: SessionDep, role: RoleDep) -> TakeoverResponse:
    candidate = candidate_or_404(session, candidate_id)
    audit_human_action(
        session,
        role=role,
        action="takeover",
        candidate_id=candidate.id,
        payload={"from_state": candidate.state},
    )
    return TakeoverResponse(
        candidate_id=str(candidate.id), agent_in_control=False, taken_over_by=role
    )


@router.post("/candidates/{candidate_id}/release", response_model=ReleaseResponse)
def release(candidate_id: UUID, session: SessionDep, role: RoleDep) -> ReleaseResponse:
    candidate = candidate_or_404(session, candidate_id)
    audit_human_action(
        session,
        role=role,
        action="release",
        candidate_id=candidate.id,
        payload={"to_state": candidate.state},
    )
    return ReleaseResponse(
        candidate_id=str(candidate.id), agent_in_control=True, released_by=role
    )


@router.post(
    "/candidates/{candidate_id}/messages",
    status_code=201,
    response_model=MessageResponse,
)
def send_human_message(
    candidate_id: UUID, body: HumanMessageBody, session: SessionDep, role: RoleDep
) -> MessageResponse:
    candidate = candidate_or_404(session, candidate_id)
    if agent_in_control(session, candidate.id):
        raise HTTPException(
            status_code=409,
            detail="the agent is in control: take over before sending a human message",
        )
    trace_id = f"console-{uuid4().hex[:10]}"
    message_id = uuid4()
    envelope = append_event(
        session,
        EventEnvelope(
            event_id=message_id,
            type=EventType.MESSAGE_OUT,
            candidate_id=candidate.id,
            trace_id=trace_id,
            payload={
                "channel": "console",
                "sender_type": "human",
                "role": role,
                "body": body.text,
            },
        ),
    )
    _deliver_to_simulator_channel(session, candidate.id, candidate.phone, body.text, trace_id)
    audit_human_action(
        session,
        role=role,
        action="message",
        candidate_id=candidate.id,
        payload={"message_id": str(message_id)},
    )
    return MessageResponse(
        id=str(message_id),
        candidate_id=str(candidate.id),
        sender_type="human",
        text=body.text,
        at=envelope.occurred_at.isoformat(),
    )


def _deliver_to_simulator_channel(
    session: Session, candidate_id: UUID, phone: str, text: str, trace_id: str
) -> None:
    """Best-effort channel delivery during a demo run; recording is the truth."""
    from app.adapters.simulator import channel as simulator_channel
    from app.ports.messaging import OutboundMessage
    from app.sim.store import SimRun

    run = session.scalars(
        select(SimRun).where(SimRun.candidate_id == candidate_id).limit(1)
    ).first()
    if run is None:
        return  # no active demo run: the event record is still the truth
    simulator_channel.send_message(
        OutboundMessage(recipient_ref=phone, body=text, correlation_id=trace_id)
    )


@router.post("/restaurants/{restaurant_id}/pause", response_model=PauseResponse)
def pause_restaurant(
    restaurant_id: UUID, session: SessionDep, role: RoleDep, body: PauseBody | None = None
) -> PauseResponse:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    resume = bool(body and body.resume)
    append_audit(
        session,
        event_type=RESTAURANT_RESUMED_EVENT if resume else RESTAURANT_PAUSED_EVENT,
        actor_id=f"console:{role}",
        payload={
            "role": role,
            "restaurant_code": restaurant.code,
            "action": "resume" if resume else "pause",
        },
    )
    return PauseResponse(
        restaurant_id=str(restaurant.id), code=restaurant.code, paused=not resume
    )


@router.post("/outbox/{message_id}/replay", response_model=ReplayResponse)
def replay_outbox_message(
    message_id: UUID, session: SessionDep, role: RoleDep
) -> ReplayResponse:
    row = session.get(OutboxMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown outbox message")
    if row.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"only dead-lettered (failed) rows can be replayed; row is {row.status}",
        )
    if row.port != "hiredesk":
        raise HTTPException(
            status_code=409,
            detail="replay is wired for the hiredesk async port only in this milestone",
        )

    # Back on the schedule with a fresh attempt budget, then one relay pass
    # reusing the existing relay logic (claim, deliver, retry or dead-letter).
    row.status = "pending"
    row.attempts = 0
    row.next_retry_at = None
    append_audit(
        session,
        event_type="outbox.replay",
        actor_id=f"console:{role}",
        payload={
            "role": role,
            "outbox_id": str(row.id),
            "idempotency_key": row.idempotency_key,
            "port": str(row.port),
            "operation": row.operation,
        },
    )
    session.commit()  # the relay uses its own sessions and must see this row

    from app.adapters.hiredesk import HireDeskAdapter

    engine = session.get_bind()
    assert isinstance(engine, Engine)  # get_bind on an ORM session is an Engine
    adapter = HireDeskAdapter.from_settings(settings)
    relay_pending(engine, adapter, now=datetime.now(UTC))

    session.expire_all()
    refreshed = session.get(OutboxMessage, message_id)
    assert refreshed is not None
    return ReplayResponse(
        id=str(refreshed.id), status=refreshed.status, attempts=refreshed.attempts
    )


@router.post("/erasure-requests", status_code=201, response_model=ErasureResponse)
def create_erasure_request(
    body: ErasureBody, session: SessionDep, role: RoleDep
) -> ErasureResponse:
    candidate = candidate_or_404(session, body.candidate_id)
    event = append_audit(
        session,
        event_type="erasure.requested",
        actor_id=f"console:{role}",
        candidate_id=candidate.id,
        payload={
            "role": role,
            "reason": body.reason or "",
            "status": "requested",
            "note": (
                "The DPO erasure process executes the deletion; this request "
                "records who asked, when and why (C-L5)."
            ),
        },
    )
    return ErasureResponse(
        id=str(event.id),
        candidate_id=str(candidate.id),
        status="requested",
        requested_at=event.occurred_at.isoformat(),
    )
