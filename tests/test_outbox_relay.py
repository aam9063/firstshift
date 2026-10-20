"""T6 (S5): outbox relay worker writing a stage update back to the HireDesk
mock, idempotent.

Specs/04-prototype.md section 1.5: "Outbox table and relay worker writing a
stage update back to HireDesk mock, idempotent (test: relay the same message
twice, one write)." Retry and dead-letter semantics follow
design/integration-contracts.md (default retry policy: 5 attempts, exponential
backoff 1s, 4s, 16s, 60s; the write history is recorded per attempt).

The relay is called directly in tests (no Redis, no Celery); the HireDesk
adapter is injected against the HireDeskPort Protocol.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, OutboxMessage
from app.ports.hiredesk import StageUpdate
from tests.test_db_models import fresh_migrated_schema

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    with fresh_migrated_schema() as eng:
        yield eng


class CountingHireDesk:
    """Counting fake implementing HireDeskPort for relay unit tests."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.calls: list[StageUpdate] = []
        self.fail_with = fail_with

    def update_stage(self, payload: StageUpdate) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append(payload)


def _insert_outbox_row(
    engine: Engine,
    hiredesk_application_id: str,
    *,
    status: str = "pending",
    attempts: int = 0,
    next_retry_at: datetime | None = None,
) -> uuid.UUID:
    """One pending update_stage message for a fresh HireDesk application."""
    row_id = uuid.uuid4()
    payload = {
        "hiredesk_application_id": hiredesk_application_id,
        "stage": "screening",
        "rejection_reason": None,
        "decision_id": f"dec-{hiredesk_application_id}",
    }
    with Session(engine) as session, session.begin():
        session.add(
            OutboxMessage(
                id=row_id,
                port="hiredesk",
                operation="update_stage",
                payload=payload,
                idempotency_key=f"fs/hiredesk/update_stage/R001/{hiredesk_application_id}/{row_id}",
                status=status,
                attempts=attempts,
                next_retry_at=next_retry_at,
                related_entity_id=None,
            )
        )
    return row_id


def _get_row(engine: Engine, row_id: uuid.UUID) -> OutboxMessage:
    with Session(engine) as session:
        row = session.scalars(select(OutboxMessage).where(OutboxMessage.id == row_id)).one()
        session.expunge(row)
        return row


# --------------------------------------------------------------- idempotency


def test_relay_same_message_twice_performs_exactly_one_hiredesk_write(engine: Engine) -> None:
    """S5 named test: relay the same message twice, exactly one HireDesk write."""
    from app.outbox.relay import relay_pending

    row_id = _insert_outbox_row(engine, "hd-idem-001")
    hiredesk = CountingHireDesk()

    first = relay_pending(engine, hiredesk, now=NOW)
    second = relay_pending(engine, hiredesk, now=NOW)

    assert len(hiredesk.calls) == 1, "the same outbox message was delivered twice"
    delivered = hiredesk.calls[0]
    assert delivered.hiredesk_application_id == "hd-idem-001"
    assert delivered.stage == "screening"
    assert delivered.decision_id == "dec-hd-idem-001"

    assert first.delivered == 1
    assert second.delivered == 0

    row = _get_row(engine, row_id)
    assert row.status == "api_confirmed"  # the delivered state for async ports
    assert row.attempts == 1
    assert row.last_error is None
    assert row.next_retry_at is None


def test_two_sequential_relay_passes_cannot_double_deliver_same_row(engine: Engine) -> None:
    """Claim semantics: a claimed (relaying) row is invisible to later passes,
    and a delivered row never enters a second pass."""
    from app.outbox.relay import relay_pending

    delivered_id = _insert_outbox_row(engine, "hd-claim-001")
    in_flight_id = _insert_outbox_row(engine, "hd-claim-002", status="relaying")
    hiredesk = CountingHireDesk()

    relay_pending(engine, hiredesk, now=NOW)
    result = relay_pending(engine, hiredesk, now=NOW)

    assert len(hiredesk.calls) == 1
    assert hiredesk.calls[0].hiredesk_application_id == "hd-claim-001"

    assert result.claimed == 0, "a relaying (claimed) row was re-claimed by a later pass"
    # The in-flight row is untouched: a crashed worker's claim is not stolen.
    in_flight = _get_row(engine, in_flight_id)
    assert in_flight.status == "relaying"
    delivered = _get_row(engine, delivered_id)
    assert delivered.status == "api_confirmed"


# ----------------------------------------------------------- retry / backoff


