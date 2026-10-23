"""F12 T2 (S4): dead-letter queue visible and replayable.

specs/06-integration-rollout.md section 2: "Outbox with exponential backoff
and a dead-letter queue visible and replayable in the console".

GET /api/outbox?status=failed lists dead-lettered writes (id, port,
operation, attempts, last_error, idempotency_key). POST
/api/outbox/{id}/replay resets one row to pending with attempts 0 and hands
it back to the relay; replaying a non-failed row is a 409 with a clear
message. Both actions are audited with the actor role.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, OutboxMessage
from app.ports.hiredesk import StageUpdate
from tests.test_db_models import fresh_migrated_schema

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="function")
def engine() -> Iterator[Engine]:
    # Function scope: the audit log is append-only (INV-5), so every test
    # needs a pristine schema.
    with fresh_migrated_schema() as eng:
        yield eng


@pytest.fixture()
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _outbox_payload(hiredesk_application_id: str) -> dict[str, object]:
    return {
        "hiredesk_application_id": hiredesk_application_id,
        "stage": "screening",
        "rejection_reason": None,
        "decision_id": f"dec-{hiredesk_application_id}",
    }


def _insert_row(
    engine: Engine,
    *,
    status: str,
    attempts: int = 3,
    last_error: str | None = "hiredesk down",
) -> UUID:
    row_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            OutboxMessage(
                id=row_id,
                port="hiredesk",
                operation="update_stage",
                payload=_outbox_payload(f"hd-dlq-{row_id}"),
                idempotency_key=f"fs/hiredesk/update_stage/R001/hd-dlq-{row_id}/{row_id}",
                status=status,
                attempts=attempts,
                last_error=last_error,
                related_entity_id=None,
            )
        )
    return row_id


def _get_row(engine: Engine, row_id: UUID) -> OutboxMessage:
    with Session(engine) as session:
        row = session.scalars(select(OutboxMessage).where(OutboxMessage.id == row_id)).one()
        session.expunge(row)
        return row


def _audits(engine: Engine, event_type: str) -> list[AuditEvent]:
    with Session(engine) as session:
        rows = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == event_type)
        ).all()
        session.expunge_all()
        return list(rows)


# ----------------------------------------------------------------- listing


def test_list_failed_returns_the_dead_letter_fields(engine: Engine, client: TestClient) -> None:
    failed_id = _insert_row(engine, status="failed")
    _insert_row(engine, status="pending", attempts=0, last_error=None)

    response = client.get("/api/outbox", params={"status": "failed"})

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [m["id"] for m in messages] == [str(failed_id)]
    entry = messages[0]
    assert entry["port"] == "hiredesk"
    assert entry["operation"] == "update_stage"
    assert entry["attempts"] == 3
    assert entry["last_error"] == "hiredesk down"
    assert entry["idempotency_key"] == _get_row(engine, failed_id).idempotency_key


def test_list_supports_other_statuses_and_rejects_unknown_ones(
    engine: Engine, client: TestClient
) -> None:
    pending_id = _insert_row(engine, status="pending", attempts=0, last_error=None)
    _insert_row(engine, status="failed")

    response = client.get("/api/outbox", params={"status": "pending"})
    assert response.status_code == 200
    assert [m["id"] for m in response.json()["messages"]] == [str(pending_id)]

    unknown = client.get("/api/outbox", params={"status": "made_up"})
    assert unknown.status_code == 422


# ------------------------------------------------------------------- replay


def test_replay_resets_a_failed_row_to_pending_and_the_relay_delivers_it(
    engine: Engine, client: TestClient
) -> None:
    from app.outbox.relay import relay_pending

    class CountingHireDesk:
        def __init__(self) -> None:
            self.calls: list[StageUpdate] = []

        def update_stage(self, payload: StageUpdate) -> None:
            self.calls.append(payload)

    failed_id = _insert_row(engine, status="failed")

    response = client.post(
        f"/api/outbox/{failed_id}/replay", headers={"X-Actor-Role": "ops"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(failed_id)
    assert body["status"] == "pending"
    assert body["attempts"] == 0

    row = _get_row(engine, failed_id)
    assert row.status == "pending"
    assert row.attempts == 0
    assert row.next_retry_at is None

    # The row is back in the relay's hands: the next pass delivers it.
    relay = CountingHireDesk()
    result = relay_pending(engine, relay, now=NOW)
    assert result.delivered == 1
    assert len(relay.calls) == 1
    assert _get_row(engine, failed_id).status == "api_confirmed"


def test_replay_is_audited_with_the_actor_role(engine: Engine, client: TestClient) -> None:
    failed_id = _insert_row(engine, status="failed")

    response = client.post(
        f"/api/outbox/{failed_id}/replay", headers={"X-Actor-Role": "dpo"}
    )
    assert response.status_code == 200

    audits = _audits(engine, "outbox.replay_requested")
    assert len(audits) == 1
    audit = audits[0]
    assert audit.actor_id == "console:dpo"
    assert audit.payload["actor_role"] == "dpo"
    assert audit.payload["outbox_id"] == str(failed_id)
    assert audit.payload["port"] == "hiredesk"
    assert audit.payload["previous_status"] == "failed"
    assert audit.payload["previous_attempts"] == 3


def test_replay_without_a_role_header_defaults_to_ops(
    engine: Engine, client: TestClient
) -> None:
    failed_id = _insert_row(engine, status="failed")

    response = client.post(f"/api/outbox/{failed_id}/replay")
    assert response.status_code == 200

    audits = _audits(engine, "outbox.replay_requested")
    assert audits[0].payload["actor_role"] == "ops"


def test_replaying_a_non_failed_row_is_409_with_a_clear_message(
    engine: Engine, client: TestClient
) -> None:
    pending_id = _insert_row(engine, status="pending", attempts=1, last_error=None)

    response = client.post(f"/api/outbox/{pending_id}/replay")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "not dead-lettered" in detail
    assert "pending" in detail

    # The row is untouched: no reset, no relay hand-back.
    row = _get_row(engine, pending_id)
    assert row.status == "pending"
    assert row.attempts == 1
    assert _audits(engine, "outbox.replay_requested") == []


def test_replaying_an_unknown_row_is_404(client: TestClient) -> None:
    response = client.post(f"/api/outbox/{uuid.uuid4()}/replay")

    assert response.status_code == 404


def test_listing_is_audited_with_the_actor_role(engine: Engine, client: TestClient) -> None:
    _insert_row(engine, status="failed")

    response = client.get(
        "/api/outbox", params={"status": "failed"}, headers={"X-Actor-Role": "talent"}
    )
    assert response.status_code == 200

    audits = _audits(engine, "outbox.listed")
    assert len(audits) == 1
    assert audits[0].actor_id == "console:talent"
    assert audits[0].payload["actor_role"] == "talent"
    assert audits[0].payload["status"] == "failed"
    assert audits[0].payload["count"] == 1
