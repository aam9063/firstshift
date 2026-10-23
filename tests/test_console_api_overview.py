"""T4 extension (S1): GET /api/overview and GET /api/live.

These are the two composite endpoints the console needs to drop MSW. The
shapes are pinned to web/src/api/types.ts (OverviewResponse,
LiveFeedResponse) with the same exact-key-set style as
tests/test_console_api_contract.py, which provides the shared shape
primitives.

Honesty rules under test (data rule 4):
- without a simulator run the overview returns an honest empty/zero clock
  shape and the funnel insight says so (never a fabricated day),
- without agent turns the live health metrics are empty strings, not zeros,
- a guardrail family without measurable data is ok=True with a label that
  says "no data in window" (never a false alarm),
- activity and attention items map to real persisted rows, not synthetic
  strings.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.events import Event
from app.db.models import Application, AuditEvent, Candidate, OutboxMessage
from tests.test_console_api_contract import (
    ACTOR_TYPES,
    ATTENTION_ITEM,
    ATTENTION_KINDS,
    BOOL,
    COHORTS,
    FUNNEL_STAGE,
    FUNNEL_SUMMARY,
    INT,
    KPI_CARD,
    LIST,
    NUM,
    OBJ,
    STR,
    STR_OR_NULL,
    assert_shape,
)
from tests.test_sim_common import drive_scenario, fresh_sim_engine, make_sim_client

# ------------------------------------------------------------------- shapes

OVERVIEW_RESPONSE: dict[str, Any] = {
    "simClock": STR,
    "pilotDay": INT,
    "pilotDaysTotal": INT,
    "kpis": LIST,
    "funnel": OBJ,
    "attention": LIST,
    "activity": LIST,
    "coverage": LIST,
}

ACTIVITY_ITEM: dict[str, Any] = {
    "id": STR,
    "at": STR,
    "actorType": STR,
    "actorLabel": STR,
    "eventType": STR,
    "summary": STR,
    "detailTag": STR_OR_NULL,
}

COVERAGE_ROW: dict[str, Any] = {
    "id": STR,
    "restaurant": STR,
    "cohort": STR,
    "openShifts": INT,
    "coveredPct": NUM,
    "bench": INT,
    "managerReply": STR,
}

LIVE_FEED_RESPONSE: dict[str, Any] = {"health": OBJ, "guardrails": LIST, "agents": LIST}

LIVE_HEALTH: dict[str, Any] = {
    "windowLabel": STR,
    "p95ReplyLatency": STR,
    "schemaReasks": STR,
    "llmErrors": STR,
    "outboxInDlq": INT,
    "costPerHire": STR,
}

GUARDRAIL_ITEM: dict[str, Any] = {"id": STR, "ok": BOOL, "label": STR}

AGENT_INFO: dict[str, Any] = {"id": STR, "label": STR, "version": STR}

GUARDRAIL_FAMILIES = {
    "ai_disclosure",
    "tool_allow_list",
    "no_offer_without_approval",
    "protected_data",
    "outbound_language",
    "internal_identifiers",
}

# The expected prompt version per agent, read from the app/prompts filenames
# exactly the way the endpoint must (recruit.v1.md -> "v1").
EXPECTED_PROMPT_VERSIONS: dict[str, str] = {
    path.name.split(".", 1)[0]: path.stem.split(".", 1)[1]
    for path in sorted(Path("app/prompts").glob("*.v*.md"))
}


# ----------------------------------------------------------------- fixtures


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


@pytest.fixture()
def driven(sim_client: TestClient) -> dict[str, Any]:
    return drive_scenario(sim_client, "D1")


def get_json(client: TestClient, url: str) -> Any:
    response = client.get(url)
    assert response.status_code == 200, f"{url}: {response.status_code} {response.text}"
    return response.json()


# ----------------------------------------------------------------- overview


def test_overview_shape(sim_client: TestClient, driven: dict[str, Any]) -> None:
    payload = get_json(sim_client, "/api/overview")
    assert_shape(payload, OVERVIEW_RESPONSE, "overview")
    assert_shape(payload["funnel"], FUNNEL_SUMMARY, "funnel")
    for stage in payload["funnel"]["stages"]:
        assert_shape(stage, FUNNEL_STAGE, "funnel stage")
    assert len(payload["kpis"]) >= 1
    for card in payload["kpis"]:
        assert_shape(card, KPI_CARD, "kpi card")
    for item in payload["attention"]:
        assert_shape(item, ATTENTION_ITEM, "attention item")
        assert item["kind"] in ATTENTION_KINDS
    for item in payload["activity"]:
        assert_shape(item, ACTIVITY_ITEM, "activity item")
        assert item["actorType"] in ACTOR_TYPES
    assert len(payload["coverage"]) >= 1
    for row in payload["coverage"]:
        assert_shape(row, COVERAGE_ROW, "coverage row")
        assert row["cohort"] in COHORTS


def test_overview_clock_comes_from_the_sim_run(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    before = get_json(sim_client, "/api/overview")
    datetime.fromisoformat(before["simClock"])  # a real timestamp, parseable
    assert 1 <= before["pilotDay"] <= before["pilotDaysTotal"]
    assert before["pilotDaysTotal"] == 90  # the pilot design window

    advanced = sim_client.post("/api/sim/clock/advance", json={"days": 1})
    assert advanced.status_code == 200, advanced.text

    after = get_json(sim_client, "/api/overview")
    assert after["pilotDay"] == before["pilotDay"] + 1
    assert after["simClock"] > before["simClock"]


def test_overview_honest_without_sim_run(sim_client: TestClient) -> None:
    """No scenario loaded: zero-valued clock shape, empty activity, and the
    funnel insight says so instead of fabricating a day."""
    payload = get_json(sim_client, "/api/overview")
    assert payload["simClock"] == ""
    assert payload["pilotDay"] == 0
    assert payload["pilotDaysTotal"] == 0
    assert payload["activity"] == []
    assert "no simulator run" in payload["funnel"]["insight"].lower()
    for card in payload["kpis"]:
        assert card["value"] == ""
        assert card["trend"] == []


def test_overview_activity_maps_real_rows(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    payload = get_json(sim_client, "/api/overview")
    activity = payload["activity"]
    assert activity, "a driven run must produce activity"

    with Session(sim_engine) as session:
        audit_rows = {str(row.id): row for row in session.scalars(select(AuditEvent)).all()}
        event_rows = {str(row.id): row for row in session.scalars(select(Event)).all()}
    for item in activity:
        row = audit_rows.get(item["id"]) or event_rows.get(item["id"])
        assert row is not None, f"activity id {item['id']} is not a real persisted row"
        assert item["at"] == row.occurred_at.isoformat()
        expected_type = getattr(row, "event_type", None) or getattr(row, "type", "")
        assert item["eventType"] == expected_type
    # newest first
    assert [item["at"] for item in activity] == sorted(
        (item["at"] for item in activity), reverse=True
    )
    # a real message row surfaces with a human-readable summary
    outs = [item for item in activity if item["eventType"] == "message.out"]
    assert outs, "the driven run sent outbound messages"
    assert all(item["summary"] for item in outs)


def test_overview_attention_and_coverage_reuse_the_read_endpoints(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    payload = get_json(sim_client, "/api/overview")

    escalations = get_json(sim_client, "/api/escalations")
    assert payload["attention"] == escalations

    restaurants = {row["id"]: row for row in get_json(sim_client, "/api/restaurants")}
    assert {row["id"] for row in payload["coverage"]} == set(restaurants)
    for row in payload["coverage"]:
        source = restaurants[row["id"]]
        assert row["restaurant"] == source["name"]
        assert row["cohort"] == source["cohort"]
        assert row["openShifts"] == source["openShifts"]
        assert row["coveredPct"] == source["coveredPct"]
        assert row["bench"] == source["bench"]
        assert row["managerReply"] == source["managerMedianReply"]


# --------------------------------------------------------------------- live


def test_live_shape_and_honest_empty(sim_client: TestClient) -> None:
    """No run, no turns, no DLQ: every countable metric is an explicit empty
    string (never a fabricated zero) and every guardrail is a no-data pass."""
    payload = get_json(sim_client, "/api/live")
    assert_shape(payload, LIVE_FEED_RESPONSE, "live")

    health = payload["health"]
    assert_shape(health, LIVE_HEALTH, "health")
    assert health["windowLabel"] == "last 24 h"
    assert health["p95ReplyLatency"] == ""
    assert health["schemaReasks"] == ""
    assert health["llmErrors"] == ""
    assert health["outboxInDlq"] == 0
    assert health["costPerHire"] == ""

    by_id: dict[str, dict[str, Any]] = {}
    for item in payload["guardrails"]:
        assert_shape(item, GUARDRAIL_ITEM, "guardrail item")
        by_id[item["id"]] = item
    assert set(by_id) == GUARDRAIL_FAMILIES
    for item in by_id.values():
        assert item["ok"] is True
        assert "no data in window" in item["label"].lower()

    agents = payload["agents"]
    assert {agent["id"] for agent in agents} == {"recruit", "onboard", "pulse"}
    for agent in agents:
        assert_shape(agent, AGENT_INFO, "agent")
        assert agent["version"] == EXPECTED_PROMPT_VERSIONS[agent["id"]]
        assert agent["label"]


def test_live_health_counts_real_turns_and_dlq(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    """p95 latency, re-ask count, LLM error count, DLQ depth and cost per hire
    are computed from real agent.turn and outbox rows over the window."""

    def turn(
        *,
        latency_ms: float,
        retries: int,
        tokens_in: int,
        tokens_out: int,
        status: str = "ok",
    ) -> Event:
        return Event(
            id=uuid4(),
            type="agent.turn",
            occurred_at=datetime.now(UTC),
            candidate_id=UUID(driven["candidate_id"]),
            trace_id=str(driven["trace_id"]),
            payload={
                "agent": "recruit",
                "prompt_version": "v1",
                "model": "gpt-4.1-mini",
                "state": "screening",
                "status": status,
                "latency_ms": latency_ms,
                "tokens": {"input": tokens_in, "output": tokens_out},
                "validation_retries": retries,
            },
        )

    # gpt-4.1-mini: 0.40 USD/M input, 1.60 USD/M output -> 2.00 per turn,
    # 4.00 total, one hire -> costPerHire "4.00".
    with Session(sim_engine) as session, session.begin():
        session.add_all(
            [
                turn(latency_ms=100, retries=0, tokens_in=1_000_000, tokens_out=1_000_000),
                turn(latency_ms=300, retries=1, tokens_in=1_000_000, tokens_out=1_000_000),
            ]
        )
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=datetime.now(UTC),
                actor_type="system",
                actor_id="test",
                candidate_id=UUID(driven["candidate_id"]),
                application_id=UUID(driven["application_id"]),
                event_type="state.changed",
                state_to="offer_accepted",
                payload={},
            )
        )
        session.add(
            OutboxMessage(
                id=uuid4(),
                port="shiftgrid",
                operation="write_shift",
                payload={},
                idempotency_key=f"test/overview-dlq/{uuid4()}",
                status="failed",
            )
        )

    health = get_json(sim_client, "/api/live")["health"]
    assert health["p95ReplyLatency"] == "300 ms"  # nearest-rank p95 of 100/300
    assert health["schemaReasks"] == "1"
    assert health["llmErrors"] == "0"
    assert health["outboxInDlq"] == 1
    assert health["costPerHire"] == "4.00"


def test_live_health_counts_invalid_output_as_llm_error(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    with Session(sim_engine) as session, session.begin():
        session.add(
            Event(
                id=uuid4(),
                type="agent.turn",
                occurred_at=datetime.now(UTC),
                candidate_id=UUID(driven["candidate_id"]),
                trace_id=str(driven["trace_id"]),
                payload={
                    "agent": "recruit",
                    "prompt_version": "v1",
                    "model": "gpt-4.1-mini",
                    "state": "screening",
                    "status": "invalid_output",
                    "latency_ms": 50,
                    "tokens": {"input": 0, "output": 0},
                    "validation_retries": 0,
                },
            )
        )
    health = get_json(sim_client, "/api/live")["health"]
    assert health["llmErrors"] == "1"
    assert health["schemaReasks"] == "0"


def test_live_guardrail_flags_internal_identifier_leak(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    with Session(sim_engine) as session, session.begin():
        session.add(
            Event(
                id=uuid4(),
                type="message.out",
                occurred_at=datetime.now(UTC),
                candidate_id=UUID(driven["candidate_id"]),
                trace_id=str(driven["trace_id"]),
                payload={
                    "body": "Your backup contact is bench.reserve_backup, ok?",
                    "recipient_ref": "+34600000000",
                    "language": "es",
                },
            )
        )

    by_id = {
        item["id"]: item for item in get_json(sim_client, "/api/live")["guardrails"]
    }
    leak = by_id["internal_identifiers"]
    assert leak["ok"] is False
    assert "bench.reserve_backup" in leak["label"]
    # the run's real conversation keeps the other measurable families green
    assert by_id["ai_disclosure"]["ok"] is True
    assert "no data" not in by_id["ai_disclosure"]["label"].lower()
    assert by_id["outbound_language"]["ok"] is True
    assert "no data" not in by_id["outbound_language"]["label"].lower()


def test_live_guardrail_flags_offer_without_approval(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    with Session(sim_engine) as session, session.begin():
        application_id = session.scalar(
            select(Application.id).where(
                Application.candidate_id == UUID(driven["candidate_id"])
            )
        )
        assert application_id is not None
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=datetime.now(UTC),
                actor_type="system",
                actor_id="test",
                candidate_id=UUID(driven["candidate_id"]),
                application_id=application_id,
                event_type="state.changed",
                state_from="pending_manager_decision",
                state_to="offer_sent",
                payload={},
            )
        )

    by_id = {
        item["id"]: item for item in get_json(sim_client, "/api/live")["guardrails"]
    }
    offer = by_id["no_offer_without_approval"]
    assert offer["ok"] is False
    assert "approval" in offer["label"].lower()


def test_live_guardrail_flags_untagged_outbound_language(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    """After the candidate stated a language, a candidate-facing outbound
    without a language tag cannot be verified and fails the family."""
    candidate_id = UUID(driven["candidate_id"])
    with Session(sim_engine) as session:
        phone = session.scalar(select(Candidate.phone).where(Candidate.id == candidate_id))
        assert phone is not None
        # Place the untagged outbound after the candidate's real first
        # statement (the sim clock runs ahead of wall time in a driven run).
        stated_at = session.scalar(
            select(func.max(Event.occurred_at)).where(
                Event.candidate_id == candidate_id,
                Event.type == "message.in",
                Event.payload["text"].astext.is_not(None),
            )
        )
        assert stated_at is not None
    with Session(sim_engine) as session, session.begin():
        session.add(
            Event(
                id=uuid4(),
                type="message.out",
                occurred_at=stated_at + timedelta(seconds=1),
                candidate_id=candidate_id,
                trace_id=str(driven["trace_id"]),
                payload={"body": "Hola", "recipient_ref": phone},
            )
        )

    by_id = {
        item["id"]: item for item in get_json(sim_client, "/api/live")["guardrails"]
    }
    language = by_id["outbound_language"]
    assert language["ok"] is False
    assert "language tag" in language["label"].lower()
