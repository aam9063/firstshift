"""T7 (S7): Milestone A acceptance, specs/04-prototype.md section 1.

"Acceptance: uv run pytest green; a scripted candidate reaches
first_shift_scheduled in an integration test using only mocks; the audit log
shows every transition with actor."

One candidate drives the full happy path with no LLM:

1. POST /webhooks/hiredesk (TestClient against app.main.create_app) creates
   the candidate and sends the first scripted message (message.out + outbox
   row, port whatsapp).
2. The remaining candidate/manager/system events go through the same
   persisted dispatch path the webhook uses, via the thin
   app.services.scripted wrapper (loads the application, dispatches through
   StateMachine.dispatch with the right Actor, persists audit/events/outbox).
3. relay_pending delivers the HireDesk stage update through the real
   HireDeskAdapter pointed at the mocks app (localhost uvicorn): the mock
   shows the stage progressed, exactly once per idempotency key.

Tests run against a throwaway schema per test (fresh_migrated_schema); audit
rows are append-only, so state cannot be reused across tests.
"""

import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.deps import get_session
from app.core.state_machine import Actor, ActorKind
from app.main import app
from tests.test_db_models import fresh_migrated_schema

MOCKS_CANDIDATE_ID = "hdc-e2e-001"
MANAGER_ID = "mgr-yolanda-001"
NOTICE_VERSION = "v1"
EXPECTED_CHAIN = (
    "new",
    "contacted",
    "consented",
    "screening",
    "matched",
    "interview_booked",
    "interviewed",
    "pending_manager_decision",
    "offer_sent",
    "offer_accepted",
    "preboarding",
    "ready_for_rota",
    "first_shift_scheduled",
)


# --------------------------------------------------------------- fixtures


@dataclass
class Journey:
    """Ids and clock shared by the webhook and the scripted steps."""

    engine: Engine
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    trace_id: str


