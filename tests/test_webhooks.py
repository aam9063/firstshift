"""T5 (S3): HireDesk new-application webhook wiring.

specs/04-prototype.md section 1.3: HireDesk mock fires a "new application"
webhook, POST /webhooks/hiredesk creates the candidate in state new, and the
channel gateway sends the first scripted message to the simulator.

Covered here:
- First delivery creates Candidate + Application, dispatches the first
  contact (state.transition new -> contacted) and the message reaches the
  simulator channel adapter (GET /simulator/messages).
- A replayed identical delivery returns 200, creates nothing (dedup on the
  HireDesk application id; at-least-once delivery, S5 spirit).
- A malformed payload returns 422 and creates nothing.
- Dispatch effects are persisted: audit entry, message.in / state.transition
  / message.out events, and one outbox row with port whatsapp and the C-T5
  idempotency key scheme.

Tests run against a throwaway schema created by fresh_migrated_schema
(same pattern as tests/test_db_models.py); the FastAPI session dependency is
overridden with that engine's sessions.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.deps import get_session
from app.main import app
from tests.test_db_models import fresh_migrated_schema


def webhook_payload(**overrides: Any) -> dict[str, Any]:
    """The payload mocks/services/routers/hiredesk.py emits, verbatim shape."""
    payload: dict[str, Any] = {
        "event": "new_application",
        "event_id": "hd-evt-hd-app-000001",
        "application_id": "hd-app-000001",
        "candidate_id": "hdc-test-000001",
        "restaurant_id": "R001",
        "applied_at": datetime.now(UTC).isoformat(),
        "first_name": "Lucia",
        "phone": "+34600111222",
    }
    payload.update(overrides)
    return payload


@pytest.fixture(scope="function")
def migrated_engine() -> Iterator[Engine]:
    # Function scope: payloads reuse the same HireDesk application id across
    # tests on purpose, and audit rows cannot be deleted (append-only
    # triggers), so each test needs its own schema.
    with fresh_migrated_schema() as engine:
        yield engine


@pytest.fixture()
def client(migrated_engine: Engine) -> Iterator[TestClient]:
    from app.db.seed import seed_restaurants

    with migrated_engine.begin() as conn:
        seed_restaurants(conn)

    simulator_channel.sent.clear()

    def override_get_session() -> Iterator[Session]:
        # Same commit-on-success contract as app.api.deps.get_session.
        session = Session(migrated_engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def store_counts(engine: Engine) -> dict[str, int]:
    from app.db.events import Event
    from app.db.models import Application, AuditEvent, Candidate, OutboxMessage

    with Session(engine) as session:
        return {
            "candidates": session.scalar(select(func.count()).select_from(Candidate)) or 0,
            "applications": session.scalar(select(func.count()).select_from(Application)) or 0,
            "audit_events": session.scalar(select(func.count()).select_from(AuditEvent)) or 0,
            "events": session.scalar(select(func.count()).select_from(Event)) or 0,
            "outbox_messages": session.scalar(
                select(func.count()).select_from(OutboxMessage)
            ) or 0,
        }


def simulator_messages(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/simulator/messages")
    assert response.status_code == 200
    return response.json()


def test_first_delivery_creates_candidate_and_sends_first_message(
    client: TestClient, migrated_engine: Engine
) -> None:
    response = client.post("/webhooks/hiredesk", json=webhook_payload())

    assert response.status_code == 201
    body = response.json()
    candidate_id = body["candidate_id"]
    assert candidate_id

    from app.db.models import Application, Candidate

    with Session(migrated_engine) as session:
        candidate = session.scalars(
            select(Candidate).where(Candidate.id == __import__("uuid").UUID(candidate_id))
        ).one()
        application = session.scalars(select(Application)).one()

    # The row is created in new, then the first-contact dispatch moves it.
    assert application.state == "contacted"
    assert candidate.state == "contacted"
    assert candidate.hiredesk_candidate_id == "hdc-test-000001"
    assert candidate.first_name == "Lucia"

    # The channel gateway delivered the first message to the simulator.
    sent = simulator_messages(client)
    assert len(sent) == 1
    message = sent[0]
    assert message["recipient_ref"] == "+34600111222"
    assert "Lucia" in message["body"]
    # The first message carries the AI disclosure and the notice version
    # (guard first_message_discloses_ai, design row 2).
    assert "IA" in message["body"]
    assert "v1" in message["body"]


def test_replayed_delivery_returns_200_and_creates_nothing(
    client: TestClient, migrated_engine: Engine
) -> None:
    first = client.post("/webhooks/hiredesk", json=webhook_payload())
    assert first.status_code == 201
    before = store_counts(migrated_engine)
    messages_before = simulator_messages(client)

    second = client.post("/webhooks/hiredesk", json=webhook_payload())

    assert second.status_code == 200
    assert second.json()["status"] == "replayed"
    assert store_counts(migrated_engine) == before
    assert simulator_messages(client) == messages_before
    assert len(messages_before) == 1


def test_invalid_payload_returns_422_and_creates_nothing(
    client: TestClient, migrated_engine: Engine
) -> None:
    response = client.post("/webhooks/hiredesk", json={"event": "new_application"})

    assert response.status_code == 422
    assert store_counts(migrated_engine) == {
        "candidates": 0,
        "applications": 0,
        "audit_events": 0,
        "events": 0,
        "outbox_messages": 0,
    }
    assert simulator_messages(client) == []


def test_dispatch_effects_persisted(client: TestClient, migrated_engine: Engine) -> None:
    response = client.post("/webhooks/hiredesk", json=webhook_payload())
    assert response.status_code == 201
    candidate_id = response.json()["candidate_id"]

    from app.db.events import Event
    from app.db.models import AuditEvent, OutboxMessage

    with Session(migrated_engine) as session:
        # Audit (INV-5): the transition is recorded with who, what, when, why.
        audit = session.scalars(select(AuditEvent)).all()
        assert len(audit) == 1
        assert audit[0].event_type == "intake_processed"
        assert audit[0].state_from == "new"
        assert audit[0].state_to == "contacted"
        assert audit[0].actor_type == "system"
        assert str(audit[0].candidate_id) == candidate_id

        # Typed event stream (S6): message.in, state.transition, message.out.
        events = session.scalars(select(Event).order_by(Event.occurred_at)).all()
        assert sorted(e.type for e in events) == [
            "message.in",
            "message.out",
            "state.transition",
        ]
        message_out = next(e for e in events if e.type == "message.out")
        assert message_out.candidate_id is not None
        assert str(message_out.candidate_id) == candidate_id
        assert message_out.payload["body"]
        assert message_out.payload["recipient_ref"] == "+34600111222"
        transition = next(e for e in events if e.type == "state.transition")
        assert transition.payload["from_state"] == "new"
        assert transition.payload["to_state"] == "contacted"

        # Outbox (ADR-003): one row, port whatsapp, C-T5 key scheme.
        outbox = session.scalars(select(OutboxMessage)).all()
        assert len(outbox) == 1
        row = outbox[0]
        assert str(row.port) == "whatsapp"
        assert row.operation == "send"
        assert row.status == "api_confirmed"
        assert row.idempotency_key.startswith("fs/whatsapp/send/R001/")
        assert row.idempotency_key.endswith(str(row.id))
        assert str(row.related_entity_id) == candidate_id


def test_unknown_restaurant_is_rejected(client: TestClient, migrated_engine: Engine) -> None:
    response = client.post(
        "/webhooks/hiredesk", json=webhook_payload(restaurant_id="R999")
    )

    assert response.status_code == 404
    assert store_counts(migrated_engine)["candidates"] == 0
    assert simulator_messages(client) == []


def test_degraded_channel_pauses_first_contact(
    client: TestClient, migrated_engine: Engine
) -> None:
    """F12 S4: when the channel is degraded the candidate is created, the
    state does not advance, and the candidate gets the holding message from
    the catalog instead of silence."""
    from uuid import UUID

    from app.core.degraded import set_known_statuses
    from app.db.models import Application, AuditEvent, OutboxMessage

    set_known_statuses({"whatsapp": "degraded"})
    try:
        response = client.post(
            "/webhooks/hiredesk",
            json=webhook_payload(
                event_id="hd-evt-degraded-0001",
                application_id="hd-app-degraded-0001",
                candidate_id="hdc-degraded-0001",
            ),
        )
    finally:
        set_known_statuses(None)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "paused"
    assert body["paused_by"] == "whatsapp"

    with Session(migrated_engine) as session:
        application = session.get(Application, UUID(body["application_id"]))
        assert application is not None
        assert application.state == "new", "a paused first contact must not advance the state"
        holding = [
            row
            for row in session.scalars(select(OutboxMessage)).all()
            if row.payload.get("template") == "holding"
        ]
        assert holding, "no holding message was queued"
        assert holding[0].status == "api_confirmed"
        pauses = [
            row
            for row in session.scalars(select(AuditEvent)).all()
            if row.event_type == "flow.paused"
        ]
        assert pauses, "the pause was not audited"
        assert pauses[0].payload["required_system"] == "whatsapp"
