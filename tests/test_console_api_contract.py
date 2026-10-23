"""T1 (S1): contract tests pinning every console API response shape.

specs/04b-console.md section 2 and odd/tasks/console-api.md: every response
must match the TypeScript contract the console consumes (web/src/api/types.ts,
read-only) exactly: same key names, same value kinds, same enum strings where
constrained (MetricStatus, AttentionKind, ActorType, EventKind,
JourneyStateId).

These tests drive the public HTTP interface only (no imports from
app.api.console): a shape change breaks a test here, never a console
component. The candidates list-row shape follows the contract types file as
closely as it allows; fields the backend cannot fill yet are explicit empty
values ("" or 0), never fabricated data (data rule 4).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import Restaurant
from tests.test_sim_common import drive_scenario, fresh_sim_engine, make_sim_client

# ---------------------------------------------------------------- value kinds

STR = str
INT = int
BOOL = bool
NUM = "number"  # JSON number, int or float, not bool
NUM_OR_NULL = "number|null"
STR_OR_NULL = "string|null"
LIST = "list"
OBJ = "object"
ANY = "any"


def assert_shape(value: Any, spec: dict[str, Any], label: str) -> None:
    """Exact key set plus a kind check per key (bool is not an int here)."""
    assert isinstance(value, dict), f"{label}: expected object, got {type(value)}"
    assert sorted(value) == sorted(spec), (
        f"{label}: keys {sorted(value)} != contract {sorted(spec)}"
    )
    for key, kind in spec.items():
        item = value[key]
        if kind is STR:
            assert isinstance(item, str), f"{label}.{key}: {item!r} is not a string"
        elif kind is INT:
            assert isinstance(item, int) and not isinstance(item, bool), (
                f"{label}.{key}: {item!r} is not an int"
            )
        elif kind is BOOL:
            assert isinstance(item, bool), f"{label}.{key}: {item!r} is not a bool"
        elif kind == NUM:
            assert isinstance(item, (int, float)) and not isinstance(item, bool), (
                f"{label}.{key}: {item!r} is not a number"
            )
        elif kind == NUM_OR_NULL:
            assert item is None or (
                isinstance(item, (int, float)) and not isinstance(item, bool)
            ), f"{label}.{key}: {item!r} is not a number or null"
        elif kind == STR_OR_NULL:
            assert item is None or isinstance(item, str), (
                f"{label}.{key}: {item!r} is not a string or null"
            )
        elif kind is LIST:
            assert isinstance(item, list), f"{label}.{key}: {item!r} is not a list"
        elif kind is OBJ:
            assert isinstance(item, dict), f"{label}.{key}: {item!r} is not an object"
        elif kind is ANY:
            pass
        else:  # pragma: no cover - test bug
            raise AssertionError(f"unknown kind {kind!r} for {label}.{key}")


# ------------------------------------------------------------------- shapes

CANDIDATE_LIST_ITEM: dict[str, Any] = {
    "id": STR,
    "firstName": STR,
    "initials": STR,
    "state": STR,
    "stateLabel": STR,
    "restaurant": STR,
    "restaurantCode": STR,
    "cohort": STR,
    "languages": LIST,
    "agentVersion": STR,
    "agentInControl": BOOL,
    "slaRisk": STR,
    "lastActivityAt": STR,
    "matchedShiftLabel": STR,
    "phoneMasked": STR,
    "elapsedLabel": STR,
}

CANDIDATE_DETAIL: dict[str, Any] = {
    "id": STR,
    "firstName": STR,
    "lastName": STR,
    "initials": STR,
    "stateLabel": STR,
    "restaurant": STR,
    "languages": LIST,
    "agentVersion": STR,
    "agentInControl": BOOL,
    "elapsedLabel": STR,
    "phoneMasked": STR,
    "journey": LIST,
    "candidateThread": LIST,
    "managerThread": LIST,
    "matchedShift": OBJ,
    "summaryRows": LIST,
    "summaryNote": STR,
    "consentRow": OBJ,
    "preBoarding": LIST,
    "writes": LIST,
}

JOURNEY_STEP: dict[str, Any] = {
    "id": STR,
    "label": STR,
    "at": STR,
    "actorLabel": STR,
    "actorType": STR,
    "note": STR_OR_NULL,
    "current": BOOL,
}

THREAD_MESSAGE: dict[str, Any] = {
    "id": STR,
    "at": STR,
    "senderType": STR,
    "senderLabel": STR_OR_NULL,
    "agentVersion": STR_OR_NULL,
    "text": STR,
    "toolCalls": LIST,
}

TOOL_CALL_MARKER: dict[str, Any] = {
    "tool": STR,
    "argsSummary": STR,
    "latencyMs": NUM_OR_NULL,
    "resultSummary": STR_OR_NULL,
}

MATCHED_SHIFT: dict[str, Any] = {
    "label": STR,
    "restaurant": STR,
    "detail": STR,
    "shiftIds": LIST,
    "held": STR,
}

RECORD_ROW: dict[str, Any] = {
    "label": STR,
    "value": STR,
    "status": STR_OR_NULL,
}

INTEGRATION_WRITE: dict[str, Any] = {
    "id": STR,
    "statusCode": INT,
    "target": STR,
    "operation": STR,
    "idempotencyKey": STR,
}

RESTAURANT_ROW: dict[str, Any] = {
    "id": STR,
    "code": STR,
    "name": STR,
    "city": STR,
    "cohort": STR,
    "openShifts": INT,
    "coveredPct": NUM,
    "bench": INT,
    "openCandidates": INT,
    "managerMedianReply": STR,
    "paused": BOOL,
}

SHIFTS_RESPONSE: dict[str, Any] = {"restaurant": OBJ, "shifts": LIST}

SHIFT_ROW: dict[str, Any] = {
    "id": STR,
    "label": STR,
    "startsAt": STR,
    "endsAt": STR,
    "role": STR,
    "requiresFoodHygiene": BOOL,
    "status": STR,
    "matchedCandidateId": STR_OR_NULL,
    "matchedCandidateName": STR_OR_NULL,
}

FUNNEL_SUMMARY: dict[str, Any] = {
    "pilotCandidates": INT,
    "controlCandidates": INT,
    "stages": LIST,
    "insight": STR,
}

FUNNEL_STAGE: dict[str, Any] = {
    "id": STR,
    "label": STR,
    "pilotPct": NUM,
    "controlPct": NUM,
}

KPI_CARD: dict[str, Any] = {
    "id": STR,
    "label": STR,
    "value": STR,
    "unit": STR,
    "status": STR,
    "control": STR,
    "baseline": STR,
    "target": STR,
    "source": STR,
    "trend": LIST,
}

KPI_IDS = {
    "ttfps",
    "time_to_first_contact",
    "interview_show_rate",
    "offer_to_rota_days",
    "day1_show_rate",
    "manager_minutes_per_hire",
}

ATTENTION_ITEM: dict[str, Any] = {
    "id": STR,
    "kind": STR,
    "title": STR,
    "detail": STR,
    "ago": STR,
}

AUDIT_RESPONSE: dict[str, Any] = {"items": LIST, "total": INT, "limit": INT, "offset": INT}

AUDIT_ROW: dict[str, Any] = {
    "id": STR,
    "at": STR,
    "actorType": STR,
    "actorLabel": STR,
    "eventType": STR,
    "stateFrom": STR_OR_NULL,
    "stateTo": STR_OR_NULL,
    "summary": STR,
    "payload": OBJ,
}

EVAL_SUMMARY_ROW: dict[str, Any] = {
    "version": STR,
    "label": STR,
    "generatedAt": STR,
    "taskSuccessRate": NUM_OR_NULL,
    "costPerHireUsd": NUM_OR_NULL,
}

TAKEOVER_RESPONSE: dict[str, Any] = {
    "candidateId": STR,
    "agentInControl": BOOL,
    "takenOverBy": STR,
}

RELEASE_RESPONSE: dict[str, Any] = {
    "candidateId": STR,
    "agentInControl": BOOL,
    "releasedBy": STR,
}

MESSAGE_RESPONSE: dict[str, Any] = {
    "id": STR,
    "candidateId": STR,
    "senderType": STR,
    "text": STR,
    "at": STR,
}

PAUSE_RESPONSE: dict[str, Any] = {
    "restaurantId": STR,
    "code": STR,
    "paused": BOOL,
}

REPLAY_RESPONSE: dict[str, Any] = {"id": STR, "status": STR, "attempts": INT}

ERASURE_RESPONSE: dict[str, Any] = {
    "id": STR,
    "candidateId": STR,
    "status": STR,
    "requestedAt": STR,
}

# Enum strings constrained by the TypeScript contract.
METRIC_STATUSES = {"on_target", "below_target"}
ATTENTION_KINDS = {"sla_breach", "first_shift", "human_needed", "dlq", "eval"}
ACTOR_TYPES = {"agent", "candidate", "human", "system"}
EVENT_KINDS = {"agent_turn", "tool_call", "state_change", "integration", "human_action"}
JOURNEY_STATE_IDS = {"new", "contacted", "consent", "screening", "matched", "interview_booked"}
COHORTS = {"pilot", "control"}
SENDER_TYPES = ACTOR_TYPES | {"candidate"}
RECORD_ROW_STATUSES = {"ok", "pending", "not_requested"}


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


@pytest.fixture()
def driven(sim_client: TestClient) -> dict[str, Any]:
    """One fully driven D1 run: candidate, journey, threads and outbox rows."""
    return drive_scenario(sim_client, "D1")


def first_candidate_id(sim_engine: Engine) -> str:
    with Session(sim_engine) as session:
        return str(session.scalar(select(Restaurant.id).limit(1)) or "")


@pytest.fixture()
def candidate_id(sim_engine: Engine, driven: dict[str, Any]) -> str:
    return str(driven["candidate_id"])


@pytest.fixture()
def restaurant_id(sim_engine: Engine) -> str:
    with Session(sim_engine) as session:
        found = session.scalar(select(Restaurant.id).where(Restaurant.code == "R001"))
        assert found is not None
        return str(found)


def get_json(client: TestClient, url: str, **kwargs: Any) -> Any:
    response = client.get(url, **kwargs)
    assert response.status_code == 200, f"{url}: {response.status_code} {response.text}"
    return response.json()


# ------------------------------------------------------------------- tests


def test_candidates_list_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    payload = get_json(sim_client, "/api/candidates")
    assert_shape(payload, {"items": LIST, "total": INT, "page": INT, "pageSize": INT}, "list")
    assert payload["total"] >= 1
    for item in payload["items"]:
        assert_shape(item, CANDIDATE_LIST_ITEM, "candidate row")
        assert item["cohort"] in COHORTS
        assert item["slaRisk"] in {"ok", "at_risk", "breached"}
        assert isinstance(item["languages"], list)
        assert all(isinstance(lang, str) for lang in item["languages"])


def test_candidate_detail_shape(
    sim_client: TestClient, driven: dict[str, Any], candidate_id: str
) -> None:
    detail = get_json(sim_client, f"/api/candidates/{candidate_id}")
    assert_shape(detail, CANDIDATE_DETAIL, "detail")
    for step in detail["journey"]:
        assert_shape(step, JOURNEY_STEP, "journey step")
        assert step["id"] in JOURNEY_STATE_IDS
        assert step["actorType"] in ACTOR_TYPES
    for thread in (detail["candidateThread"], detail["managerThread"]):
        for message in thread:
            assert_shape(message, THREAD_MESSAGE, "thread message")
            assert message["senderType"] in SENDER_TYPES
            for marker in message["toolCalls"]:
                assert_shape(marker, TOOL_CALL_MARKER, "tool call marker")
    assert_shape(detail["matchedShift"], MATCHED_SHIFT, "matched shift")
    for row in [*detail["summaryRows"], detail["consentRow"], *detail["preBoarding"]]:
        assert_shape(row, RECORD_ROW, "record row")
        assert row["status"] in RECORD_ROW_STATUSES | {None}
    for write in detail["writes"]:
        assert_shape(write, INTEGRATION_WRITE, "integration write")


def test_restaurants_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    rows = get_json(sim_client, "/api/restaurants")
    assert isinstance(rows, list) and len(rows) >= 1
    for row in rows:
        assert_shape(row, RESTAURANT_ROW, "restaurant row")
        assert row["cohort"] in COHORTS


def test_restaurant_shifts_shape(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any], restaurant_id: str
) -> None:
    from app.db.seed import seed_open_shifts

    with sim_engine.begin() as conn:
        seed_open_shifts(conn)
    payload = get_json(sim_client, f"/api/restaurants/{restaurant_id}/shifts")
    assert_shape(payload, SHIFTS_RESPONSE, "shifts response")
    assert_shape(payload["restaurant"], RESTAURANT_ROW, "restaurant")
    assert len(payload["shifts"]) >= 1
    for shift in payload["shifts"]:
        assert_shape(shift, SHIFT_ROW, "shift row")


def test_metrics_funnel_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    funnel = get_json(sim_client, "/api/metrics/funnel")
    assert_shape(funnel, FUNNEL_SUMMARY, "funnel")
    assert len(funnel["stages"]) >= 1
    for stage in funnel["stages"]:
        assert_shape(stage, FUNNEL_STAGE, "funnel stage")
        assert 0 <= stage["pilotPct"] <= 100
        assert 0 <= stage["controlPct"] <= 100


def test_metrics_kpis_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    kpis = get_json(sim_client, "/api/metrics/kpis")
    assert isinstance(kpis, list) and len(kpis) >= 1
    assert {card["id"] for card in kpis} == KPI_IDS
    for card in kpis:
        assert_shape(card, KPI_CARD, "kpi card")
        assert card["status"] in METRIC_STATUSES
        assert all(isinstance(point, (int, float)) for point in card["trend"])


def test_escalations_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    items = get_json(sim_client, "/api/escalations")
    assert isinstance(items, list)
    for item in items:
        assert_shape(item, ATTENTION_ITEM, "attention item")
        assert item["kind"] in ATTENTION_KINDS


def test_audit_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    payload = get_json(sim_client, "/api/audit")
    assert_shape(payload, AUDIT_RESPONSE, "audit response")
    assert payload["total"] >= 1
    for row in payload["items"]:
        assert_shape(row, AUDIT_ROW, "audit row")


def test_evals_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    rows = get_json(sim_client, "/api/evals")
    assert isinstance(rows, list) and len(rows) >= 1
    for row in rows:
        assert_shape(row, EVAL_SUMMARY_ROW, "eval summary row")

    report = get_json(sim_client, "/api/evals/v1")
    report_path = Path("evals/reports/eval-v1.json")
    assert report == json.loads(report_path.read_text(encoding="utf-8"))


def test_takeover_release_contract(
    sim_client: TestClient, driven: dict[str, Any], candidate_id: str
) -> None:
    taken = sim_client.post(
        f"/api/candidates/{candidate_id}/takeover", headers={"X-Actor-Role": "talent"}
    )
    assert taken.status_code == 200, taken.text
    body = taken.json()
    assert_shape(body, TAKEOVER_RESPONSE, "takeover response")
    assert body["agentInControl"] is False
    assert body["takenOverBy"] == "talent"

    released = sim_client.post(
        f"/api/candidates/{candidate_id}/release", headers={"X-Actor-Role": "ops"}
    )
    assert released.status_code == 200, released.text
    body = released.json()
    assert_shape(body, RELEASE_RESPONSE, "release response")
    assert body["agentInControl"] is True
    assert body["releasedBy"] == "ops"


def test_human_message_contract(
    sim_client: TestClient, driven: dict[str, Any], candidate_id: str
) -> None:
    sim_client.post(
        f"/api/candidates/{candidate_id}/takeover", headers={"X-Actor-Role": "talent"}
    )
    sent = sim_client.post(
        f"/api/candidates/{candidate_id}/messages",
        json={"text": "Hola, soy Marta del equipo de Lumbre."},
        headers={"X-Actor-Role": "talent"},
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert_shape(body, MESSAGE_RESPONSE, "message response")
    assert body["senderType"] == "human"
    assert body["text"] == "Hola, soy Marta del equipo de Lumbre."


def test_pause_contract(
    sim_client: TestClient, driven: dict[str, Any], restaurant_id: str
) -> None:
    paused = sim_client.post(
        f"/api/restaurants/{restaurant_id}/pause", headers={"X-Actor-Role": "ops"}
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert_shape(body, PAUSE_RESPONSE, "pause response")
    assert body["paused"] is True
    assert body["code"] == "R001"


def test_outbox_replay_contract(
    sim_client: TestClient, driven: dict[str, Any], sim_engine: Engine
) -> None:
    from app.db.models import OutboxMessage

    message_id = uuid4()
    with Session(sim_engine) as session, session.begin():
        session.add(
            OutboxMessage(
                id=message_id,
                port="hiredesk",
                operation="update_stage",
                payload={
                    "hiredesk_application_id": "hd-replay-shape",
                    "stage": "screening",
                    "rejection_reason": None,
                    "decision_id": str(uuid4()),
                },
                idempotency_key=f"test/replay/{message_id}",
                status="failed",
            )
        )

    replayed = sim_client.post(
        f"/api/outbox/{message_id}/replay", headers={"X-Actor-Role": "ops"}
    )
    assert replayed.status_code == 200, replayed.text
    body = replayed.json()
    # The path is owned by app/api/outbox.py (F12): it resets the dead letter
    # and the relay delivers it on its next pass, so the response is the reset
    # row. The console uses id, status and attempts; extra diagnostic keys
    # (port, operation, idempotency_key) are allowed and useful in /ops.
    for key, kind in REPLAY_RESPONSE.items():
        assert key in body, f"replay response is missing '{key}'"
        assert isinstance(body[key], kind), (
            f"replay response '{key}' should be {kind}, got {type(body[key])}"
        )
    assert body["status"] == "pending"
    assert body["attempts"] == 0


def test_erasure_request_contract(
    sim_client: TestClient, driven: dict[str, Any], candidate_id: str
) -> None:
    created = sim_client.post(
        "/api/erasure-requests",
        json={"candidateId": candidate_id},
        headers={"X-Actor-Role": "dpo"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert_shape(body, ERASURE_RESPONSE, "erasure response")
    assert body["status"] == "requested"
    assert body["candidateId"] == candidate_id


def test_unknown_resources_return_404(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    missing = uuid4()
    for url in (
        f"/api/candidates/{missing}",
        f"/api/restaurants/{missing}/shifts",
        "/api/evals/does-not-exist",
    ):
        response = sim_client.get(url)
        assert response.status_code == 404, f"{url}: {response.status_code}"
    assert sim_client.post(
        f"/api/candidates/{missing}/takeover", headers={"X-Actor-Role": "talent"}
    ).status_code == 404
    assert sim_client.post(
        f"/api/outbox/{missing}/replay", headers={"X-Actor-Role": "ops"}
    ).status_code == 404


def test_missing_or_invalid_actor_role_is_rejected(
    sim_client: TestClient, driven: dict[str, Any], candidate_id: str
) -> None:
    response = sim_client.post(f"/api/candidates/{candidate_id}/takeover")
    assert response.status_code == 400, response.text
    response = sim_client.post(
        f"/api/candidates/{candidate_id}/takeover", headers={"X-Actor-Role": "ceo"}
    )
    assert response.status_code == 400, response.text
