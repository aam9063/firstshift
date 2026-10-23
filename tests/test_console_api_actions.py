"""T6 (S5, rule 3): human actions are audited with the acting role.

specs/04b-console.md section 2 action rows and odd/tasks/console-api.md:
- POST /api/candidates/{id}/takeover makes agentInControl false for the
  candidate and release flips it back; every action is audited with the
  X-Actor-Role value (talent, dpo, ops) as the actor,
- messages sent during takeover are recorded as message.out events with the
  human sender type,
- POST /api/restaurants/{id}/pause pauses every agent for one restaurant,
- POST /api/outbox/{id}/replay reuses the existing relay logic
  (app/outbox/relay.py) on a dead-lettered row,
- POST /api/erasure-requests starts a GDPR erasure request.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.events import Event
from app.db.models import AuditEvent, OutboxMessage
from tests.test_sim_common import drive_scenario, fresh_sim_engine, make_sim_client


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


@pytest.fixture()
def driven(sim_client: TestClient) -> dict[str, Any]:
    return drive_scenario(sim_client, "D1")


def take_over(client: TestClient, candidate_id: str, role: str = "talent") -> httpx.Response:
    return client.post(
        f"/api/candidates/{candidate_id}/takeover", headers={"X-Actor-Role": role}
    )


# ---------------------------------------------------------------- takeover


def test_takeover_flips_agent_in_control(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    detail = sim_client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["agentInControl"] is True

    response = take_over(sim_client, candidate_id)
    assert response.status_code == 200
    detail = sim_client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["agentInControl"] is False

    release = sim_client.post(
        f"/api/candidates/{candidate_id}/release", headers={"X-Actor-Role": "talent"}
    )
    assert release.status_code == 200
    detail = sim_client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["agentInControl"] is True


def test_takeover_is_audited_with_the_role(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    take_over(sim_client, candidate_id, role="dpo")

    with Session(sim_engine) as session:
        row = session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.candidate_id == candidate_id,
                AuditEvent.event_type == "human_action.takeover",
            )
            .order_by(AuditEvent.occurred_at.desc())
            .limit(1)
        ).first()
    assert row is not None, "takeover must append an audit event"
    assert row.actor_id == "console:dpo"
    assert row.payload["role"] == "dpo"
    assert row.payload["action"] == "takeover"


def test_release_is_audited_with_the_role(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    take_over(sim_client, candidate_id)
    sim_client.post(
        f"/api/candidates/{candidate_id}/release", headers={"X-Actor-Role": "ops"}
    )
    with Session(sim_engine) as session:
        row = session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.candidate_id == candidate_id,
                AuditEvent.event_type == "human_action.release",
            )
            .order_by(AuditEvent.occurred_at.desc())
            .limit(1)
        ).first()
    assert row is not None
    assert row.actor_id == "console:ops"


# ---------------------------------------------------------------- messages


def test_human_message_requires_takeover(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    response = sim_client.post(
        f"/api/candidates/{candidate_id}/messages",
        json={"text": "Hola"},
        headers={"X-Actor-Role": "talent"},
    )
    assert response.status_code == 409
    with Session(sim_engine) as session:
        human_messages = session.scalars(
            select(Event).where(
                Event.candidate_id == candidate_id,
                Event.type == "message.out",
                Event.payload["sender_type"].astext == "human",
            )
        ).all()
    assert human_messages == [], "a rejected message must leave no message.out row"


def test_human_message_recorded_as_message_out_from_human(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    take_over(sim_client, candidate_id)
    sent = sim_client.post(
        f"/api/candidates/{candidate_id}/messages",
        json={"text": "Soy Marta de Lumbre, te ayudo con tu solicitud."},
        headers={"X-Actor-Role": "talent"},
    )
    assert sent.status_code == 201

    with Session(sim_engine) as session:
        row = session.scalars(
            select(Event)
            .where(
                Event.candidate_id == candidate_id,
                Event.type == "message.out",
                Event.payload["sender_type"].astext == "human",
            )
            .order_by(Event.occurred_at.desc())
            .limit(1)
        ).first()
    assert row is not None, "the human message must be a message.out event"
    assert row.payload["body"].startswith("Soy Marta de Lumbre")
    assert row.payload["role"] == "talent"

    detail = sim_client.get(f"/api/candidates/{candidate_id}").json()
    human_rows = [
        message
        for message in detail["candidateThread"]
        if message["senderType"] == "human"
    ]
    assert human_rows, "the human message must appear in the candidate thread"
    assert human_rows[-1]["text"].startswith("Soy Marta de Lumbre")


# ------------------------------------------------------------- restaurant pause


def test_pause_restaurant_audited_and_visible(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    from app.db.models import Restaurant

    with Session(sim_engine) as session:
        restaurant_id, code = session.execute(
            select(Restaurant.id, Restaurant.code).where(Restaurant.code == "R001")
        ).one()

    paused = sim_client.post(
        f"/api/restaurants/{restaurant_id}/pause", headers={"X-Actor-Role": "ops"}
    )
    assert paused.status_code == 200
    assert paused.json()["paused"] is True

    rows = sim_client.get("/api/restaurants").json()
    target = next(row for row in rows if row["code"] == code)
    assert target["paused"] is True
    others = [row for row in rows if row["code"] != code]
    assert all(row["paused"] is False for row in others)

    with Session(sim_engine) as session:
        event = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == "restaurant.paused")
            .order_by(AuditEvent.occurred_at.desc())
            .limit(1)
        ).first()
    assert event is not None
    assert event.payload["restaurant_code"] == code
    assert event.payload["role"] == "ops"


def test_pause_then_resume(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    from app.db.models import Restaurant

    with Session(sim_engine) as session:
        restaurant_id, _ = session.execute(
            select(Restaurant.id, Restaurant.code).where(Restaurant.code == "R001")
        ).one()
    sim_client.post(
        f"/api/restaurants/{restaurant_id}/pause", headers={"X-Actor-Role": "ops"}
    )
    resumed = sim_client.post(
        f"/api/restaurants/{restaurant_id}/pause",
        json={"resume": True},
        headers={"X-Actor-Role": "ops"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False
    rows = sim_client.get("/api/restaurants").json()
    assert all(row["paused"] is False for row in rows)


# ----------------------------------------------------------------- outbox replay
# The replay path is owned by app/api/outbox.py (F12). The console contract is
# the same endpoint, so these tests pin the shared semantics rather than a
# second implementation.


def _failed_outbox_row(engine: Engine, hiredesk_application_id: str) -> UUID:
    row_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            OutboxMessage(
                id=row_id,
                port="hiredesk",
                operation="update_stage",
                payload={
                    "hiredesk_application_id": hiredesk_application_id,
                    "stage": "interview",
                    "rejection_reason": None,
                    "decision_id": str(uuid4()),
                },
                idempotency_key=f"test/replay/{uuid4()}",
                status="failed",
                attempts=5,
                last_error="hiredesk rejected stage update: 500 exploded",
            )
        )
    return row_id


def test_replay_resets_a_dead_letter_to_pending_with_a_fresh_budget(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    row_id = _failed_outbox_row(sim_engine, "hd-replay-happy")

    response = sim_client.post(
        f"/api/outbox/{row_id}/replay", headers={"X-Actor-Role": "ops"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(row_id)
    assert body["status"] == "pending"
    assert body["attempts"] == 0

    with Session(sim_engine) as session:
        replayed = session.get(OutboxMessage, row_id)
        assert replayed is not None
        assert replayed.status == "pending"
        assert replayed.attempts == 0
        audit = session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.event_type.in_(
                    ["outbox.replay", "outbox.replay_requested"]
                ),
                AuditEvent.payload["outbox_id"].astext == str(row_id),
            )
            .limit(1)
        ).first()
    assert audit is not None, "a replay is a human action and must be audited"


def test_replay_rejects_rows_that_are_not_dead_letters(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    row_id = _failed_outbox_row(sim_engine, "hd-replay-reject")
    with Session(sim_engine) as session, session.begin():
        row = session.get(OutboxMessage, row_id)
        assert row is not None
        row.status = "api_confirmed"

    response = sim_client.post(
        f"/api/outbox/{row_id}/replay", headers={"X-Actor-Role": "ops"}
    )

    assert response.status_code == 409, response.text


# ------------------------------------------------------------------- erasure


def test_erasure_request_creates_audited_request(
    sim_client: TestClient, sim_engine: Engine, driven: dict[str, Any]
) -> None:
    candidate_id = str(driven["candidate_id"])
    response = sim_client.post(
        "/api/erasure-requests",
        json={"candidateId": candidate_id, "reason": "candidate asked by WhatsApp"},
        headers={"X-Actor-Role": "dpo"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["candidateId"] == candidate_id
    assert body["status"] == "requested"

    with Session(sim_engine) as session:
        event = session.get(AuditEvent, body["id"])
        assert event is not None, "the erasure request id is its audit event id"
        assert event.event_type == "erasure.requested"
        assert str(event.candidate_id) == candidate_id
        assert event.payload["role"] == "dpo"
        assert event.payload["reason"] == "candidate asked by WhatsApp"


def test_erasure_request_unknown_candidate_404(
    sim_client: TestClient, driven: dict[str, Any]
) -> None:
    response = sim_client.post(
        "/api/erasure-requests",
        json={"candidateId": str(uuid4())},
        headers={"X-Actor-Role": "dpo"},
    )
    assert response.status_code == 404
