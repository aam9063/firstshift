"""Simulator orchestration (F07, T2): clock advances and sim messages.

The API endpoints (app/api/sim.py) are thin wrappers over these functions.
Each function reads the run row, derives ``now`` from the persisted clock
offset (app/sim/clock.py), drives the deterministic core through the
persisted dispatch path (app/sim/dispatch.py) and reports what happened as
plain data for the console.

Timer firing mirrors StateMachine.tick's checks (declarative order, fired
set, state match, anchor, condition) but persists each due timer as its own
committed dispatch, because the request-scoped path cannot hold one open
transaction across the whole tick.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from app.core.policies import CONDITIONS, TIMER_DEFINITIONS
from app.core.state_machine import Actor, ActorKind
from app.core.state_machine import Application as CoreApplication
from app.sim.clock import SimClock
from app.sim.dispatch import (
    SimDispatchRejected,
    dispatch_and_persist,
    record_chat_message,
)
from app.sim.store import (
    RunRef,
    clock_offset_to_timedelta,
    coerce_snapshot_updates,
    get_active_run,
    get_run_by_application,
    persist_clock_offset,
    snapshot_from_json,
)


class NoActiveRun(RuntimeError):
    """No scenario run is active: load a scenario first."""


def resolve_run(engine: Any, application_id: str | None) -> RunRef:
    """The run to act on: by application id, else the most recent load."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        if application_id is not None:
            from uuid import UUID

            row = get_run_by_application(session, UUID(application_id))
        else:
            row = get_active_run(session)
        if row is None:
            raise NoActiveRun("no active scenario run: load a scenario first")
        return RunRef.from_row(row)


# ------------------------------------------------------------------ clock


def advance_clock(
    engine: Any,
    run: RunRef,
    *,
    minutes: float = 0.0,
    hours: float = 0.0,
    days: float = 0.0,
    next_timer: bool = False,
) -> dict[str, Any]:
    """Advance the run's clock and fire every timer due at the new now."""
    clock = SimClock(
        base_at=run.base_at,
        offset=clock_offset_to_timedelta(_stored_offset(engine, run)),
    )
    if next_timer:
        snapshot = _run_snapshot(run)
        target = clock.at_next_timer(snapshot)
        if target is None:
            return {
                "status": "no_pending_timer",
                "now": clock.now.isoformat(),
                "clock_offset_seconds": clock.offset.total_seconds(),
                "timers_fired": [],
                "timers_skipped": [],
                "state": snapshot.state.value,
            }
        new_now = target
    else:
        new_now = clock.now + timedelta(days=days, hours=hours, minutes=minutes)

    fired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    current = _run_snapshot(run)
    for timer in sorted(TIMER_DEFINITIONS, key=lambda d: d.offset):
        if timer.key in current.fired_timers:
            continue
        if current.state not in timer.states:
            continue
        anchor: datetime | None = getattr(current, timer.anchor)
        if anchor is None:
            continue
        due_at = anchor + timer.offset
        if new_now < due_at:
            continue
        if timer.condition is not None and not CONDITIONS[timer.condition](current, new_now):
            continue
        try:
            result = dispatch_and_persist(
                engine,
                run,
                event=timer.event,
                actor=Actor(ActorKind.TIMER, timer.key),
                now=new_now,
                payload={"timer": timer.key, "due_at": due_at.isoformat()},
                snapshot=current,
            )
        except SimDispatchRejected as exc:
            skipped.append({"timer": timer.key, "reason": str(exc)})
            continue
        fired.append(
            {
                "timer": timer.key,
                "event": timer.event,
                "from_state": result.from_state.value,
                "to_state": result.to_state.value if result.to_state else None,
            }
        )
        current = result.application

    offset_seconds = (new_now - run.base_at).total_seconds()
    from sqlalchemy.orm import Session

    with Session(engine) as session, session.begin():
        persist_clock_offset(session, run.id, offset_seconds)

    return {
        "status": "advanced",
        "next_timer": next_timer,
        "now": new_now.isoformat(),
        "clock_offset_seconds": offset_seconds,
        "timers_fired": fired,
        "timers_skipped": skipped,
        "state": current.state.value,
    }


# --------------------------------------------------------------- messages


