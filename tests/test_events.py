"""T4 (S6): typed event model and append-only event/audit tables.

The envelope (event_id, type, occurred_at, candidate_id, trace_id, payload) is
a Pydantic model validated in tests; the `events` and `audit_events` tables are
append-only, enforced by database triggers (INV-5).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.test_db_models import fresh_migrated_schema


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    with fresh_migrated_schema() as eng:
        yield eng


# ---------------------------------------------------------------- envelope


def test_event_envelope_defaults_and_validation() -> None:
    from app.db.events import EventEnvelope, EventType

    envelope = EventEnvelope(
        type=EventType.STATE_TRANSITION, trace_id="trc-123", payload={"from": "new"}
    )
    assert isinstance(envelope.event_id, uuid.UUID)
    assert envelope.occurred_at is not None
    assert envelope.candidate_id is None
    assert envelope.type is EventType.STATE_TRANSITION


def test_event_envelope_rejects_unknown_type_and_missing_trace() -> None:
    from pydantic import ValidationError

    from app.db.events import EventEnvelope, EventType

    with pytest.raises(ValidationError):
        EventEnvelope(type="made.up.type", trace_id="trc-123", payload={})  # type: ignore[arg-type]
    # F07: agent events are now first-class typed events.
    assert (
        EventEnvelope(type="agent.turn", trace_id="trc-123", payload={}).type
        is EventType.AGENT_TURN
    )
    assert (
        EventEnvelope(type="tool.call", trace_id="trc-123", payload={}).type
        is EventType.TOOL_CALL
    )
    with pytest.raises(ValidationError):
        EventEnvelope(type="state.transition", payload={})  # missing trace_id
    with pytest.raises(ValidationError):
        EventEnvelope(type="state.transition", trace_id="", payload={})  # empty trace_id


def test_event_envelope_json_roundtrip() -> None:
    from app.db.events import EventEnvelope, EventType

    envelope = EventEnvelope(
        type=EventType.MESSAGE_OUT,
        candidate_id=uuid.uuid4(),
        trace_id="trc-456",
        payload={"text": "Hola"},
    )
    parsed = EventEnvelope.model_validate_json(envelope.model_dump_json())
    assert parsed == envelope


def test_typed_event_types_exist() -> None:
    from app.db.events import EventType

    # The four skeleton types (S6) plus the F07 agent events.
    assert {t.value for t in EventType} == {
        "state.transition",
        "integration.write",
        "message.in",
        "message.out",
        "agent.turn",
        "tool.call",
        "unmatched.inbound",
        "escalation.created",
    }


# ------------------------------------------------------- append-only tables


def _insert_event(engine: Engine) -> uuid.UUID:
    from sqlalchemy import insert

    from app.db.events import Event

    event_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(Event).values(
                id=event_id,
                type="message.out",
                occurred_at=datetime.now(UTC),
                candidate_id=None,
                trace_id="trc-append-only",
                payload={"text": "Hola"},
            )
        )
    return event_id


def _insert_audit_event(engine: Engine) -> uuid.UUID:
    from sqlalchemy import insert

    from app.db.models import AuditEvent

    audit_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(AuditEvent).values(
                id=audit_id,
                occurred_at=datetime.now(UTC),
                actor_type="system",
                actor_id="core.state-machine",
                event_type="state.transition",
                state_from="new",
                state_to="contacted",
                payload={"reason": "first message sent"},
                idempotency_key="fs/hiredesk/update_stage/R001/app_1/ob_1",
            )
        )
    return audit_id


def test_events_table_is_append_only(engine: Engine) -> None:
    from sqlalchemy import delete, func, select, update

    from app.db.events import Event

    event_id = _insert_event(engine)

    with (  # UPDATE and DELETE must be rejected by the database
        pytest.raises(DBAPIError, match="append-only"),
        engine.begin() as conn,
    ):
        conn.execute(update(Event).where(Event.id == event_id).values(payload={"tampered": True}))

    with (
        pytest.raises(DBAPIError, match="append-only"),
        engine.begin() as conn,
    ):
        conn.execute(delete(Event).where(Event.id == event_id))
    with Session(engine) as session:  # the original row survives untouched
        row = session.scalars(select(Event).where(Event.id == event_id)).one()
        count = session.scalar(select(func.count()).select_from(Event))
    assert row.payload == {"text": "Hola"}
    assert count >= 1


def test_audit_events_table_is_append_only_inv5(engine: Engine) -> None:
    """INV-5: every transition is appended to an immutable audit log."""
    from sqlalchemy import delete, select, update

    from app.db.models import AuditEvent

    audit_id = _insert_audit_event(engine)

    with (
        pytest.raises(DBAPIError, match="append-only"),
        engine.begin() as conn,
    ):
        conn.execute(
            update(AuditEvent).where(AuditEvent.id == audit_id).values(state_to="tampered")
        )

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(delete(AuditEvent).where(AuditEvent.id == audit_id))

    with Session(engine) as session:
        row = session.scalars(select(AuditEvent).where(AuditEvent.id == audit_id)).one()
    assert str(row.state_to) == "contacted"


def test_audit_event_carriers_who_what_when_why(engine: Engine) -> None:
    """INV-5 fields: who (actor), what (event_type), when (occurred_at), why (payload)."""
    from sqlalchemy import select

    from app.db.models import AuditEvent

    audit_id = _insert_audit_event(engine)
    with Session(engine) as session:
        row = session.scalars(select(AuditEvent).where(AuditEvent.id == audit_id)).one()
    assert row.occurred_at is not None
    assert row.actor_type in {"candidate", "manager", "agent", "system", "timer"}
    assert row.actor_id == "core.state-machine"
    assert row.event_type == "state.transition"
    assert row.payload == {"reason": "first message sent"}
