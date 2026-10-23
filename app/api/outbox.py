"""Dead-letter queue API (F12 T2, S4): visible and replayable.

specs/06-integration-rollout.md section 2: "Outbox with exponential backoff
and a dead-letter queue visible and replayable in the console (/ops)".

- GET /api/outbox?status=failed lists dead-lettered writes with the fields
  IT and People Ops need: id, port, operation, attempts, last_error and the
  idempotency key that identifies the logical write (C-T5).
- POST /api/outbox/{id}/replay resets one dead-lettered row to pending with
  attempts 0, so the next relay pass claims and delivers it like any pending
  write (the idempotency key stays stable, so a replay can never double-
  apply). Replaying a row that is not failed is a 409 with a clear message.

Both actions are audited (INV-5) with the actor role from the console: the
X-Actor-Role header carries the operator's role (Talent, DPO, Ops, Admin per
spec 06 section 3), defaulting to ops. The audit row keeps who (actor),
what (the action and the row), when and why (previous state), so a replay of
a poisoned write is always explainable after the fact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.db.models import OUTBOX_STATUSES, AuditEvent, OutboxMessage

router = APIRouter(tags=["outbox"])

DEFAULT_ACTOR_ROLE = "ops"

# Values accepted by the ?status= filter: exactly the outbox status set from
# the data model, so the filter can never drift from what the relay writes.
_OUTBOX_STATUS_SET = frozenset(OUTBOX_STATUSES)

SessionDep = Annotated[Session, Depends(get_session)]


def _actor_role(x_actor_role: str | None) -> str:
    """The operator role for the audit record; ops is the default console
    role for reliability work."""
    if x_actor_role is None or not x_actor_role.strip():
        return DEFAULT_ACTOR_ROLE
    return x_actor_role.strip().lower()


def _audit(
    session: Session,
    *,
    role: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """One audit row (INV-5): who (console:{role}), what, when, why."""
    session.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(UTC),
            actor_type="system",
            actor_id=f"console:{role}",
            event_type=event_type,
            payload={**payload, "actor_role": role},
        )
    )


@router.get("/api/outbox")
def list_outbox(
    session: SessionDep,
    status: str = "failed",
    x_actor_role: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """List outbox writes filtered by status (default: the dead-letter queue).

    The dead-letter listing (?status=failed) is the console /ops view of
    every write that exhausted its retries: id, port, operation, attempts,
    last_error and idempotency_key.
    """
    if status not in _OUTBOX_STATUS_SET:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unknown status '{status}': expected one of "
                f"{', '.join(OUTBOX_STATUSES)}"
            ),
        )
    rows = session.scalars(
        select(OutboxMessage)
        .where(OutboxMessage.status == status)
        .order_by(OutboxMessage.id)
    ).all()
    messages = [
        {
            "id": str(row.id),
            "port": str(row.port),
            "operation": str(row.operation),
            "status": str(row.status),
            "attempts": row.attempts,
            "last_error": row.last_error,
            "idempotency_key": row.idempotency_key,
        }
        for row in rows
    ]
    _audit(
        session,
        role=_actor_role(x_actor_role),
        event_type="outbox.listed",
        payload={"status": status, "count": len(messages)},
    )
    return {"status": status, "messages": messages}


@router.post("/api/outbox/{message_id}/replay")
def replay_outbox_message(
    message_id: UUID,
    session: SessionDep,
    x_actor_role: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Reset one dead-lettered write to pending with attempts 0.

    The next relay pass claims the row and delivers it under the same
    idempotency key (C-T5), so the replay maps to the same logical write.
    A row that is not failed is refused with 409: pending rows are already
    in the relay's hands, and confirmed rows must not be rewritten.
    """
    row = session.get(OutboxMessage, message_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"outbox message {message_id} not found",
        )
    if row.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"outbox message {message_id} is not dead-lettered "
                f"(status: {row.status}): only failed rows can be replayed"
            ),
        )
    previous_status = str(row.status)
    previous_attempts = row.attempts
    previous_error = row.last_error
    row.status = "pending"
    row.attempts = 0
    row.next_retry_at = None
    row.last_error = None
    session.flush()
    _audit(
        session,
        role=_actor_role(x_actor_role),
        event_type="outbox.replay_requested",
        payload={
            "outbox_id": str(message_id),
            "port": str(row.port),
            "operation": str(row.operation),
            "idempotency_key": row.idempotency_key,
            "previous_status": previous_status,
            "previous_attempts": previous_attempts,
            "previous_error": previous_error,
        },
    )
    return {
        "id": str(message_id),
        "port": str(row.port),
        "operation": str(row.operation),
        "status": "pending",
        "attempts": 0,
        "idempotency_key": row.idempotency_key,
    }
