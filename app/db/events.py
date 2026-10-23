"""Typed event model (S6): a common envelope plus the append-only events table.

Four event types exist in the skeleton; agent turn and tool-call events arrive
in F07 and will extend this enum. The console's live feed, simulator timeline
and candidate journey all read from this stream, so it is append-only: update
and delete are blocked by database triggers created in the core migration.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Uuid, insert
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventType(StrEnum):
    """Typed event stream types (S4/S6). Agent events added in F07."""

    STATE_TRANSITION = "state.transition"
    INTEGRATION_WRITE = "integration.write"
    MESSAGE_IN = "message.in"
    MESSAGE_OUT = "message.out"
    AGENT_TURN = "agent.turn"
    TOOL_CALL = "tool.call"
    UNMATCHED_INBOUND = "unmatched.inbound"
    # G5 (F11 T4/S4): a deterministic inbound classification (abusive or
    # distressed candidate message) escalates to a human. The Event.type
    # column is a plain String, so no migration is needed.
    ESCALATION_CREATED = "escalation.created"


class EventEnvelope(BaseModel):
    """Common envelope for every event in the stream."""

    event_id: UUID = Field(default_factory=uuid4)
    type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    candidate_id: UUID | None = None
    trace_id: str = Field(min_length=1)
    payload: dict[str, Any]


class Event(Base):
    """Append-only event row; the persisted form of an EventEnvelope."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)  # the envelope's event_id
    type: Mapped[str] = mapped_column(String(32))  # EventType value
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


def append_event(conn: Any, envelope: EventEnvelope) -> Event:
    """Append one envelope to the events table (the only write path)."""
    conn.execute(
        insert(Event).values(
            id=envelope.event_id,
            type=envelope.type.value,
            occurred_at=envelope.occurred_at,
            candidate_id=envelope.candidate_id,
            trace_id=envelope.trace_id,
            payload=envelope.payload,
        )
    )
    return Event(
        id=envelope.event_id,
        type=envelope.type.value,
        occurred_at=envelope.occurred_at,
        candidate_id=envelope.candidate_id,
        trace_id=envelope.trace_id,
        payload=envelope.payload,
    )
