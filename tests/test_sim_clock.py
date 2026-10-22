"""T2 (S3): the controllable simulator clock.

specs/04-prototype.md section 2: "a clock control to fast-forward timers
(nudges, reminders, cutoffs) so the demo can show a 10-day journey in 2
minutes" and specs/04b-console.md section 3.9 (+1 h, +1 day, jump to next
timer).

Covered here:
- Advancing 2 h fires the T1 no-reply nudge; the offset persists across
  requests, so a second advance continues from there (nudge_2, not nudge_1
  again; fired timers are remembered).
- Advancing past 48 h benches the silent candidate (row 5).
- next_timer jumps exactly to the soonest pending timer deadline (manager
  decision SLA: remind at 2 h, escalate at 8 h).
- Advancing with no active run is rejected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from tests.test_sim_common import (
    drive_scenario,
    fresh_sim_engine,
    load_scenario,
    make_sim_client,
    trace_events,
)


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


def _fired_timers(response_json: dict[str, Any]) -> list[str]:
    return [entry["timer"] for entry in response_json["timers_fired"]]


def test_clock_advance_fires_nudge_and_offset_persists(
    sim_client: TestClient, sim_engine: Engine
) -> None:
    run = load_scenario(sim_client, "D1")

    first = sim_client.post("/api/sim/clock/advance", json={"hours": 2})
    assert first.status_code == 200, first.text
    body = first.json()
    assert _fired_timers(body) == ["no_reply_nudge_1"]
    assert body["state"] == "contacted"

    # The nudge reached the candidate channel and the event stream.
    events = trace_events(sim_engine, run["trace_id"])
    outbound = [payload for event_type, payload in events if event_type == "message.out"]
    assert any(payload.get("template") == "nudge_1" for payload in outbound)

    # A second advance continues from the persisted offset: nudge_2 at 24 h,
    # and nudge_1 never fires twice.
    second = sim_client.post("/api/sim/clock/advance", json={"hours": 22})
    assert second.status_code == 200, second.text
    assert _fired_timers(second.json()) == ["no_reply_nudge_2"]
    outbound = [
        payload
        for event_type, payload in trace_events(sim_engine, run["trace_id"])
        if event_type == "message.out"
    ]
    assert [
        payload.get("template")
        for payload in outbound
        if "nudge" in str(payload.get("template", ""))
    ] == [
        "nudge_1",
        "nudge_2",
    ]


def test_clock_advance_silent_candidate_benched_at_48h(
    sim_client: TestClient, sim_engine: Engine
) -> None:
    run = load_scenario(sim_client, "D1")

    response = sim_client.post("/api/sim/clock/advance", json={"days": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    assert _fired_timers(body) == [
        "no_reply_nudge_1",
        "no_reply_nudge_2",
        "no_reply_bench",
    ]
    assert body["state"] == "benched"

    from sqlalchemy.orm import Session

    from app.db.models import Candidate

    with Session(sim_engine) as session:
        from uuid import UUID

        candidate = session.get(Candidate, UUID(run["candidate_id"]))
        assert candidate is not None
        assert candidate.state == "benched"


def test_clock_next_timer_jumps_to_sla_deadlines(sim_client: TestClient) -> None:
    """D5 timers: remind at 2 h, escalate at 8 h after the decision request."""
    drive_scenario(sim_client, "D5", upto=6)  # through decision_requested

    remind = sim_client.post("/api/sim/clock/advance", json={"next_timer": True})
    assert remind.status_code == 200, remind.text
    body = remind.json()
    assert _fired_timers(body) == ["manager_decision_remind"]
    assert body["state"] == "pending_manager_decision"

    escalate = sim_client.post("/api/sim/clock/advance", json={"next_timer": True})
    assert escalate.status_code == 200, escalate.text
    assert _fired_timers(escalate.json()) == ["manager_decision_escalate"]

    # The escalation jumped 6 h further than the reminder.
    from datetime import datetime

    remind_at = datetime.fromisoformat(remind.json()["now"])
    escalate_at = datetime.fromisoformat(escalate.json()["now"])
    assert (escalate_at - remind_at).total_seconds() == 6 * 3600


def test_clock_advance_without_active_run_rejected(sim_client: TestClient) -> None:
    response = sim_client.post("/api/sim/clock/advance", json={"hours": 1})
    assert response.status_code == 409


def test_clock_advance_d4_confirmation_cutoff_activates_backup(
    sim_client: TestClient, sim_engine: Engine
) -> None:
    """D4: the cutoff (T-18 h) activates the bench backup, no confirmation."""
    run = drive_scenario(sim_client, "D4", upto=11)  # through first_shift_picked

    response = sim_client.post("/api/sim/clock/advance", json={"next_timer": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert _fired_timers(body) == ["confirmation_cutoff"]
    assert body["state"] == "first_shift_scheduled"

    events = trace_events(sim_engine, run["trace_id"])
    assert any(
        event_type == "message.out" and payload.get("template") == "backup.activate"
        for event_type, payload in events
    )