@pytest.fixture(scope="module")
def mocks_base_url() -> Iterator[str]:
    """The mocks app served on a localhost port for the real HireDeskAdapter.

    A thread-local uvicorn keeps the module-level mock stores in-process, so
    the relay test can assert on them directly after the adapter's HTTP
    writes. Only the relay test needs the server: the stage PATCH is the one
    write that leaves FirstShift.
    """
    from mocks.services.main import app as mocks_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]  # type: ignore[assignment]
    config = uvicorn.Config(mocks_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("mocks server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture(scope="function")
def engine() -> Iterator[Engine]:
    # Function scope: the audit log is append-only (INV-5), so every test
    # needs a pristine schema.
    with fresh_migrated_schema() as eng:
        yield eng


@pytest.fixture()
def client(engine: Engine) -> Iterator[TestClient]:
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ------------------------------------------------------------- journey


def _create_hiredesk_application(mocks_base_url: str, tag: str) -> str:
    """Create the application in the HireDesk mock so its stage PATCH exists."""
    from mocks.services.main import app as mocks_app

    with TestClient(mocks_app) as mocks_client:
        response = mocks_client.post(
            "/hiredesk/applications",
            json={"candidate_id": f"{MOCKS_CANDIDATE_ID}-{tag}", "restaurant_id": "R001"},
        )
    assert response.status_code == 200, response.text
    return str(response.json()["application_id"])


def _start_candidate(
    client: TestClient, engine: Engine, hiredesk_application_id: str, tag: str
) -> Journey:
    """Webhook delivery for a new application: the persisted entry point."""
    trace_id = f"e2e-trace-{tag}"
    response = client.post(
        "/webhooks/hiredesk",
        json={
            "event": "new_application",
            "event_id": trace_id,
            "application_id": hiredesk_application_id,
            "candidate_id": f"{MOCKS_CANDIDATE_ID}-{tag}",
            "restaurant_id": "R001",
            "first_name": "Lucia",
            "phone": "+34600111222",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return Journey(
        engine=engine,
        application_id=uuid.UUID(body["application_id"]),
        candidate_id=uuid.UUID(body["candidate_id"]),
        trace_id=trace_id,
    )


def _drive_journey(journey: Journey) -> None:
    """Every event after the webhook, through the persisted dispatch path."""
    from app.services.scripted import ScriptedJourney

    base = datetime.now(UTC)
    slot = base + timedelta(days=2, hours=4)
    first_shift_at = base + timedelta(days=6)

    scripted = ScriptedJourney(
        journey.engine,
        application_id=journey.application_id,
        candidate_id=journey.candidate_id,
        trace_id=journey.trace_id,
        notice_version=NOTICE_VERSION,
    )
    steps: list[tuple[str, Actor, dict[str, object], dict[str, object]]] = [
        (
            "candidate_consents",
            Actor(ActorKind.CANDIDATE, "candidate"),
            {"channel": "whatsapp", "language": "es"},
            {},
        ),
        ("screening_starts", Actor(ActorKind.SYSTEM, "firstshift"), {}, {}),
        (
            "shift_fit_matched",
            Actor(ActorKind.SYSTEM, "firstshift"),
            {},
            {"eligibility_ok": True, "shift_fit_ok": True},
        ),
        (
            "slot_selected",
            Actor(ActorKind.CANDIDATE, "candidate"),
            {"slot": slot, "stage": "interview"},
            {"manager_open_slots": (slot,)},
        ),
        ("interview_attended", Actor(ActorKind.CANDIDATE, "candidate"), {}, {}),
        ("decision_requested", Actor(ActorKind.SYSTEM, "firstshift"), {}, {}),
        (
            "approval_recorded",
            Actor(ActorKind.MANAGER, MANAGER_ID),
            {
                "approval": {
                    "manager_id": MANAGER_ID,
                    "manager_name": "Yolanda",
                    "decided_at": base + timedelta(days=1),
                    "facts_seen": "screening summary and shift fit evidence",
                }
            },
            {},
        ),
        ("offer_accepted", Actor(ActorKind.CANDIDATE, "candidate"), {}, {}),
        ("tracker_opened", Actor(ActorKind.SYSTEM, "firstshift"), {}, {}),
        (
            "tracker_completed",
            Actor(ActorKind.SYSTEM, "firstshift"),
            {},
            {"documents_complete": True, "csv_confirmed": True},
        ),
        (
            "first_shift_picked",
            Actor(ActorKind.MANAGER, MANAGER_ID),
            {"first_shift_at": first_shift_at},
            {"hygiene_module_complete": True},
        ),
    ]
    for offset, (event, actor, payload, snapshot_updates) in enumerate(steps, start=1):
        scripted.apply(
            event=event,
            actor=actor,
            payload=payload,
            snapshot_updates=snapshot_updates,
            now=base + timedelta(minutes=offset),
        )


# ------------------------------------------------------------- assertions


def _application_state(engine: Engine, application_id: uuid.UUID) -> str:
    from app.db.models import Application

    with Session(engine) as session:
        row = session.scalars(select(Application).where(Application.id == application_id)).one()
        session.expunge(row)
        return str(row.state)


def _candidate_state(engine: Engine, candidate_id: uuid.UUID) -> str:
    from app.db.models import Candidate

    with Session(engine) as session:
        row = session.scalars(select(Candidate).where(Candidate.id == candidate_id)).one()
        session.expunge(row)
        return str(row.state)


def _events(engine: Engine, trace_id: str) -> list[tuple[str, dict[str, object]]]:
    from app.db.events import Event

    with Session(engine) as session:
        rows = session.scalars(
            select(Event).where(Event.trace_id == trace_id).order_by(Event.occurred_at)
        ).all()
        return [(row.type, dict(row.payload)) for row in rows]


# ----------------------------------------------------------------- tests


def test_full_scripted_journey_reaches_first_shift_scheduled(
    client: TestClient, engine: Engine
) -> None:
    """Steps 1 to 2: webhook to first_shift_scheduled with only mocks."""

    journey = _start_candidate(client, engine, "hd-e2e-journey-001", "journey")

    # The webhook created the candidate and the first message went out.
    assert _application_state(engine, journey.application_id) == "contacted"
    assert len(simulator_channel.sent) == 1
    assert "IA" in simulator_channel.sent[0].body

    _drive_journey(journey)

    assert _application_state(engine, journey.application_id) == "first_shift_scheduled"
    assert _candidate_state(engine, journey.candidate_id) == "first_shift_scheduled"

    # Message flow: an inbound message precedes every outbound reply.
    events = _events(engine, journey.trace_id)
    types = {event_type for event_type, _ in events}
    assert "message.in" in types
    assert "message.out" in types


def test_audit_log_shows_every_transition_with_actor(
    client: TestClient, engine: Engine
) -> None:
    """S7 acceptance: the audit log shows every transition with actor."""
    from app.db.models import AuditEvent

    journey = _start_candidate(client, engine, "hd-e2e-audit-001", "audit")
    _drive_journey(journey)

    with Session(engine) as session:
        audit = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.application_id == journey.application_id)
            .order_by(AuditEvent.occurred_at)
        ).all()

    # One audit row per transition, in order, with who (actor_type, actor_id).
    chain = [(str(row.state_from), str(row.state_to)) for row in audit]
    # Pairwise (13 states produce 12 transitions; lengths differ by design).
    assert chain == list(zip(EXPECTED_CHAIN, EXPECTED_CHAIN[1:], strict=False))
    for row in audit:
        assert str(row.actor_type) in {"candidate", "manager", "system"}
        assert row.actor_id, "every audit row names its actor"
        assert row.occurred_at is not None
        assert row.event_type

    # Human decisions carry the named manager (C-L6, INV-1).
    approval = next(row for row in audit if row.event_type == "approval_recorded")
    assert str(approval.actor_type) == "manager"
    assert approval.actor_id == MANAGER_ID

    # The event stream mirrors the audit chain: one state.transition event
    # per transition, all on the same trace_id (rule 7, S6).
    events = _events(engine, journey.trace_id)
    transitions = [payload for event_type, payload in events if event_type == "state.transition"]
    assert len(transitions) == len(EXPECTED_CHAIN) - 1
    event_chain = [
        (str(payload["from_state"]), str(payload["to_state"])) for payload in transitions
    ]
    assert event_chain == chain


def test_relay_delivers_stage_update_exactly_once_per_idempotency_key(
    client: TestClient, engine: Engine, mocks_base_url: str
) -> None:
    """Step 3: the real HireDeskAdapter writes the stage to the mock, once."""
    import httpx

    from app.adapters.hiredesk import HireDeskAdapter
    from app.db.events import Event
    from app.db.models import OutboxMessage
    from app.outbox.relay import relay_pending
    from mocks.services.routers import hiredesk as hiredesk_mock

    hiredesk_application_id = _create_hiredesk_application(mocks_base_url, "relay")
    journey = _start_candidate(client, engine, hiredesk_application_id, "relay")
    _drive_journey(journey)

    with Session(engine) as session:
        rows = session.scalars(
            select(OutboxMessage).where(
                OutboxMessage.port == "hiredesk",
                OutboxMessage.status == "pending",
            )
        ).all()
    assert len(rows) == 1, "slot_selected queued exactly one HireDesk stage update"
    key = rows[0].idempotency_key
    decision_id = rows[0].payload["decision_id"]

    adapter = HireDeskAdapter(
        mocks_base_url,
        client=httpx.Client(base_url=mocks_base_url, timeout=10.0, trust_env=False),
    )
    first = relay_pending(engine, adapter)
    second = relay_pending(engine, adapter)

    assert first.delivered == 1
    assert second.claimed == 0, "a delivered row is never claimed again"
    assert second.delivered == 0

    with Session(engine) as session:
        delivered = session.get(OutboxMessage, rows[0].id)
        assert delivered is not None
        assert str(delivered.status) == "api_confirmed"
        assert delivered.attempts == 1

    staged = next(
        app_row
        for app_row in hiredesk_mock.store.applications
        if app_row["application_id"] == hiredesk_application_id
    )
    assert staged["stage"] == "interview"
    assert staged["decision_id"] == decision_id

    # Exactly one delivered integration.write event per idempotency key.
    with Session(engine) as session:
        writes = session.scalars(select(Event).where(Event.type == "integration.write")).all()
    per_key = [
        event
        for event in writes
        if event.payload.get("idempotency_key") == key
        and event.payload.get("outcome") == "delivered"
    ]
    assert len(per_key) == 1
