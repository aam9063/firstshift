"""T1 (S3, S5, S6): POST /webhooks/whatsapp, the Twilio sandbox inbound path.

Covered here:
- A validly signed form-encoded message from a known candidate phone is
  processed: message.in persisted with the body text and the scripted
  sandbox reply queued through the outbox whatsapp port.
- An invalid X-Twilio-Signature is rejected with 403 before any effect
  (S5: validate before processing).
- A replayed MessageSid returns 200 "replayed" and creates nothing (S3:
  inbound idempotency on the provider message id).
- An unknown phone gets a polite holding reply and an unmatched_inbound
  event, never a new candidate (S6: candidate creation stays behind the
  HireDesk webhook).
- A consent keyword dispatches candidate_consents through the state
  machine on the same persisted path as sim messages: audit row, typed
  events, Consent row and the state mirror.

Tests run against a throwaway schema created by fresh_migrated_schema and
monkeypatch the Twilio settings, so the in-process simulator adapter stays
selected and no test traffic reaches Twilio.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.adapters.simulator import channel as simulator_channel
from app.api.deps import get_session
from app.main import app
from app.settings import settings
from tests.test_db_models import fresh_migrated_schema

TEST_AUTH_TOKEN = "test-auth-token-1234567890abcdef"
WEBHOOK_PATH = "/webhooks/whatsapp"


@pytest.fixture(scope="function")
def migrated_engine() -> Iterator[Engine]:
    # Function scope like tests/test_webhooks.py: append-only audit rows and
    # events cannot be deleted, so every test needs its own schema.
    with fresh_migrated_schema() as engine:
        yield engine


@pytest.fixture()
def client(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from app.db.seed import seed_restaurants

    with migrated_engine.begin() as conn:
        seed_restaurants(conn)

    # Deterministic Twilio settings for the sandbox path: a known signing
    # token, validation on the default (enabled because a token exists) and
    # no REST credentials, so the simulator adapter stays selected and no
    # test traffic can reach Twilio.
    monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)
    monkeypatch.setattr(settings, "twilio_validate_signature", None)
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_api_key_sid", None)
    monkeypatch.setattr(settings, "twilio_api_key_secret", None)

    simulator_channel.sent.clear()

    def override_get_session() -> Iterator[Session]:
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


def signed_post(
    client: TestClient, params: dict[str, str], signature: str | None = None
) -> Any:
    """POST the form params with a signature computed by the same validator
    the endpoint uses (known-vector style: the HMAC over the exact URL and
    params the app reconstructs)."""
    if signature is None:
        validator = RequestValidator(TEST_AUTH_TOKEN)
        signature = validator.compute_signature(
            f"http://testserver{WEBHOOK_PATH}", params
        )
    headers = {} if signature is None else {"X-Twilio-Signature": signature}
    return client.post(WEBHOOK_PATH, data=params, headers=headers)


def twilio_params(**overrides: Any) -> dict[str, str]:
    params: dict[str, str] = {
        "MessageSid": f"SM{uuid4().hex[:24]}",
        "From": "whatsapp:+34600111222",
        "To": "whatsapp:+14155238886",
        "Body": "Hola",
        "ProfileName": "Lucia",
    }
    params.update(overrides)
    return params


def seed_contacted_candidate(client: TestClient, phone: str) -> str:
    """One candidate in contacted through the real HireDesk webhook path."""
    response = client.post(
        "/webhooks/hiredesk",
        json={
            "event": "new_application",
            "event_id": f"hd-evt-{uuid4().hex[:10]}",
            "application_id": f"hd-app-{uuid4().hex[:10]}",
            "candidate_id": f"hdc-{uuid4().hex[:10]}",
            "restaurant_id": "R001",
            "first_name": "Lucia",
            "phone": phone,
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def wa_events(engine: Engine, trace_id: str) -> list[tuple[str, dict[str, Any]]]:
    from app.db.events import Event

    with Session(engine) as session:
        rows = session.scalars(
            select(Event).where(Event.trace_id == trace_id)
        ).all()
        return [(row.type, dict(row.payload)) for row in rows]


def count(engine: Engine, model: Any) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_valid_signed_message_is_processed(
    client: TestClient, migrated_engine: Engine
) -> None:
    candidate_id = seed_contacted_candidate(client, "+34600111222")
    params = twilio_params(Body="Hola, tengo una duda")

    response = signed_post(client, params)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["candidate_id"] == candidate_id
    assert body["event"] is None  # free text: recorded, nothing dispatched

    # The message.in event carries the body text and the provider id (S3).
    events = wa_events(migrated_engine, f"wa-{params['MessageSid']}")
    assert [event_type for event_type, _ in events] == ["message.in"]
    payload = events[0][1]
    assert payload["channel"] == "whatsapp"
    assert payload["text"] == "Hola, tengo una duda"
    assert payload["provider_message_id"] == params["MessageSid"]
    assert payload["from"] == "+34600111222"

    # The scripted reply is queued through the outbox whatsapp port.
    from app.db.models import OutboxMessage

    with Session(migrated_engine) as session:
        rows = session.scalars(select(OutboxMessage)).all()
    replies = [
        row
        for row in rows
        if row.payload.get("correlation_id") == f"wa-{params['MessageSid']}"
    ]
    assert len(replies) == 1
    assert replies[0].port == "whatsapp"
    assert replies[0].operation == "send"
    assert "IA" in replies[0].payload["body"]  # S4: the reply discloses AI
    # No candidate or application was created by this message (S6).
    from app.db.models import Application, Candidate

    assert count(migrated_engine, Candidate) == 1
    assert count(migrated_engine, Application) == 1


def test_invalid_signature_is_rejected_with_403(
    client: TestClient, migrated_engine: Engine
) -> None:
    seed_contacted_candidate(client, "+34600111222")
    params = twilio_params()
    before_messages = list(simulator_channel.sent)
    from app.db.models import OutboxMessage

    outbox_before = count(migrated_engine, OutboxMessage)

    response = client.post(
        WEBHOOK_PATH, data=params, headers={"X-Twilio-Signature": "bad-signature"}
    )

    assert response.status_code == 403
    # Nothing was processed: no message.in, no outbox row, no channel send.
    assert wa_events(migrated_engine, f"wa-{params['MessageSid']}") == []
    assert list(simulator_channel.sent) == before_messages

    assert count(migrated_engine, OutboxMessage) == outbox_before


def test_replayed_message_sid_is_a_no_op(
    client: TestClient, migrated_engine: Engine
) -> None:
    seed_contacted_candidate(client, "+34600111222")
    params = twilio_params()
    first = signed_post(client, params)
    assert first.status_code == 200
    events_after_first = wa_events(migrated_engine, f"wa-{params['MessageSid']}")
    from app.db.events import Event
    from app.db.models import OutboxMessage

    outbox_after_first = count(migrated_engine, OutboxMessage)
    events_total_after_first = count(migrated_engine, Event)
    sent_after_first = len(simulator_channel.sent)

    second = signed_post(client, params)

    assert second.status_code == 200
    assert second.json()["status"] == "replayed"
    assert count(migrated_engine, OutboxMessage) == outbox_after_first
    assert count(migrated_engine, Event) == events_total_after_first
    assert wa_events(migrated_engine, f"wa-{params['MessageSid']}") == events_after_first
    assert len(simulator_channel.sent) == sent_after_first  # no second reply sent


def test_unknown_phone_gets_holding_reply_and_unmatched_event(
    client: TestClient, migrated_engine: Engine
) -> None:
    params = twilio_params(From="whatsapp:+34699999999", Body="Buenas")

    response = signed_post(client, params)

    assert response.status_code == 200
    assert response.json()["status"] == "unmatched_inbound"

    # S6: never a new candidate from an inbound message.
    from app.db.models import Candidate

    assert count(migrated_engine, Candidate) == 0

    # The unmatched arrival is observable (rule 7): one unmatched_inbound
    # event without the body text (data minimization for an unknown sender).
    from app.db.events import Event

    with Session(migrated_engine) as session:
        unmatched = session.scalars(
            select(Event).where(Event.type == "unmatched.inbound")
        ).all()
    assert len(unmatched) == 1
    assert unmatched[0].payload["provider_message_id"] == params["MessageSid"]
    assert unmatched[0].payload["from"] == "+34699999999"

    # S3: a replayed delivery of the same MessageSid is a no-op, even on the
    # unmatched path (the holding reply must not repeat either).
    replay = signed_post(client, params)
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    with Session(migrated_engine) as session:
        unmatched = session.scalars(
            select(Event).where(Event.type == "unmatched.inbound")
        ).all()
    assert len(unmatched) == 1
    assert "text" not in unmatched[0].payload

    # A polite holding reply is queued through the whatsapp port.
    from app.db.models import OutboxMessage

    with Session(migrated_engine) as session:
        rows = session.scalars(select(OutboxMessage)).all()
    assert len(rows) == 1
    assert rows[0].port == "whatsapp"
    assert rows[0].payload["recipient_ref"] == "+34699999999"
    assert "IA" in rows[0].payload["body"]
    assert rows[0].related_entity_id is None
    assert len(simulator_channel.sent) == 1


def test_consent_keyword_dispatches_through_the_state_machine(
    client: TestClient, migrated_engine: Engine
) -> None:
    candidate_id = seed_contacted_candidate(client, "+34600111222")
    params = twilio_params(Body="Sí")

    response = signed_post(client, params)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["event"] == "candidate_consents"

    from app.db.events import Event
    from app.db.models import Application, AuditEvent, Candidate, Consent

    with Session(migrated_engine) as session:
        candidate = session.get(Candidate, UUID(candidate_id))
        assert candidate is not None
        assert candidate.state == "consented"
        application = session.scalars(select(Application)).one()
        assert application.state == "consented"  # mirror rule

        # Dispatch effects on the persisted path: audit entry (INV-5) and
        # typed events (message.in first, then state.transition).
        audit = session.scalars(select(AuditEvent)).all()
        consent_audits = [a for a in audit if a.event_type == "candidate_consents"]
        assert len(consent_audits) == 1
        assert consent_audits[0].actor_type == "candidate"
        assert consent_audits[0].state_from == "contacted"
        assert consent_audits[0].state_to == "consented"
        folded = consent_audits[0].payload["folded_events"]
        assert any(e["type"] == "consent.recorded" for e in folded)

        trace = f"wa-{params['MessageSid']}"
        events = session.scalars(
            select(Event).where(Event.trace_id == trace)
        ).all()
        assert sorted(e.type for e in events) == ["message.in", "state.transition"]

        # Consent is captured with channel, notice version and timestamp.
        consents = session.scalars(select(Consent)).all()
        assert len(consents) == 1
        assert consents[0].channel == "whatsapp"
        assert consents[0].purpose == "screening"
        assert consents[0].notice_version == "v1"
        assert consents[0].granted_at is not None


def test_validation_can_be_disabled_explicitly(
    client: TestClient, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "twilio_validate_signature", False)
    seed_contacted_candidate(client, "+34600111222")
    params = twilio_params()

    response = client.post(WEBHOOK_PATH, data=params)  # no signature header

    assert response.status_code == 200
    assert response.json()["status"] == "processed"


def test_missing_form_fields_rejected(client: TestClient) -> None:
    response = signed_post(client, {"MessageSid": "SM-only"})

    assert response.status_code == 400
