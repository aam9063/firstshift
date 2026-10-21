"""Simulator API (F07, T2; specs/04b-console.md section 2, simulator rows).

- POST /api/sim/scenarios/{id}/load: reset the simulator stores to a clean
  scenario state and fire the HireDesk "new application" webhook exactly
  like the mock does, so the candidate enters through the same persisted
  dispatch path as a real application (actor: system).
- POST /api/sim/clock/advance: advance the persisted clock by
  minutes/hours/days or jump to the next pending timer deadline, then run
  every due timer through the state machine (actor: timer, via the core).
- POST /api/sim/messages: send a message as candidate, manager or (until the
  agent layer lands, T1) system through the channel inbound path; each
  dispatched event is audited with its actor, and candidate/manager/system
  actions are all observable in the event stream.

The simulator is demo-scoped: the run store (app/sim/store.py) is reset on
every load; client-system history is append-only and never deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.webhooks import NOTICE_VERSION, HireDeskNewApplication, hiredesk_webhook
from app.core.state_machine import Application as CoreApplication
from app.core.state_machine import State
from app.db.models import Application
from app.sim.dispatch import SimDispatchRejected
from app.sim.runner import NoActiveRun, advance_clock, resolve_run, send_sim_message
from app.sim.scenarios import get_scenario
from app.sim.store import reset_and_create_run, snapshot_to_json

router = APIRouter(prefix="/api/sim", tags=["simulator"])

SessionDep = Annotated[Session, Depends(get_session)]


class ClockAdvanceBody(BaseModel):
    """Clock control: advance by amounts, or jump to the next timer."""

    minutes: float = 0.0
    hours: float = 0.0
    days: float = 0.0
    next_timer: bool = False


class SimMessageBody(BaseModel):
    """One simulated inbound message on the channel inbound path."""

    role: Literal["candidate", "manager", "system"]
    text: str = Field(min_length=1)
    event: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    application_id: UUID | None = None


@router.post("/scenarios/{scenario_id}/load", status_code=201)
def load_scenario(scenario_id: str, session: SessionDep) -> dict[str, Any]:
    """Reset the simulator stores and load one scenario's initial state."""
    try:
        scenario = get_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario_id}") from exc

    from app.sim.scenarios import resolve_relative_datetimes

    application_payload = resolve_relative_datetimes(
        scenario.application, datetime.now(UTC)
    )
    trace_id = f"sim-{scenario_id.lower()}-{uuid4().hex[:10]}"
    hiredesk_application_id = f"hd-sim-{scenario_id.lower()}-{uuid4().hex[:10]}"

    webhook_payload = HireDeskNewApplication(
        event="new_application",
        event_id=trace_id,
        application_id=hiredesk_application_id,
        candidate_id=f"hdc-sim-{uuid4().hex[:10]}",
        restaurant_id=str(application_payload.get("restaurant_id", "R001")),
        first_name=application_payload.get("first_name"),
        phone=application_payload.get("phone"),
        source=str(application_payload.get("source", "qr")),
    )

    # The reset: prior run rows go, the in-memory channel store is cleared.
    # Client-system history is append-only and stays; the new run gets a
    # fresh trace id so every stream consumer can scope to this run.
    from app.adapters.simulator import channel as simulator_channel

    simulator_channel.sent.clear()

    created = hiredesk_webhook(payload=webhook_payload, session=session)
    assert isinstance(created, dict), "a fresh scenario load cannot be a replay"

    application_id = UUID(created["application_id"])
    application = session.get(Application, application_id)
    assert application is not None
    base_at = application.state_changed_at

    # Seed the scripted snapshot: the webhook left the candidate contacted
    # with the first contact anchored at the load moment.
    snapshot = CoreApplication(
        application_id=str(application_id),
        state=State(application.state),
        notice_version=NOTICE_VERSION,
        language="es",
        contacted_at=base_at,
    )
    run = reset_and_create_run(
        session,
        scenario_id=scenario.id,
        trace_id=trace_id,
        hiredesk_application_id=hiredesk_application_id,
        candidate_id=UUID(created["candidate_id"]),
        application_id=application_id,
        manager_id=scenario.manager.id,
        manager_name=scenario.manager.name,
        base_at=base_at,
        clock_offset_seconds=0.0,
        snapshot=snapshot_to_json(snapshot),
        created_at=datetime.now(UTC),
    )

    return {
        "status": "loaded",
        "scenario_id": scenario.id,
        "run_id": str(run.id),
        "trace_id": trace_id,
        "hiredesk_application_id": hiredesk_application_id,
        "candidate_id": created["candidate_id"],
        "application_id": created["application_id"],
        "state": application.state,
        "base_at": base_at.isoformat(),
        "now": base_at.isoformat(),
        "manager": scenario.manager.model_dump(),
    }


@router.post("/clock/advance")
def advance(body: ClockAdvanceBody, session: SessionDep) -> dict[str, Any]:
    """Advance the active run's clock and fire every due timer."""
    engine = session.get_bind()
    try:
        run = resolve_run(engine, None)
        return advance_clock(
            engine,
            run,
            minutes=body.minutes,
            hours=body.hours,
            days=body.days,
            next_timer=body.next_timer,
        )
    except NoActiveRun as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/messages")
def send_message(body: SimMessageBody, session: SessionDep) -> dict[str, Any]:
    """Send a message as candidate, manager or system through the sim channel."""
    engine = session.get_bind()
    try:
        run = resolve_run(engine, str(body.application_id) if body.application_id else None)
        return send_sim_message(
            engine,
            run,
            role=body.role,
            text=body.text,
            event=body.event,
            payload=body.payload,
            snapshot_updates=body.snapshot or None,
        )
    except NoActiveRun as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SimDispatchRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
