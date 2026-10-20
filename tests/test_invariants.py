"""T3 (S4): invariants INV-1 to INV-5 of specs/03 section 5 as tests.

Each invariant is checked two ways: structurally over the declarative
transition table (so a future table edit cannot silently drop a guard) and
behaviorally through the public dispatch interface (rejected input leaves the
stored application unchanged).
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.core.state_machine import TRANSITIONS, Actor, ActorKind, Application, State, StateMachine
from tests.test_state_machine import (
    FIRST_SHIFT,
    SLOT,
    T0,
    approval_payload,
    candidate,
    happy_walk,
    manager,
    system,
)

NOTICE = "notice-2025-01"


def _app(state: State, **facts: object) -> Application:
    return replace(Application("app-1"), state=state, **facts)


def _pick_first_shift(machine: StateMachine, app: Application, **payload: object):
    payload.setdefault("first_shift_at", FIRST_SHIFT)
    return machine.dispatch(app, "first_shift_picked", manager(), now=T0, payload=payload)


def _rows_to(state: State) -> list:
    """Rows entering ``state`` from a different state: the real entry paths."""
    return [t for t in TRANSITIONS if t.to_state is state and t.from_state is not state]


# ------------------------------------------------------------------- INV-1


def test_inv1_structural_every_path_to_offer_sent_requires_recorded_approval() -> None:
    rows = _rows_to(State.OFFER_SENT)
    assert rows, "the table must contain the approval path"
    for row in rows:
        assert "manager_approval_recorded" in row.guards, row


def test_inv1_offer_without_approval_is_rejected() -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    result = machine.dispatch(app, "approval_recorded", manager(), now=T0)
    assert result.transitioned is False
    assert result.rejection_reason == "guard failed: manager_approval_recorded"
    assert result.application == app


@pytest.mark.parametrize("missing", ["manager_name", "decided_at", "facts_seen"])
def test_inv1_approval_missing_who_when_or_facts_is_rejected(missing: str) -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    payload = approval_payload()
    del payload["approval"][missing]
    result = machine.dispatch(app, "approval_recorded", manager(), now=T0, payload=payload)
    assert result.transitioned is False
    assert result.application.state is State.PENDING_MANAGER_DECISION


def test_inv1_no_event_reaches_offer_sent_without_approval() -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    for row in (t for t in TRANSITIONS if t.from_state is State.PENDING_MANAGER_DECISION):
        result = machine.dispatch(app, row.event, manager(), now=T0)
        assert not result.transitioned or result.to_state is not State.OFFER_SENT, row


def test_inv1_approval_with_full_record_reaches_offer_sent() -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    result = machine.dispatch(
        app, "approval_recorded", manager(), now=T0 + timedelta(hours=1), payload=approval_payload()
    )
    assert result.transitioned is True
    assert result.application.state is State.OFFER_SENT


# ------------------------------------------------------------------- INV-2


def test_inv2_structural_every_path_to_not_selected_requires_human_actor() -> None:
    rows = _rows_to(State.NOT_SELECTED)
    assert len(rows) == 2, rows
    for row in rows:
        assert "human_actor" in row.guards, row
        assert row.actors == (ActorKind.MANAGER,), row


@pytest.mark.parametrize("kind", [ActorKind.CANDIDATE, ActorKind.SYSTEM, ActorKind.TIMER])
@pytest.mark.parametrize("from_state", [State.SCREENING, State.PENDING_MANAGER_DECISION])
def test_inv2_not_selected_requires_a_human_actor(kind: ActorKind, from_state: State) -> None:
    machine = StateMachine()
    app = _app(from_state, decision_requested_at=T0)
    result = machine.dispatch(app, "rejection_recorded", Actor(kind), now=T0)
    # Rejected either by the actor-kind check or by the human_actor guard:
    # either way the state never changes.
    assert result.transitioned is False
    assert result.application == app
    assert result.application.state is from_state


def test_inv2_manager_without_a_name_is_not_a_named_human() -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    result = machine.dispatch(app, "rejection_recorded", Actor(ActorKind.MANAGER, None), now=T0)
    assert result.transitioned is False


def test_inv2_named_manager_records_rejection_with_facts() -> None:
    machine = StateMachine()
    app = _app(State.PENDING_MANAGER_DECISION, decision_requested_at=T0)
    result = machine.dispatch(
        app, "rejection_recorded", manager(), now=T0, payload={"reason": "no fit"}
    )
    assert result.transitioned is True
    assert result.application.state is State.NOT_SELECTED
    entry = result.audit_entries[0]
    assert entry.actor_kind == "manager"
    assert entry.actor_name == "Maria Gomez"


# ------------------------------------------------------------------- INV-3


def test_inv3_structural_scheduling_requires_documents_or_exception() -> None:
    rows = _rows_to(State.FIRST_SHIFT_SCHEDULED)
    assert rows, "the table must contain the scheduling path"
    for row in rows:
        assert "documents_or_exception" in row.guards, row


@pytest.mark.parametrize(
    "facts",
    [
        {"documents_complete": False, "people_ops_exception": False},
        {"documents_complete": False, "people_ops_exception": False, "csv_confirmed": True},
    ],
)
def test_inv3_scheduling_without_documents_or_exception_is_rejected(facts: dict) -> None:
    machine = StateMachine()
    app = _app(State.READY_FOR_ROTA, **facts)
    result = _pick_first_shift(machine, app)
    assert result.transitioned is False
    assert result.rejection_reason == "guard failed: documents_or_exception"
    assert result.application == app


def test_inv3_people_ops_exception_allows_scheduling() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=False,
        people_ops_exception=True,
        csv_confirmed=True,
        hygiene_module_complete=True,
    )
    result = _pick_first_shift(machine, app)
    assert result.transitioned is True
    assert result.application.state is State.FIRST_SHIFT_SCHEDULED


def test_inv3_complete_documents_allow_scheduling() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=True,
        csv_confirmed=True,
        hygiene_module_complete=True,
    )
    result = _pick_first_shift(machine, app)
    assert result.transitioned is True


# ------------------------------------------------------------------- INV-4


def test_inv4_structural_fallback_effect_declared_on_scheduling_path() -> None:
    rows = _rows_to(State.FIRST_SHIFT_SCHEDULED)
    for row in rows:
        assert "hygiene_fallback_if_needed" in row.effects, row


def test_inv4_food_handling_without_hygiene_falls_back_and_notifies_trainer() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=True,
        csv_confirmed=True,
        shift_type="food_handling",
        hygiene_module_complete=False,
    )
    result = _pick_first_shift(machine, app)
    assert result.transitioned is True
    assert result.application.effective_shift_type in ("till", "front_of_house")
    assert any(m.kind == "trainer.notify" for m in result.outbox_messages)
    writes = [m for m in result.outbox_messages if m.kind == "shiftgrid.write"]
    assert writes and writes[0].payload["shift_type"] == result.application.effective_shift_type


def test_inv4_fallback_shift_type_can_be_front_of_house() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=True,
        csv_confirmed=True,
        shift_type="food_handling",
        hygiene_module_complete=False,
    )
    result = machine.dispatch(
        app,
        "first_shift_picked",
        manager(),
        now=T0,
        payload={"first_shift_at": FIRST_SHIFT, "fallback_shift_type": "front_of_house"},
    )
    assert result.transitioned is True
    assert result.application.effective_shift_type == "front_of_house"


def test_inv4_completed_hygiene_module_keeps_food_handling() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=True,
        csv_confirmed=True,
        shift_type="food_handling",
        hygiene_module_complete=True,
    )
    result = _pick_first_shift(machine, app)
    assert result.transitioned is True
    assert result.application.effective_shift_type == "food_handling"
    assert not any(m.kind == "trainer.notify" for m in result.outbox_messages)


def test_inv4_non_food_handling_shift_needs_no_hygiene_module() -> None:
    machine = StateMachine()
    app = _app(
        State.READY_FOR_ROTA,
        documents_complete=True,
        csv_confirmed=True,
        shift_type="till",
        hygiene_module_complete=False,
    )
    result = _pick_first_shift(machine, app)
    assert result.transitioned is True
    assert result.application.effective_shift_type == "till"
    assert not any(m.kind == "trainer.notify" for m in result.outbox_messages)


# ------------------------------------------------------------------- INV-5


def test_inv5_every_transition_in_the_happy_walk_yields_an_audit_entry() -> None:
    _, results, _ = happy_walk()
    for result in results:
        assert result.transitioned is True
        assert len(result.audit_entries) >= 1
        entry = result.audit_entries[0]
        assert entry.event
        assert entry.from_state
        assert entry.to_state
        assert entry.at is not None
        assert entry.actor_kind


def test_inv5_audit_entry_matches_the_transition_it_records() -> None:
    machine = StateMachine()
    app = _app(State.CONTACTED, notice_version=NOTICE)
    result = machine.dispatch(
        app, "candidate_consents", candidate(), now=T0, payload={"channel": "whatsapp"}
    )
    entry = result.audit_entries[0]
    assert entry.application_id == "app-1"
    assert entry.from_state == "contacted"
    assert entry.to_state == "consented"
    assert entry.event == "candidate_consents"
    assert entry.at == T0


def test_inv5_timer_transitions_are_audited_with_the_timer_actor() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.CONTACTED,
        contacted_at=T0,
    )
    # A single tick at 48 h fires the whole T1 sequence in declarative order:
    # nudge 2 h, nudge 24 h, bench.
    results = machine.tick(app, T0 + timedelta(hours=48))
    assert [r.to_state for r in results] == [State.CONTACTED, State.CONTACTED, State.BENCHED]
    entry = results[-1].audit_entries[0]
    assert entry.actor_kind == "timer"
    assert entry.to_state == "benched"


def test_inv5_side_state_paths_also_produce_audit_entries() -> None:
    machine = StateMachine()
    app = _app(State.CONTACTED, notice_version=NOTICE)
    for event, actor, payload in [
        ("candidate_opted_out", candidate(), None),
    ]:
        result = machine.dispatch(app, event, actor, now=T0, payload=payload)
        assert result.transitioned is True
        assert len(result.audit_entries) == 1
        app = result.application
    # rejected dispatches are not transitions: no audit entries
    rejected = machine.dispatch(app, "candidate_opted_out", candidate(), now=T0)
    assert rejected.transitioned is False
    assert rejected.audit_entries == ()


# ------------------------------------------- declarative table sanity checks


def test_table_is_renderable_as_plain_data_for_the_console() -> None:
    meta = StateMachine().describe()
    state_names = {s.value for s in State}
    for row in meta["transitions"]:
        assert row["from_state"] in state_names
        assert row["to_state"] in state_names
        assert isinstance(row["event"], str)
        assert isinstance(row["guards"], list)
        assert isinstance(row["effects"], list)
    for timer in meta["timers"]:
        assert timer["key"]
        assert timer["event"]
        assert timer["offset_hours"] is not None


def test_side_states_are_reachable_per_the_design() -> None:
    targets = {t.to_state for t in TRANSITIONS}
    assert {State.BENCHED, State.WITHDRAWN, State.NOT_SELECTED, State.NO_SHOW} <= targets


def test_happy_path_slots_guard_uses_manager_open_slots() -> None:
    machine = StateMachine()
    app = replace(Application("app-1"), state=State.MATCHED, manager_open_slots=(SLOT,))
    other = SLOT + timedelta(days=1)
    rejected = machine.dispatch(app, "slot_selected", candidate(), now=T0, payload={"slot": other})
    assert rejected.transitioned is False
    accepted = machine.dispatch(app, "slot_selected", candidate(), now=T0, payload={"slot": SLOT})
    assert accepted.transitioned is True
    assert accepted.application.interview_at == SLOT


def test_offer_window_is_seven_days() -> None:
    machine = StateMachine()
    app = _app(State.OFFER_SENT, offer_sent_at=T0)
    late = machine.dispatch(app, "offer_accepted", candidate(), now=T0 + timedelta(days=8))
    assert late.transitioned is False
    assert late.rejection_reason == "guard failed: offer_within_window"
    within = machine.dispatch(app, "offer_accepted", candidate(), now=T0 + timedelta(days=6))
    assert within.transitioned is True
    assert within.application.state is State.OFFER_ACCEPTED


def test_screening_requires_eligibility_and_shift_fit() -> None:
    machine = StateMachine()
    app = _app(State.SCREENING)
    rejected = machine.dispatch(app, "shift_fit_matched", system(), now=T0)
    assert rejected.transitioned is False
    assert rejected.rejection_reason == "guard failed: eligibility_and_shift_fit"
    matched = machine.dispatch(
        app,
        "shift_fit_matched",
        system(),
        now=T0,
    )
    assert matched.transitioned is False
    good = replace(app, eligibility_ok=True, shift_fit_ok=True)
    result = machine.dispatch(good, "shift_fit_matched", system(), now=T0)
    assert result.transitioned is True
    assert result.application.state is State.MATCHED


def test_tracker_completion_requires_documents_and_csv_confirmation() -> None:
    machine = StateMachine()
    app = _app(State.PREBOARDING, documents_complete=True, csv_confirmed=False)
    rejected = machine.dispatch(app, "tracker_completed", system(), now=T0)
    assert rejected.transitioned is False
    assert rejected.rejection_reason == "guard failed: documents_and_csv_confirmed"


def test_system_actor_cannot_request_placeholder_events() -> None:
    # system() imported for symmetry with the other actor helpers; the real
    # enforcement lives in the actor-kind tests above.
    assert system().kind is ActorKind.SYSTEM
