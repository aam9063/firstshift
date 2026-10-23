"""T2-T5 (S1, S3, S4): read endpoint behavior, not just shape.

Data rules under test (odd/tasks/console-api.md rule 4):
- the backend never fabricates: unknown values are explicit empty or zero and
  the accompanying text says so,
- phone numbers are masked to their last three digits,
- documents appear only as status rows, never as contents,
- KPIs and funnel follow design/metric-tree.md formulas over the event and
  audit log; a series without history returns an empty trend and an honest
  insight.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import Application, Candidate
from tests.test_sim_common import drive_scenario, fresh_sim_engine, make_sim_client


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


@pytest.fixture()
def restaurant_id() -> str:
    from sqlalchemy import select

    from app.db.models import Restaurant

    with Session(_LAST_ENGINE) as session:
        found = session.scalar(select(Restaurant.id).where(Restaurant.code == "R001"))
        assert found is not None
        return str(found)


@pytest.fixture()
def driven(sim_client: TestClient) -> dict[str, Any]:
    return drive_scenario(sim_client, "D1")


def add_candidate(
    engine: Engine,
    *,
    restaurant_code: str,
    state: str,
    phone: str,
    language: str = "es",
    first_name: str = "Ana",
    entered_days_ago: float = 1.0,
) -> str:
    """Insert one candidate + application row pair for filter tests."""
    from sqlalchemy import select

    from app.db.models import Restaurant

    with Session(engine) as session, session.begin():
        restaurant_id = session.scalar(
            select(Restaurant.id).where(Restaurant.code == restaurant_code)
        )
        assert restaurant_id is not None, f"missing seeded restaurant {restaurant_code}"
        candidate_id = uuid4()
        entered_at = datetime.now(UTC) - timedelta(days=entered_days_ago)
        session.add(
            Candidate(
                id=candidate_id,
                brand_id="lumbre",
                first_name=first_name,
                phone=phone,
                preferred_language=language,
                state=state,
                source="qr",
            )
        )
        session.flush()  # candidate row first: no ORM relationship sorts it
        session.add(
            Application(
                id=uuid4(),
                candidate_id=candidate_id,
                restaurant_id=restaurant_id,
                state=state,
                entered_at=entered_at,
                state_changed_at=entered_at,
            )
        )
        return str(candidate_id)


# ------------------------------------------------------------- candidates list


def test_pagination(sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]) -> None:
    for index in range(3):
        add_candidate(
            sim_engine,
            restaurant_code="R002",
            state="contacted",
            phone=f"+3460010000{index}",
        )
    page1 = sim_client.get("/api/candidates", params={"page": 1, "pageSize": 2}).json()
    page2 = sim_client.get("/api/candidates", params={"page": 2, "pageSize": 2}).json()
    assert page1["total"] == 4
    assert page1["pageSize"] == 2
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    ids1 = {item["id"] for item in page1["items"]}
    ids2 = {item["id"] for item in page2["items"]}
    assert ids1.isdisjoint(ids2), "pages must not overlap"


def test_filter_by_state_language_and_restaurant(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    add_candidate(
        sim_engine, restaurant_code="R002", state="screening", phone="+346002000001"
    )
    by_state = sim_client.get("/api/candidates", params={"state": "screening"}).json()
    assert by_state["total"] == 1
    assert by_state["items"][0]["state"] == "screening"

    by_language = sim_client.get("/api/candidates", params={"language": "es"}).json()
    assert by_language["total"] >= 2

    by_restaurant = sim_client.get(
        "/api/candidates", params={"restaurant": "R002"}
    ).json()
    assert by_restaurant["total"] == 1
    assert by_restaurant["items"][0]["restaurantCode"] == "R002"


def test_filter_by_cohort_follows_restaurant_seed(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    add_candidate(
        sim_engine, restaurant_code="R002", state="contacted", phone="+346003000001"
    )
    pilot = sim_client.get("/api/candidates", params={"cohort": "pilot"}).json()
    control = sim_client.get("/api/candidates", params={"cohort": "control"}).json()
    assert pilot["total"] + control["total"] >= 2
    assert all(item["cohort"] == "pilot" for item in pilot["items"])
    assert all(item["cohort"] == "control" for item in control["items"])


def test_filter_by_agent_follows_state_group(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    add_candidate(
        sim_engine, restaurant_code="R002", state="preboarding", phone="+346004000001"
    )
    add_candidate(
        sim_engine, restaurant_code="R003", state="contacted", phone="+346004000002"
    )
    recruit = sim_client.get("/api/candidates", params={"agent": "recruit"}).json()
    onboard = sim_client.get("/api/candidates", params={"agent": "onboard"}).json()
    # The driven D1 candidate (first_shift_worked) also belongs to onboard.
    assert onboard["total"] >= 2
    assert recruit["total"] >= 1
    assert all(item["state"] in ONBOARD_STATES for item in onboard["items"])
    assert all(item["state"] not in ONBOARD_STATES for item in recruit["items"])


ONBOARD_STATES = {
    "preboarding",
    "ready_for_rota",
    "first_shift_scheduled",
    "first_shift_confirmed",
    "first_shift_worked",
}


def test_sla_risk_flags_pending_manager_decisions(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    add_candidate(
        sim_engine,
        restaurant_code="R002",
        state="pending_manager_decision",
        phone="+346005000001",
        entered_days_ago=3.0,
    )
    breached = sim_client.get("/api/candidates", params={"sla_risk": "breached"}).json()
    assert breached["total"] == 1
    assert breached["items"][0]["slaRisk"] == "breached"
    ok = sim_client.get("/api/candidates", params={"sla_risk": "ok"}).json()
    assert all(item["slaRisk"] == "ok" for item in ok["items"])


def test_phone_masking_keeps_last_three_digits(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate = add_candidate(
        sim_engine, restaurant_code="R002", state="contacted", phone="+346006001234"
    )
    detail = sim_client.get(f"/api/candidates/{candidate}").json()
    assert detail["phoneMasked"].endswith("234")
    assert "+346006001234" not in detail["phoneMasked"]
    assert "600600" not in detail["phoneMasked"].replace("•", "")


def test_detail_honest_empty_values_for_untracked_fields(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    detail = sim_client.get(f"/api/candidates/{driven['candidate_id']}").json()
    # No LLM agent loop exists yet (scripted backend): the agent version is an
    # explicit empty string, never an invented version.
    assert detail["agentVersion"] == ""
    # Candidates carry no surname in FirstShift (data minimization).
    assert detail["lastName"] == ""
    assert detail["summaryNote"] != ""
    # Documents are status rows only, never contents.
    for row in detail["summaryRows"]:
        assert len(row["value"]) < 120


def test_unknown_candidate_and_shift_owners_are_null_not_fabricated(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    detail = sim_client.get(f"/api/candidates/{driven['candidate_id']}").json()
    assert isinstance(detail["matchedShift"]["shiftIds"], list)
    # A D1 candidate matched to a shift must name a real seeded shift id.
    if detail["matchedShift"]["shiftIds"]:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.db.models import OpenShift

        with Session(_LAST_ENGINE) as session:
            found = session.scalar(
                select(OpenShift).where(
                    OpenShift.shiftgrid_shift_id.in_(detail["matchedShift"]["shiftIds"])
                )
            )
        assert found is not None, "matched shift ids must be real shiftgrid ids"


# Set by the autouse fixture below; the module's tests read the current
# throwaway engine through it instead of reaching into the test client.
_LAST_ENGINE: Engine | None = None


@pytest.fixture(autouse=True)
def _remember_engine(sim_engine: Engine) -> Iterator[None]:
    global _LAST_ENGINE
    _LAST_ENGINE = sim_engine
    yield


# ------------------------------------------------------------------- metrics


def test_funnel_counts_follow_the_event_log(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    funnel = sim_client.get("/api/metrics/funnel").json()
    assert funnel["pilotCandidates"] + funnel["controlCandidates"] >= 1
    assert funnel["insight"] != ""
    stage_ids = [stage["id"] for stage in funnel["stages"]]
    assert stage_ids[0] == "applied"
    applied = funnel["stages"][0]
    assert applied["pilotPct"] == 100.0


def test_funnel_empty_state_is_honest(sim_client: TestClient) -> None:
    funnel = sim_client.get("/api/metrics/funnel").json()
    assert funnel["pilotCandidates"] == 0
    assert funnel["controlCandidates"] == 0
    assert all(stage["pilotPct"] == 0 for stage in funnel["stages"])
    assert "no" in funnel["insight"].lower()


def test_kpi_day1_show_rate_computed_from_audit(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    # D1 ends with first_shift_worked after first_shift_scheduled: 100%.
    kpis = sim_client.get("/api/metrics/kpis").json()
    day1 = next(card for card in kpis if card["id"] == "day1_show_rate")
    assert day1["value"] == "100.0"
    assert day1["status"] == "on_target"


def test_kpi_empty_history_is_explicit(sim_client: TestClient) -> None:
    kpis = sim_client.get("/api/metrics/kpis").json()
    ttfps = next(card for card in kpis if card["id"] == "ttfps")
    assert ttfps["value"] == ""
    assert ttfps["trend"] == []
    assert "no" in ttfps["source"].lower() or "not" in ttfps["source"].lower()


def test_manager_minutes_per_hire_is_not_invented(sim_client: TestClient) -> None:
    kpis = sim_client.get("/api/metrics/kpis").json()
    manager = next(card for card in kpis if card["id"] == "manager_minutes_per_hire")
    assert manager["value"] == ""
    assert manager["baseline"] == ""


# ------------------------------------------------------- restaurants, shifts


def test_restaurants_list_reflects_seed(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    rows = sim_client.get("/api/restaurants").json()
    assert len(rows) >= 15  # 12 pilot + 3 control from the seed CSV
    codes = {row["code"] for row in rows}
    assert "R001" in codes
    bench_counts = {row["code"]: row["bench"] for row in rows}
    # The bench only operates in pilot sites (seed rule).
    assert all(value == 0 for code, value in bench_counts.items() if code in CONTROL_CODES)


CONTROL_CODES = {"R013", "R014", "R015"}


def test_restaurant_shifts_window_and_status(
    sim_client: TestClient, driven: dict[str, Any], restaurant_id: str
) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.models import Restaurant
    from app.db.seed import seed_open_shifts

    with sim_engine_for_test().begin() as conn:
        seed_open_shifts(conn)
    with Session(sim_engine_for_test()) as session:
        restaurant = session.scalar(
            select(Restaurant).where(Restaurant.id == restaurant_id)
        )
        assert restaurant is not None
    payload = sim_client.get(f"/api/restaurants/{restaurant_id}/shifts").json()
    assert payload["restaurant"]["code"] == restaurant.code
    statuses = {shift["status"] for shift in payload["shifts"]}
    assert statuses <= {"open", "matched", "filled", "cancelled"}


def sim_engine_for_test() -> Engine:
    assert _LAST_ENGINE is not None, "engine fixture did not run"
    return _LAST_ENGINE


# ----------------------------------------------------------- escalations, audit


def test_escalations_include_dlq_and_manager_pending(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    from app.db.models import OutboxMessage

    with Session(sim_engine) as session, session.begin():
        session.add(
            OutboxMessage(
                id=uuid4(),
                port="hiredesk",
                operation="update_stage",
                payload={
                    "hiredesk_application_id": "hd-dlq",
                    "stage": "offer",
                    "rejection_reason": None,
                    "decision_id": str(uuid4()),
                },
                idempotency_key=f"test/dlq/{uuid4()}",
                status="failed",
                last_error="hiredesk rejected stage update: 422 boom",
            )
        )
    items = sim_client.get("/api/escalations").json()
    kinds = {item["kind"] for item in items}
    assert "dlq" in kinds
    dlq = next(item for item in items if item["kind"] == "dlq")
    assert "422" in dlq["detail"]


def test_audit_search_by_text(sim_client: TestClient, driven: dict[str, Any]) -> None:
    everything = sim_client.get("/api/audit").json()
    assert everything["total"] >= 1
    # Search for a value that actually exists in the log (observed, not assumed):
    # every returned row must contain the query text.
    needle = everything["items"][0]["eventType"]
    payload = sim_client.get("/api/audit", params={"q": needle}).json()
    assert payload["total"] >= 1
    assert all(
        needle in json.dumps(row, default=str) for row in payload["items"]
    )
    assert payload["total"] <= everything["total"]


def test_audit_filter_by_candidate(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    from sqlalchemy import func, select

    from app.db.models import AuditEvent

    with Session(sim_engine) as session:
        expected = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.candidate_id == driven["candidate_id"])
        )
    assert expected is not None and expected >= 1
    payload = sim_client.get(
        "/api/audit", params={"candidateId": driven["candidate_id"]}
    ).json()
    assert payload["total"] == expected
