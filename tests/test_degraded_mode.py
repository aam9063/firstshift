"""F12 T2 (S4): degraded-mode gating, holding messages and trace propagation.

specs/06-integration-rollout.md section 2: "a degraded adapter pauses only the
flows that need it, and candidates get a holding message instead of silence",
and "Every candidate journey has a trace ID across messages, core transitions
and integration calls".

The flow -> required client system mapping is pure (app/core/degraded.py), so
the gating decision is deterministic and testable without a network. Fault
injection here is the injected adapter status map, toggled per test, never
ambient.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.core.state_machine import Actor, ActorKind
from app.db.events import Event, EventType
from app.db.models import Application, AuditEvent, Candidate, OutboxMessage, Restaurant
from app.ports.hiredesk import StageUpdate
from tests.test_db_models import fresh_migrated_schema

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="function")
def engine() -> Iterator[Engine]:
    # Function scope: the audit log is append-only (INV-5), so every test
    # needs a pristine schema.
    with fresh_migrated_schema() as eng:
        yield eng


@pytest.fixture(autouse=True)
def _reset_simulator_channel() -> None:
    simulator_channel.sent.clear()


def _seed_restaurant(engine: Engine) -> UUID:
    from app.db.seed import seed_restaurants

    with engine.begin() as conn:
        seed_restaurants(conn)
    with Session(engine) as session:
        return session.scalar(select(Restaurant.id).where(Restaurant.code == "R001"))


def _seed_application(
    engine: Engine,
    restaurant_id: UUID,
    *,
    state: str = "new",
    preferred_language: str = "es",
) -> tuple[UUID, UUID, str]:
    """A candidate + application row in the given state, like the webhook
    creates them, so tests start mid-flow without driving the whole path."""
    candidate_id = uuid4()
    application_id = uuid4()
    phone = f"+34600{uuid.uuid4().int % 100000000:08d}"
    with Session(engine) as session, session.begin():
        session.add(
            Candidate(
                id=candidate_id,
                brand_id="lumbre",
                first_name="Lucia",
                phone=phone,
                preferred_language=preferred_language,
                hiredesk_candidate_id=f"hdc-{candidate_id}",
                state=state,
                source="qr",
            )
        )
        session.flush()
        session.add(
            Application(
                id=application_id,
                candidate_id=candidate_id,
                restaurant_id=restaurant_id,
                hiredesk_application_id=f"hd-{application_id}",
                state=state,
                entered_at=NOW,
                state_changed_at=NOW,
            )
        )
    return application_id, candidate_id, phone


def _journey(
    engine: Engine,
    application_id: UUID,
    candidate_id: UUID,
    trace_id: str,
    adapter_statuses: dict[str, str] | None = None,
) -> object:
    from app.services.scripted import ScriptedJourney

    return ScriptedJourney(
        engine,
        application_id=application_id,
        candidate_id=candidate_id,
        trace_id=trace_id,
        adapter_statuses=adapter_statuses,
    )


def _application_state(engine: Engine, application_id: UUID) -> str:
    with Session(engine) as session:
        return str(
            session.scalar(select(Application.state).where(Application.id == application_id))
        )


def _events(engine: Engine, candidate_id: UUID) -> list[Event]:
    with Session(engine) as session:
        rows = session.scalars(
            select(Event).where(Event.candidate_id == candidate_id).order_by(Event.occurred_at)
        ).all()
        session.expunge_all()
        return list(rows)


def _audits(engine: Engine, application_id: UUID) -> list[AuditEvent]:
    with Session(engine) as session:
        rows = session.scalars(
            select(AuditEvent).where(AuditEvent.application_id == application_id)
        ).all()
        session.expunge_all()
        return list(rows)


class CountingHireDesk:
    """Counting fake implementing HireDeskPort for the relay in trace tests."""

    def __init__(self) -> None:
        self.calls: list[StageUpdate] = []

    def update_stage(self, payload: StageUpdate) -> None:
        self.calls.append(payload)


# ------------------------------------------------------- pure mapping (S4)


def test_flow_mapping_names_a_required_system_for_every_task_flow() -> None:
    """The pure mapping: first contact and reminders need the channel,
    tracker completion needs Nómina360, shift matching needs ShiftGrid and
    training enrollment needs LearnBite."""
    from app.core.degraded import FLOW_REQUIRED_SYSTEMS

    assert {
        "first_contact": {"whatsapp"},
        "reminder": {"whatsapp"},
        "tracker_completion": {"nomina360"},
        "shift_matching": {"shiftgrid"},
        "training_enrollment": {"learnbite"},
    } == FLOW_REQUIRED_SYSTEMS


def test_only_a_degraded_status_pauses_a_flow() -> None:
    """Deterministic gating rule: degraded pauses, ok and unknown never do
    (an unknown adapter is reported by the health endpoint, it does not
    silently silence candidates)."""
    from app.core.degraded import flow_paused

    assert flow_paused("first_contact", {"whatsapp": "degraded"}) == "whatsapp"
    assert flow_paused("first_contact", {"whatsapp": "ok"}) is None
    assert flow_paused("first_contact", {"whatsapp": "unknown"}) is None
    assert flow_paused("first_contact", {}) is None
    assert flow_paused("training_enrollment", {"learnbite": "degraded"}) == "learnbite"
    assert flow_paused("reminder", {"nomina360": "degraded"}) is None


def test_event_to_flow_mapping_covers_the_core_events_that_write() -> None:
    from app.core.degraded import pause_for_event

    assert pause_for_event("intake_processed", {"whatsapp": "degraded"}) == (
        "first_contact",
        "whatsapp",
    )
    assert pause_for_event("no_reply_nudge_1", {"whatsapp": "degraded"}) == (
        "reminder",
        "whatsapp",
    )
    assert pause_for_event("interview_reminder_24h", {"whatsapp": "degraded"}) == (
        "reminder",
        "whatsapp",
    )
    assert pause_for_event("tracker_completed", {"nomina360": "degraded"}) == (
        "tracker_completion",
        "nomina360",
    )
    assert pause_for_event("shift_fit_matched", {"shiftgrid": "degraded"}) == (
        "shift_matching",
        "shiftgrid",
    )
    assert pause_for_event("first_shift_picked", {"shiftgrid": "degraded"}) == (
        "shift_matching",
        "shiftgrid",
    )
    # Events outside every flow are never gated.
    assert pause_for_event("candidate_consents", {"whatsapp": "degraded"}) is None


# ------------------------------------------------- holding message behavior


def test_degraded_channel_pauses_first_contact_with_a_holding_message(
    engine: Engine,
) -> None:
    """The named fault path: the channel is degraded, so first contact pauses,
    the candidate receives a holding message from the versioned catalog
    instead of silence, and the pause is explained by an audit and escalation
    record."""
    from app.services.scripted import FlowPaused

    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, phone = _seed_application(engine, restaurant_id)
    trace_id = "trace-degraded-channel"
    journey = _journey(
        engine,
        application_id,
        candidate_id,
        trace_id,
        adapter_statuses={"whatsapp": "degraded"},
    )

    result = journey.apply(  # type: ignore[attr-defined]
        event="intake_processed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={"notice_version": "v1", "ai_disclosed": True, "language": "es"},
        now=NOW,
    )

    # The flow paused: no state transition happened.
    assert isinstance(result, FlowPaused)
    assert result.flow == "first_contact"
    assert result.required_system == "whatsapp"
    assert _application_state(engine, application_id) == "new"

    # The candidate got a holding message, not silence.
    holding = [m for m in simulator_channel.sent if m.recipient_ref == phone]
    assert len(holding) == 1
    assert holding[0].body == (
        "Estamos teniendo un problema tecnico con uno de nuestros sistemas: "
        "tu solicitud sigue abierta y te escribimos en cuanto podamos "
        "continuar. Gracias por tu paciencia."
    )
    assert holding[0].correlation_id == trace_id

    events = _events(engine, candidate_id)
    out_events = [e for e in events if e.type == EventType.MESSAGE_OUT.value]
    assert len(out_events) == 1
    assert out_events[0].payload["template"] == "holding"
    assert out_events[0].trace_id == trace_id
    escalations = [e for e in events if e.type == EventType.ESCALATION_CREATED.value]
    assert len(escalations) == 1
    assert escalations[0].payload["flow"] == "first_contact"
    assert escalations[0].payload["required_system"] == "whatsapp"
    assert escalations[0].trace_id == trace_id

    # The audit record explains why the flow paused (who, what, when, why).
    audits = _audits(engine, application_id)
    paused = [a for a in audits if a.event_type == "flow.paused"]
    assert len(paused) == 1
    assert paused[0].actor_type == "system"
    assert paused[0].payload["flow"] == "first_contact"
    assert paused[0].payload["required_system"] == "whatsapp"

    # The holding message is a confirmed outbox row (rule 4: observable write).
    with Session(engine) as session:
        row = session.scalars(
            select(OutboxMessage).where(OutboxMessage.related_entity_id == candidate_id)
        ).one()
    assert row.port == "whatsapp"
    assert row.status == "api_confirmed"
    assert row.payload["template"] == "holding"


def test_holding_message_copy_exists_in_the_three_catalog_languages() -> None:
    """The holding template is versioned catalog copy in es/pt/en (C-O4).

    It is resolved by the pause path through candidate_body(), not through
    the F09 whitelist (whose exact membership is pinned by
    tests/test_channel_body_guard.py and tests/test_language_copy.py).
    """
    from app.services.scripted import HOLDING_TEMPLATE, candidate_body

    assert HOLDING_TEMPLATE == "holding"
    bodies = {language: candidate_body("holding", language) for language in ("es", "pt", "en")}
    for language, body in bodies.items():
        assert body, f"missing holding copy for {language}"
    # Three catalog entries, not one fallback repeated.
    assert len(set(bodies.values())) == 3


def test_holding_message_follows_the_candidate_language(engine: Engine) -> None:
    from app.services.scripted import FlowPaused

    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, phone = _seed_application(
        engine, restaurant_id, preferred_language="pt"
    )
    journey = _journey(
        engine,
        application_id,
        candidate_id,
        "trace-degraded-pt",
        adapter_statuses={"whatsapp": "degraded"},
    )

    result = journey.apply(  # type: ignore[attr-defined]
        event="intake_processed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={"notice_version": "v1", "ai_disclosed": True, "language": "pt"},
        now=NOW,
    )

    assert isinstance(result, FlowPaused)
    holding = [m for m in simulator_channel.sent if m.recipient_ref == phone]
    assert len(holding) == 1
    assert holding[0].body == (
        "Estamos a ter um problema tecnico com um dos nossos sistemas: a tua "
        "candidatura continua aberta e escrevemos-te assim que pudermos "
        "continuar. Obrigado pela tua paciencia."
    )


def test_degraded_system_only_pauses_the_flows_that_need_it(engine: Engine) -> None:
    """Flows not needing the degraded system keep working: ShiftGrid down
    does not stop first contact."""
    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, _ = _seed_application(engine, restaurant_id)
    journey = _journey(
        engine,
        application_id,
        candidate_id,
        "trace-shiftgrid-degraded",
        adapter_statuses={"shiftgrid": "degraded"},
    )

    result = journey.apply(  # type: ignore[attr-defined]
        event="intake_processed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={"notice_version": "v1", "ai_disclosed": True, "language": "es"},
        now=NOW,
    )

    assert result.transitioned is True  # type: ignore[attr-defined]
    assert _application_state(engine, application_id) == "contacted"
    paused = [a for a in _audits(engine, application_id) if a.event_type == "flow.paused"]
    assert paused == []


def test_degraded_nomina_pauses_tracker_completion_but_not_other_flows(
    engine: Engine,
) -> None:
    """Tracker completion needs Nómina360: degraded Nómina360 pauses it in
    preboarding, while the same degraded map leaves flows that do not need
    Nómina360 (here, the candidate-facing reminder lane) working."""
    from app.services.scripted import FlowPaused

    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, _ = _seed_application(
        engine, restaurant_id, state="preboarding"
    )
    journey = _journey(
        engine,
        application_id,
        candidate_id,
        "trace-degraded-nomina",
        adapter_statuses={"nomina360": "degraded"},
    )

    result = journey.apply(  # type: ignore[attr-defined]
        event="tracker_completed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={},
        snapshot_updates={"documents_complete": True, "csv_confirmed": True},
        now=NOW,
    )

    assert isinstance(result, FlowPaused)
    assert result.flow == "tracker_completion"
    assert result.required_system == "nomina360"
    assert _application_state(engine, application_id) == "preboarding"

    # Control: a degraded system the flow does not need never pauses it.
    other_id, other_candidate, _ = _seed_application(
        engine, restaurant_id, state="preboarding"
    )
    healthy_for_tracker = _journey(
        engine,
        other_id,
        other_candidate,
        "trace-nomina-not-needed",
        adapter_statuses={"whatsapp": "degraded"},
    )
    control = healthy_for_tracker.apply(  # type: ignore[attr-defined]
        event="tracker_completed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={},
        snapshot_updates={"documents_complete": True, "csv_confirmed": True},
        now=NOW + timedelta(minutes=1),
    )
    assert control.transitioned is True  # type: ignore[attr-defined]
    assert _application_state(engine, other_id) == "ready_for_rota"


def test_no_statuses_means_no_gating(engine: Engine) -> None:
    """PRESERVE: without an injected status map the dispatch path behaves
    exactly as before (existing scripted journeys must be untouched)."""
    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, _ = _seed_application(engine, restaurant_id)
    journey = _journey(engine, application_id, candidate_id, "trace-no-gating")

    result = journey.apply(  # type: ignore[attr-defined]
        event="intake_processed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={"notice_version": "v1", "ai_disclosed": True, "language": "es"},
        now=NOW,
    )

    assert result.transitioned is True  # type: ignore[attr-defined]
    assert _application_state(engine, application_id) == "contacted"
    paused = [a for a in _audits(engine, application_id) if a.event_type == "flow.paused"]
    assert paused == []


# ----------------------------------------------------- trace propagation (S4)


def test_trace_id_propagates_across_messages_transitions_and_integration_writes(
    engine: Engine,
) -> None:
    """Every event of one candidate journey (message events, state
    transitions, integration.write events) carries the journey's trace id.
    The relay's integration.write events were the dropped link: they used the
    outbox row id instead of the journey trace."""
    from app.outbox.relay import relay_pending

    restaurant_id = _seed_restaurant(engine)
    application_id, candidate_id, _ = _seed_application(engine, restaurant_id, state="new")
    trace_id = "journey-trace-001"
    journey = _journey(engine, application_id, candidate_id, trace_id)

    journey.apply(  # type: ignore[attr-defined]
        event="intake_processed",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={"notice_version": "v1", "ai_disclosed": True, "language": "es"},
        now=NOW,
    )
    journey.apply(  # type: ignore[attr-defined]
        event="candidate_consents",
        actor=Actor(ActorKind.CANDIDATE, "candidate"),
        payload={"channel": "whatsapp", "language": "es"},
        now=NOW + timedelta(seconds=30),
    )
    journey.apply(  # type: ignore[attr-defined]
        event="screening_starts",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        now=NOW + timedelta(minutes=1),
    )
    journey.apply(  # type: ignore[attr-defined]
        event="shift_fit_matched",
        actor=Actor(ActorKind.SYSTEM, "firstshift"),
        payload={},
        snapshot_updates={"eligibility_ok": True, "shift_fit_ok": True},
        now=NOW + timedelta(minutes=2),
    )
    slot = NOW + timedelta(days=2)
    journey.apply(  # type: ignore[attr-defined]
        event="slot_selected",
        actor=Actor(ActorKind.CANDIDATE, "candidate"),
        payload={"slot": slot, "stage": "interview"},
        snapshot_updates={"manager_open_slots": (slot,)},
        now=NOW + timedelta(minutes=3),
    )

    # The stage update went to the outbox; the relay delivers it and records
    # the integration.write event.
    with Session(engine) as session:
        rows = session.scalars(
            select(OutboxMessage).where(
                OutboxMessage.port == "hiredesk", OutboxMessage.status == "pending"
            )
        ).all()
    assert len(rows) == 1
    result = relay_pending(engine, CountingHireDesk(), now=NOW + timedelta(minutes=2))
    assert result.delivered == 1

    events = _events(engine, candidate_id)
    types_seen = {e.type for e in events}
    assert EventType.MESSAGE_IN.value in types_seen
    assert EventType.MESSAGE_OUT.value in types_seen
    assert EventType.STATE_TRANSITION.value in types_seen
    assert EventType.INTEGRATION_WRITE.value in types_seen
    # Every link of the journey carries the same trace id.
    mismatched = [e for e in events if e.trace_id != trace_id]
    assert mismatched == [], (
        f"events dropped the journey trace id: "
        f"{[(e.type, e.trace_id) for e in mismatched]}"
    )
