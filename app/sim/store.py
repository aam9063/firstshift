"""Simulator run store: one row per loaded scenario run (F07, T2).

A run owns three pieces of simulator state that must survive between HTTP
requests within a scenario run (specs/04-prototype.md section 2):

- the clock offset (app/sim/clock.py reads it to derive ``now``),
- the core Application snapshot the scripted backend dispatches from,
  including fired timers and guard facts,
- the run identity (trace id, candidate and application ids, manager).

The table is simulator-owned and created lazily with checkfirst the first
time a scenario loads; it carries no candidate PII beyond the run linkage
and is reset (deleted) on every scenario load. Client-system history itself
is never deleted: audit rows are append-only, so a new run gets a fresh
trace id and fresh candidate/application ids instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, String, Table, Uuid, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.state_machine import Application as CoreApplication
from app.core.state_machine import ManagerApproval, State
from app.db.base import Base


class SimRun(Base):
    """One loaded scenario run: clock offset, scripted snapshot, identity."""

    __tablename__ = "sim_runs"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(16))
    trace_id: Mapped[str] = mapped_column(String(64))
    hiredesk_application_id: Mapped[str] = mapped_column(String(64))
    candidate_id: Mapped[UUID] = mapped_column(Uuid())
    application_id: Mapped[UUID] = mapped_column(Uuid())
    manager_id: Mapped[str] = mapped_column(String(120))
    manager_name: Mapped[str] = mapped_column(String(120))
    base_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_offset_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    # Serialized core Application snapshot (app/sim/store.py codec).
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


@dataclass(frozen=True)
class RunRef:
    """The run fields the dispatch path needs, safe to pass across sessions."""

    id: UUID
    trace_id: str
    candidate_id: UUID
    application_id: UUID
    manager_id: str
    manager_name: str
    base_at: datetime
    snapshot_json: dict[str, Any] | None

    @classmethod
    def from_row(cls, run: SimRun) -> RunRef:
        return cls(
            id=run.id,
            trace_id=run.trace_id,
            candidate_id=run.candidate_id,
            application_id=run.application_id,
            manager_id=run.manager_id,
            manager_name=run.manager_name,
            base_at=run.base_at,
            snapshot_json=dict(run.snapshot) if run.snapshot is not None else None,
        )


def ensure_sim_tables(session: Session) -> None:
    """Create the simulator tables if absent (lazy, demo-scoped, idempotent)."""
    table = SimRun.__table__
    assert isinstance(table, Table)
    Base.metadata.create_all(bind=session.connection(), tables=[table], checkfirst=True)


def reset_and_create_run(session: Session, **values: Any) -> SimRun:
    """Delete prior run rows and insert the fresh one (scenario load reset)."""
    ensure_sim_tables(session)
    session.query(SimRun).delete()
    run = SimRun(id=uuid4(), **values)
    session.add(run)
    session.flush()
    return run


def get_active_run(session: Session) -> SimRun | None:
    """The most recently loaded run: the one the console is looking at."""
    ensure_sim_tables(session)
    return session.scalars(
        select(SimRun).order_by(SimRun.created_at.desc(), SimRun.id).limit(1)
    ).first()


def get_run_by_application(session: Session, application_id: UUID) -> SimRun | None:
    ensure_sim_tables(session)
    return session.scalars(
        select(SimRun).where(SimRun.application_id == application_id).limit(1)
    ).first()


def persist_clock_offset(session: Session, run_id: UUID, offset_seconds: float) -> None:
    """Store the advanced clock offset so it survives across requests."""
    session.execute(
        update(SimRun).where(SimRun.id == run_id).values(clock_offset_seconds=offset_seconds)
    )


# --------------------------------------------------- snapshot JSON codec
# The core Application snapshot carries datetimes and a nested frozen
# dataclass (ManagerApproval), neither of which JSONB stores natively.
# Datetimes are tagged {"__dt__": iso} so decoding is lossless.


def snapshot_to_json(snapshot: CoreApplication) -> dict[str, Any]:
    def encode(value: Any) -> Any:
        if isinstance(value, datetime):
            return {"__dt__": value.isoformat()}
        if isinstance(value, frozenset):
            return sorted(encode(item) for item in value)
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if isinstance(value, dict):
            return {key: encode(item) for key, item in value.items()}
        return value

    return {key: encode(value) for key, value in asdict(snapshot).items()}


def snapshot_from_json(data: dict[str, Any]) -> CoreApplication:
    def decode(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"__dt__"}:
            return datetime.fromisoformat(value["__dt__"])
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            return {key: decode(item) for key, item in value.items()}
        return value

    decoded = {key: decode(value) for key, value in data.items()}
    approval = decoded.pop("manager_approval", None)
    slots = decoded.pop("manager_open_slots", None) or []
    fired = decoded.pop("fired_timers", None) or []
    snapshot = CoreApplication(
        state=State(decoded.pop("state")),
        fired_timers=frozenset(fired),
        **decoded,
    )
    if approval is not None:
        snapshot = replace(snapshot, manager_approval=ManagerApproval(**approval))
    return replace(snapshot, manager_open_slots=tuple(slots))


def coerce_snapshot_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON-body snapshot updates into the core snapshot's types.

    Accepts ISO strings for datetime fields, ISO strings or lists for
    manager_open_slots, and a plain dict for manager_approval.
    """
    # Snapshot datetime fields; ISO strings from a JSON body are parsed.
    datetime_fields = {
        "contacted_at", "interview_at", "decision_requested_at",
        "offer_sent_at", "first_shift_at",
    }
    coerced: dict[str, Any] = {}
    for key, value in updates.items():
        if key == "manager_open_slots":
            items = value if isinstance(value, list) else [value]
            coerced[key] = tuple(
                datetime.fromisoformat(item) if isinstance(item, str) else item
                for item in items
            )
        elif key == "manager_approval" and isinstance(value, dict):
            approval = dict(value)
            if isinstance(approval.get("decided_at"), str):
                approval["decided_at"] = datetime.fromisoformat(approval["decided_at"])
            coerced[key] = ManagerApproval(**approval)
        elif key in datetime_fields and isinstance(value, str):
            coerced[key] = datetime.fromisoformat(value)
        else:
            coerced[key] = value
    return coerced


def clock_offset_to_timedelta(offset_seconds: float) -> timedelta:
    return timedelta(seconds=offset_seconds)