def send_sim_message(
    engine: Any,
    run: RunRef,
    *,
    role: str,
    text: str,
    event: str | None = None,
    payload: dict[str, Any] | None = None,
    snapshot_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One simulated inbound message, through the persisted dispatch path.

    role candidate/manager are conversational actors; system stands in for
    the agent loop until the agent layer (T1) lands. A message without an
    event is chat-only: recorded, never dispatched. A rejected dispatch is
    answered as a conflict; the attempt remains observable as a message.in.

    Simulated conversations take time: every message advances the run's
    clock by MESSAGE_STEP (one minute), so the transcript's stream positions
    are monotonic and coherent with the clock control.
    """
    actor = _actor_for_role(engine, run, role)
    now = _advance_message_step(engine, run)
    coerced_payload = _coerce_payload(payload or {})
    coerced_updates = (
        coerce_snapshot_updates(snapshot_updates) if snapshot_updates else None
    )
    inbound = {"role": role, "actor_name": actor.name, "text": text}

    if event is None:
        record_chat_message(engine, run, actor=actor, text=text, now=now)
        return {
            "status": "recorded",
            "role": role,
            "event": None,
            "transitioned": False,
            "from_state": None,
            "to_state": None,
            "state": _run_snapshot(run).state.value,
            "trace_id": run.trace_id,
        }

    try:
        result = dispatch_and_persist(
            engine,
            run,
            event=event,
            actor=actor,
            now=now,
            payload=coerced_payload,
            snapshot_updates=coerced_updates,
            inbound=inbound,
        )
    except SimDispatchRejected:
        # Keep the attempt observable (rule 7): the message is stored even
        # though the core rejected the event and nothing transitioned.
        record_chat_message(
            engine, run, actor=actor, text=text, now=now, note="event_rejected"
        )
        raise
    assert result.to_state is not None, "a transitioned dispatch always has a to_state"
    return {
        "status": "accepted",
        "role": role,
        "event": event,
        "transitioned": True,
        "from_state": result.from_state.value,
        "to_state": result.to_state.value,
        "state": result.to_state.value,
        "application_id": str(run.application_id),
        "candidate_id": str(run.candidate_id),
        "trace_id": run.trace_id,
    }


# ------------------------------------------------------------------

MESSAGE_STEP = timedelta(minutes=1)


def _advance_message_step(engine: Any, run: RunRef) -> datetime:
    """Advance the run's clock by MESSAGE_STEP and return the new now."""
    from sqlalchemy.orm import Session

    offset_seconds = _stored_offset(engine, run) + MESSAGE_STEP.total_seconds()
    with Session(engine) as session, session.begin():
        persist_clock_offset(session, run.id, offset_seconds)
    return run.base_at + timedelta(seconds=offset_seconds)


def _actor_for_role(engine: Any, run: RunRef, role: str) -> Actor:
    if role == "candidate":
        from sqlalchemy.orm import Session

        from app.db.models import Candidate

        with Session(engine) as session:
            candidate = session.get(Candidate, run.candidate_id)
            name = candidate.first_name if candidate else None
        return Actor(ActorKind.CANDIDATE, name or "candidate")
    if role == "manager":
        return Actor(ActorKind.MANAGER, run.manager_id)
    if role == "system":
        # Stands in for the agent loop until T1: agent actions are recorded
        # as system actions (accountability sits with the system).
        return Actor(ActorKind.SYSTEM, "firstshift-sim")
    raise SimDispatchRejected(f"unknown role '{role}'")


def _stored_offset(engine: Any, run: RunRef) -> float:
    from sqlalchemy.orm import Session

    from app.sim.store import SimRun

    with Session(engine) as session:
        row = session.get(SimRun, run.id)
        return float(row.clock_offset_seconds) if row else 0.0


def _run_snapshot(run: RunRef) -> CoreApplication:
    if run.snapshot_json is None:
        raise NoActiveRun("scenario run has no snapshot")
    return snapshot_from_json(run.snapshot_json)


def _coerce_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse the ISO-string datetimes a JSON body carries into core types."""
    from datetime import datetime as dt

    def coerce(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _coerce_key(key, item) for key, item in value.items()}
        if isinstance(value, list):
            return [coerce(item) for item in value]
        return value

    def _coerce_key(key: str, value: Any) -> Any:
        if key in {"slot", "first_shift_at", "decided_at", "interview_at"} and isinstance(
            value, str
        ):
            return dt.fromisoformat(value)
        return coerce(value)

    return cast(dict[str, Any], coerce(payload))
