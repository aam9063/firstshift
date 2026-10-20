"""Shared setup for the simulator tests (F07, T2/T3).

Every test runs against a throwaway Postgres schema (fresh_migrated_schema,
function scope: audit rows are append-only, so state cannot be reused across
tests) and drives the simulator through its public HTTP interface only:
POST /api/sim/scenarios/{id}/load, POST /api/sim/clock/advance and
POST /api/sim/messages.

The fixtures themselves live in each test module (pytest convention); this
module provides the factories and the scenario step driver they share.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.deps import get_session
from app.main import app
from tests.test_db_models import fresh_migrated_schema


def fresh_sim_engine() -> Iterator[Engine]:
    """Factory behind the per-module sim_engine fixtures."""
    with fresh_migrated_schema() as eng:
        yield eng


def make_sim_client(engine: Engine) -> Iterator[TestClient]:
    """Factory behind the per-module sim_client fixtures: seeded, overridden."""
    from app.db.seed import seed_restaurants

    with engine.begin() as conn:
        seed_restaurants(conn)

    simulator_channel.sent.clear()

    def override_get_session() -> Iterator[Session]:
        session = Session(engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def load_scenario(sim_client: TestClient, scenario_id: str) -> dict[str, Any]:
    """Load a scenario through the API and return the run payload."""
    response = sim_client.post(f"/api/sim/scenarios/{scenario_id}/load")
    assert response.status_code == 201, response.text
    return response.json()


def drive_scenario(
    sim_client: TestClient, scenario_id: str, *, upto: int | None = None
) -> dict[str, Any]:
    """Load a scenario and execute its scripted steps through the sim API.

    Each scenario step maps to one sim API call, exactly as the console's
    simulator pane would: clock steps to POST /api/sim/clock/advance and
    message steps to POST /api/sim/messages. Relative datetimes in step
    payloads are resolved against the run's base_at.
    """
    from app.sim.scenarios import get_scenario, resolve_relative_datetimes

    run = load_scenario(sim_client, scenario_id)
    base = datetime.fromisoformat(run["base_at"])
    scenario = get_scenario(scenario_id)
    steps = scenario.steps if upto is None else scenario.steps[:upto]
    for step in steps:
        if step.kind == "clock":
            body: dict[str, Any] = {
                "minutes": step.minutes,
                "hours": step.hours,
                "days": step.days,
                "next_timer": step.next_timer,
            }
            response = sim_client.post("/api/sim/clock/advance", json=body)
            assert response.status_code == 200, response.text
        else:
            payload = resolve_relative_datetimes(step.payload, base)
            snapshot = resolve_relative_datetimes(step.snapshot, base)
            body = {
                "role": step.role,
                "text": step.text,
                "payload": _jsonable(payload),
                "snapshot": _jsonable(snapshot),
            }
            if step.event is not None:
                body["event"] = step.event
            response = sim_client.post("/api/sim/messages", json=body)
            expected = 409 if step.expect_reject else 200
            assert response.status_code == expected, response.text
    return run


def _jsonable(value: Any) -> Any:
    """Datetimes to ISO strings so the payload survives the JSON body."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def trace_events(sim_engine: Engine, trace_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Persisted envelope events for one scenario run, in stream order."""
    from sqlalchemy import select

    from app.db.events import Event

    with Session(sim_engine) as session:
        rows = session.scalars(
            select(Event).where(Event.trace_id == trace_id).order_by(Event.occurred_at, Event.id)
        ).all()
        return [(row.type, dict(row.payload)) for row in rows]


def application_state(sim_engine: Engine, application_id: str) -> str:
    from sqlalchemy import select

    from app.db.models import Application

    with Session(sim_engine) as session:
        row = session.scalars(
            select(Application).where(Application.id == application_id)
        ).one()
        session.expunge(row)
        return str(row.state)
