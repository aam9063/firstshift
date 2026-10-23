"""Outbox relay (S5): deliver pending outbox writes to async ports.

specs/04-prototype.md section 1.5: "Outbox table and relay worker writing a
stage update back to HireDesk mock, idempotent (test: relay the same message
twice, one write)." design/integration-contracts.md, shared conventions:

- "All writes go through the outbox; the relay worker delivers with retries
  and records every attempt" (C-T6).
- "Default retry policy: 5 attempts, exponential backoff 1s, 4s, 16s, 60s with
  jitter; after the last attempt the outbox message is failed, an AuditEvent
  records it."
- Idempotency key scheme (C-T5): the key is generated once when the message
  enters the outbox and stable across retries, so a replayed delivery maps to
  the same logical write.

Claim semantics: rows are claimed with SELECT ... FOR UPDATE SKIP LOCKED inside
a transaction, so two relay workers never pick up the same pending row, and a
claimed row (status ``relaying``) is invisible to later passes until its
outcome is committed. Only async ports are relayed here; the simulator channel
adapter delivers synchronously and already confirms its rows (``api_confirmed``).

The function is callable directly (no Redis, no Celery); the Celery wrapper in
app/workers/tasks.py calls it on the production cadence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import insert, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import AuditEvent, OutboxMessage
from app.ports.hiredesk import HireDeskPort, StageUpdate

MAX_ATTEMPTS = 5  # integration-contracts default retry policy
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 4.0, 16.0, 60.0)

# Ports whose writes need an out-of-band relay. Sync channels (the simulator
# messaging adapter) deliver inline and confirm their own outbox rows.
ASYNC_PORTS = ("hiredesk",)
STAGE_UPDATE_OPERATION = "update_stage"

CLAIM_BATCH_SIZE = 100


@dataclass
class RelayResult:
    """What one relay pass did, per claimed message."""

    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    dead_lettered: int = 0


def _backoff_after_attempt(attempt: int) -> float:
    """Exponential schedule 1s, 4s, 16s, 60s (capped at the last step)."""
    return RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]


def _claim_due(engine: Engine, now: datetime) -> list[dict[str, Any]]:
    """Claim due pending rows for async ports, FOR UPDATE SKIP LOCKED.

    The claim commits as ``relaying``, so a concurrent worker's SKIP LOCKED
    read (or any later pass) can never double-claim the same row. A worker
    crash after the claim leaves the row in ``relaying``; recovering stale
    claims arrives with the ops features, it is not silently retried here.
    """
    claimed: list[dict[str, Any]] = []
    # ORM Session, not Connection: entity selects materialize only through the
    # Session (Connection.scalars on an entity select yields the first column).
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(OutboxMessage)
            .where(
                OutboxMessage.port.in_(ASYNC_PORTS),
                OutboxMessage.status == "pending",
                or_(
                    OutboxMessage.next_retry_at.is_(None),
                    OutboxMessage.next_retry_at <= now,
                ),
            )
            .with_for_update(skip_locked=True)
            .limit(CLAIM_BATCH_SIZE)
        ).all()
        for row in rows:
            row.status = "relaying"
            claimed.append(
                {
                    "id": row.id,
                    "port": str(row.port),
                    "operation": row.operation,
                    "payload": dict(row.payload),
                    "idempotency_key": row.idempotency_key,
                    "related_entity_id": row.related_entity_id,
                }
            )
    return claimed


class PayloadRejected(Exception):
    """The stored payload does not match the port schema for its operation."""


STAGE_OPERATIONS = (STAGE_UPDATE_OPERATION,)  # S5 scope: HireDesk stage updates only


def _build_payload(message: dict[str, Any]) -> StageUpdate:
    """Parse the stored payload into the port's validated Pydantic model.

    A payload the port schema rejects can never succeed on retry, so the
    caller dead-letters it immediately (never retried, contracts taxonomy).
    The reserved ``trace_id`` key (trace propagation, F12 T2/S4) is not part
    of the port schema and is stripped here; the attempt recorder reads it
    straight from the stored payload.
    """
    if message["operation"] not in STAGE_OPERATIONS:
        raise PayloadRejected(f"unknown async operation: {message['operation']}")
    payload_data = {
        key: value for key, value in message["payload"].items() if key != "trace_id"
    }
    return StageUpdate.model_validate(payload_data)


def _journey_trace(message: dict[str, Any]) -> str:
    """The candidate journey's trace id for one outbox message (F12 T2/S4).

    The outbox schema has no trace column, so the dispatch path puts the
    journey trace under the reserved ``trace_id`` payload key. Rows written
    before that change (or by paths that do not set it) fall back to the
    outbox row id, the pre-F12 behavior.
    """
    trace = message["payload"].get("trace_id")
    if isinstance(trace, str) and trace:
        return trace
    return str(message["id"])


def _record_attempt(
    engine: Engine,
    message: dict[str, Any],
    outcome: str,
    attempt: int,
    now: datetime,
    error: str | None,
) -> None:
    """Every attempt emits one typed integration.write event (rule 7, C-T6).

    The event carries the candidate journey's trace id, not the outbox row
    id, so the journey is traceable across messages, state transitions and
    integration calls end to end (F12 T2, S4).
    """
    with engine.begin() as conn:
        append_event(
            conn,
            EventEnvelope(
                type=EventType.INTEGRATION_WRITE,
                trace_id=_journey_trace(message),
                payload={
                    "outbox_id": str(message["id"]),
                    "port": message["port"],
                    "operation": message["operation"],
                    "idempotency_key": message["idempotency_key"],
                    "attempt": attempt,
                    "outcome": outcome,
                    "error": error,
                },
            ),
        )


def _record_dead_letter(engine: Engine, message: dict[str, Any], attempts: int, error: str) -> None:
    """The audit-log record IT queries by idempotency key (C-T6).

    related_entity_id travels in the payload, not in the application_id FK:
    the outbox row does not carry the entity type, and a wrong FK would
    poison the dead letter itself.
    """
    with engine.begin() as conn:
        conn.execute(
            insert(AuditEvent).values(
                id=uuid4(),
                occurred_at=datetime.now(UTC),
                actor_type="system",
                actor_id="outbox.relay",
                event_type="integration.write.dead_letter",
                payload={
                    "outbox_id": str(message["id"]),
                    "port": message["port"],
                    "operation": message["operation"],
                    "related_entity_id": (
                        str(message["related_entity_id"])
                        if message["related_entity_id"]
                        else None
                    ),
                    "attempts": attempts,
                    "error": error,
                    # Trace propagation (F12 T2/S4): the dead-letter audit
                    # names the journey too, so IT can find every attempt of
                    # one candidate journey by trace id.
                    "trace_id": _journey_trace(message),
                },
                idempotency_key=message["idempotency_key"],
            )
        )


def _deliver(engine: Engine, hiredesk: HireDeskPort, message: dict[str, Any], now: datetime) -> str:
    """Deliver one claimed message and commit its outcome.

    Returns "delivered", "retried" or "dead_lettered"; the row lock from the
    claiming transaction is not held: the claim committed first, the outcome
    here is a short transaction on the single claimed row.
    """
    with Session(engine) as session, session.begin():
        row = session.get(OutboxMessage, message["id"])
        assert row is not None, f"claimed outbox row vanished: {message['id']}"
        attempt = row.attempts + 1
        row.attempts = attempt

        error: str | None
        try:
            payload = _build_payload(message)
        except (ValidationError, PayloadRejected) as exc:
            row.status = "failed"
            row.next_retry_at = None
            row.last_error = f"payload rejected by port schema: {exc}"
            error = row.last_error
            outcome = "dead_lettered"
        else:
            try:
                hiredesk.update_stage(payload)
            except Exception as exc:  # adapter failure: retry per the default policy
                if attempt >= MAX_ATTEMPTS:
                    row.status = "failed"
                    row.next_retry_at = None
                    outcome = "dead_lettered"
                else:
                    row.status = "pending"
                    row.next_retry_at = now + timedelta(seconds=_backoff_after_attempt(attempt))
                    outcome = "retried"
                error = str(exc)
                row.last_error = error
            else:
                row.status = "api_confirmed"
                row.next_retry_at = None
                row.last_error = None
                error = None
                outcome = "delivered"

    _record_attempt(engine, message, outcome, attempt, now, error)
    if outcome == "dead_lettered":
        _record_dead_letter(engine, message, attempt, error or "payload rejected")
    return outcome


def relay_pending(
    engine: Engine,
    hiredesk: HireDeskPort,
    now: datetime | None = None,
) -> RelayResult:
    """One relay pass over due pending outbox rows for async ports.

    ``hiredesk`` is the injected port adapter (mock or real); tests pass a
    counting fake. ``now`` is injectable so backoff schedules are testable.
    """
    result = RelayResult()
    at = now or datetime.now(UTC)
    for message in _claim_due(engine, at):
        result.claimed += 1
        outcome = _deliver(engine, hiredesk, message, at)
        if outcome == "delivered":
            result.delivered += 1
        elif outcome == "retried":
            result.retried += 1
        else:
            result.dead_lettered += 1
    return result