def test_failed_delivery_schedules_backoff_retry_without_losing_message(engine: Engine) -> None:
    from app.outbox.relay import relay_pending

    row_id = _insert_outbox_row(engine, "hd-retry-001")
    failing = CountingHireDesk(fail_with=RuntimeError("hiredesk timeout"))

    first = relay_pending(engine, failing, now=NOW)
    assert first.delivered == 0
    assert first.retried == 1

    row = _get_row(engine, row_id)
    assert row.status == "pending", "a failed delivery must not lose the message"
    assert row.attempts == 1
    assert row.last_error == "hiredesk timeout"
    # Attempt 1 of the default policy retries after 1s (integration-contracts).
    assert row.next_retry_at == NOW + timedelta(seconds=1)

    # A pass before the backoff deadline does nothing; past it, attempt 2 runs
    # and schedules the next step of the exponential schedule (4s).
    early = relay_pending(engine, failing, now=NOW + timedelta(milliseconds=500))
    assert early.claimed == 0
    second = relay_pending(engine, failing, now=NOW + timedelta(seconds=2))
    assert second.retried == 1
    row = _get_row(engine, row_id)
    assert row.attempts == 2
    assert row.next_retry_at == NOW + timedelta(seconds=2) + timedelta(seconds=4)

    # The message survives and is delivered once the adapter recovers.
    recovered = CountingHireDesk()
    relay_pending(engine, recovered, now=NOW + timedelta(seconds=10))
    assert len(recovered.calls) == 1
    row = _get_row(engine, row_id)
    assert row.status == "api_confirmed"


def test_dead_letter_after_max_attempts(engine: Engine) -> None:
    from app.outbox.relay import MAX_ATTEMPTS, relay_pending

    row_id = _insert_outbox_row(engine, "hd-dead-001")
    failing = CountingHireDesk(fail_with=RuntimeError("hiredesk down"))

    now = NOW
    for expected_attempt in range(1, MAX_ATTEMPTS + 1):
        result = relay_pending(engine, failing, now=now)
        assert result.retried == (0 if expected_attempt == MAX_ATTEMPTS else 1)
        assert result.dead_lettered == (1 if expected_attempt == MAX_ATTEMPTS else 0)
        row = _get_row(engine, row_id)
        assert row.attempts == expected_attempt
        if expected_attempt < MAX_ATTEMPTS:
            assert row.status == "pending"
            now = row.next_retry_at

    row = _get_row(engine, row_id)
    assert row.status == "failed"
    assert row.attempts == MAX_ATTEMPTS
    assert row.next_retry_at is None
    assert row.last_error == "hiredesk down"

    # A dead-lettered message is never claimed again.
    after = relay_pending(engine, failing, now=now + timedelta(minutes=5))
    assert after.claimed == 0
    assert _get_row(engine, row_id).attempts == MAX_ATTEMPTS

    # The dead letter is recorded for IT in the append-only audit log (C-T6).
    with Session(engine) as session:
        audit = session.scalars(
            select(AuditEvent).where(
                AuditEvent.idempotency_key == _get_row(engine, row_id).idempotency_key
            )
        ).one()
    assert audit.actor_type == "system"
    assert audit.actor_id == "outbox.relay"
    assert audit.payload["attempts"] == MAX_ATTEMPTS


# ---------------------------------------------- integration through the mock


class MockHireDeskAdapter:
    """Adapter over the mocks HireDesk HTTP surface, the same contract
    app/adapters/hiredesk.py implements against the real (mock) API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def update_stage(self, payload: StageUpdate) -> None:
        # TestClient (sync) against the ASGI app: httpx.Client cannot use
        # ASGITransport (async-only), and entering the context manager would
        # run lifespan seeding, wiping the application under test.
        client = TestClient(_mocks_app())
        response = client.patch(
            f"/hiredesk/applications/{payload.hiredesk_application_id}/stage",
            json=payload.model_dump(exclude={"hiredesk_application_id"}),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"hiredesk rejected stage update: {response.status_code}")


def _mocks_app():
    from mocks.services.main import app

    return app


def test_relay_delivers_stage_update_to_hiredesk_mock(engine: Engine) -> None:
    """The relay drives the mock HireDesk stage PATCH endpoint end to end."""
    from mocks.services.routers import hiredesk as hiredesk_mock
    from mocks.services.seed import build_seed

    hiredesk_mock.store.reset(build_seed())
    with TestClient(_mocks_app()) as client:
        application = client.post(
            "/hiredesk/applications",
            json={"candidate_id": "hdc-0001", "restaurant_id": "R001"},
        ).json()

    from app.outbox.relay import relay_pending

    row_id = _insert_outbox_row(engine, application["application_id"])
    relay_pending(engine, MockHireDeskAdapter("http://mocks.test"), now=NOW)

    staged = next(
        app_row
        for app_row in hiredesk_mock.store.applications
        if app_row["application_id"] == application["application_id"]
    )
    assert staged["stage"] == "screening"
    assert staged["decision_id"] == f"dec-{application['application_id']}"
    assert _get_row(engine, row_id).status == "api_confirmed"
