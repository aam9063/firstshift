"""T3 (S4): deterministic core state machine, happy path and timers.

The machine is pure: no I/O, no wall clock. Every dispatch receives the
current time injected as ``now`` and returns effects as plain data
(``transitioned``, ``audit_entries``, ``outbox_messages``, ``events``).
"""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.core.state_machine import Actor, ActorKind, Application, State, StateMachine

T0 = datetime(2025, 7, 7, 9, 0, 0)
NOTICE = "notice-2025-01"
SLOT = datetime(2025, 7, 8, 11, 0)
FIRST_SHIFT = datetime(2025, 7, 10, 19, 0)


def candidate() -> Actor:
    return Actor(ActorKind.CANDIDATE)


def manager(name: str = "Maria Gomez") -> Actor:
    return Actor(ActorKind.MANAGER, name)


def system() -> Actor:
    return Actor(ActorKind.SYSTEM)


def approval_payload(decided_at: datetime | None = None) -> dict:
    return {
        "approval": {
            "manager_id": "mgr-1",
            "manager_name": "Maria Gomez",
            "decided_at": decided_at or datetime(2025, 7, 8, 15, 0),
            "facts_seen": "screening summary v1, eligibility facts pass",
        }
    }


def happy_walk() -> tuple[StateMachine, list, Application]:
    """Scripted candidate walk from new to first_shift_worked."""
    machine = StateMachine()
    app = Application(
        application_id="app-1",
        manager_open_slots=(SLOT, datetime(2025, 7, 9, 11, 0)),
    )
    steps = [
        ("intake_processed", system(), {"notice_version": NOTICE, "ai_disclosed": True}, None, T0),
        ("candidate_consents", candidate(), {"channel": "whatsapp", "language": "es"}, None, T0),
        ("screening_starts", system(), None, None, T0),
        (
            "shift_fit_matched",
            system(),
            None,
            {"eligibility_ok": True, "shift_fit_ok": True},
            T0,
        ),
        ("slot_selected", candidate(), {"slot": SLOT}, None, T0),
        ("interview_attended", candidate(), None, None, datetime(2025, 7, 8, 11, 30)),
        ("decision_requested", system(), None, None, datetime(2025, 7, 8, 12, 0)),
        ("approval_recorded", manager(), approval_payload(), None, datetime(2025, 7, 8, 15, 0)),
        ("offer_accepted", candidate(), None, None, datetime(2025, 7, 8, 16, 0)),
        ("tracker_opened", system(), None, None, datetime(2025, 7, 8, 16, 5)),
        (
            "tracker_completed",
            system(),
            None,
            {"documents_complete": True, "csv_confirmed": True},
            datetime(2025, 7, 9, 3, 0),
        ),
        (
            "first_shift_picked",
            manager(),
            {"first_shift_at": FIRST_SHIFT},
            {"hygiene_module_complete": True},
            datetime(2025, 7, 9, 10, 0),
        ),
        ("first_shift_confirmed", candidate(), None, None, datetime(2025, 7, 9, 18, 0)),
        ("shift_worked", candidate(), None, None, datetime(2025, 7, 11, 1, 0)),
    ]
    results = []
    for event, actor, payload, facts, now in steps:
        if facts:
            app = replace(app, **facts)
        result = machine.dispatch(app, event, actor, now=now, payload=payload)
        results.append(result)
        assert result.transitioned, f"{event} rejected: {result.rejection_reason}"
        app = result.application
    return machine, results, app


# ----------------------------------------------------------------- happy path


def test_happy_path_walk_reaches_first_shift_worked() -> None:
    _, results, app = happy_walk()
    expected = [
        State.CONTACTED,
        State.CONSENTED,
        State.SCREENING,
        State.MATCHED,
        State.INTERVIEW_BOOKED,
        State.INTERVIEWED,
        State.PENDING_MANAGER_DECISION,
        State.OFFER_SENT,
        State.OFFER_ACCEPTED,
        State.PREBOARDING,
        State.READY_FOR_ROTA,
        State.FIRST_SHIFT_SCHEDULED,
        State.FIRST_SHIFT_CONFIRMED,
        State.FIRST_SHIFT_WORKED,
    ]
    assert [r.to_state for r in results] == expected
    assert app.state is State.FIRST_SHIFT_WORKED


def test_first_message_stores_notice_version_and_first_contact_time() -> None:
    _, results, _ = happy_walk()
    app_after_first = results[0].application
    assert app_after_first.notice_version == NOTICE
    assert app_after_first.contacted_at == T0
    assert any(m.kind == "whatsapp.out" for m in results[0].outbox_messages)


def test_consent_stores_channel_and_language() -> None:
    _, results, _ = happy_walk()
    app = results[1].application
    assert app.consent_channel == "whatsapp"
    assert app.language == "es"


def test_approval_records_who_when_and_facts_seen() -> None:
    _, results, _ = happy_walk()
    app = results[7].application
    assert app.manager_approval is not None
    assert app.manager_approval.manager_name == "Maria Gomez"
    assert app.manager_approval.facts_seen == "screening summary v1, eligibility facts pass"
    assert app.offer_sent_at == datetime(2025, 7, 8, 15, 0)


def test_first_shift_scheduled_records_slot_and_shift_type() -> None:
    _, results, _ = happy_walk()
    app = results[11].application
    assert app.first_shift_at == FIRST_SHIFT
    assert app.effective_shift_type == "food_handling"


# ---------------------------------------------------------------- rejections


def test_rejected_dispatch_leaves_application_unchanged() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.PENDING_MANAGER_DECISION,
        decision_requested_at=T0,
    )
    result = machine.dispatch(app, "approval_recorded", manager(), now=T0)
    assert result.transitioned is False
    assert result.rejection_reason == "guard failed: manager_approval_recorded"
    assert result.application == app
    assert result.audit_entries == ()
    assert result.outbox_messages == ()
    assert result.events == ()


def test_unknown_event_in_state_is_rejected() -> None:
    machine = StateMachine()
    app = Application("app-1")
    result = machine.dispatch(app, "offer_accepted", candidate(), now=T0)
    assert result.transitioned is False
    assert result.rejection_reason == "unknown event 'offer_accepted' in state 'new'"
    assert result.application == app


def test_actor_kind_is_enforced_against_the_table() -> None:
    machine = StateMachine()
    app = replace(Application("app-1"), state=State.CONTACTED, notice_version=NOTICE)
    result = machine.dispatch(
        app, "candidate_consents", system(), now=T0, payload={"channel": "whatsapp"}
    )
    assert result.transitioned is False
    assert result.rejection_reason == (
        "actor kind 'system' not allowed for event 'candidate_consents'"
    )


# -------------------------------------------------------------------- timers


def _contacted_app() -> Application:
    return replace(Application("app-1"), state=State.CONTACTED, contacted_at=T0)


def test_no_reply_nudge_at_2h_and_24h_then_bench_at_48h() -> None:
    machine = StateMachine()
    app = _contacted_app()

    assert machine.tick(app, T0 + timedelta(minutes=90)) == ()

    r1 = machine.tick(app, T0 + timedelta(hours=2))
    assert len(r1) == 1
    assert r1[0].transitioned is True
    assert r1[0].application.state is State.CONTACTED
    assert any(m.payload.get("template") == "nudge_1" for m in r1[0].outbox_messages)
    assert r1[0].audit_entries[0].actor_kind == "timer"

    # A timer fires exactly once.
    assert machine.tick(r1[0].application, T0 + timedelta(hours=2, minutes=1)) == ()

    r2 = machine.tick(r1[0].application, T0 + timedelta(hours=24))
    assert len(r2) == 1
    assert any(m.payload.get("template") == "nudge_2" for m in r2[0].outbox_messages)

    r3 = machine.tick(r2[0].application, T0 + timedelta(hours=48))
    assert len(r3) == 1
    assert r3[0].application.state is State.BENCHED


def test_consent_before_48h_prevents_benching() -> None:
    machine = StateMachine()
    app = replace(_contacted_app(), notice_version=NOTICE)
    nudged = machine.tick(app, T0 + timedelta(hours=2))[0].application
    consented = machine.dispatch(
        nudged,
        "candidate_consents",
        candidate(),
        now=T0 + timedelta(hours=3),
        payload={"channel": "whatsapp"},
    ).application
    assert consented.state is State.CONSENTED
    assert machine.tick(consented, T0 + timedelta(hours=48)) == ()


def test_interview_reminders_at_24h_and_2h_before_slot() -> None:
    machine = StateMachine()
    interview_at = T0 + timedelta(hours=30)
    app = replace(Application("app-1"), state=State.INTERVIEW_BOOKED, interview_at=interview_at)

    r1 = machine.tick(app, interview_at - timedelta(hours=24))
    assert len(r1) == 1
    assert any(
        m.payload.get("template") == "interview_reminder" and m.payload.get("hours_before") == 24
        for m in r1[0].outbox_messages
    )

    assert machine.tick(r1[0].application, interview_at - timedelta(hours=23)) == ()

    r2 = machine.tick(r1[0].application, interview_at - timedelta(hours=2))
    assert len(r2) == 1
    assert any(
        m.payload.get("template") == "interview_reminder" and m.payload.get("hours_before") == 2
        for m in r2[0].outbox_messages
    )


def test_manager_decision_sla_remind_at_2h_escalate_at_8h() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.PENDING_MANAGER_DECISION,
        decision_requested_at=T0,
    )

    r1 = machine.tick(app, T0 + timedelta(hours=2))
    assert len(r1) == 1
    assert any(m.kind == "whatsapp.out" for m in r1[0].outbox_messages)
    assert r1[0].application.state is State.PENDING_MANAGER_DECISION

    r2 = machine.tick(r1[0].application, T0 + timedelta(hours=8))
    assert len(r2) == 1
    assert any(m.payload.get("to") == "area_hrbp" for m in r2[0].outbox_messages)
    assert r2[0].application.state is State.PENDING_MANAGER_DECISION


def test_confirmation_cutoff_t_minus_18h_activates_backup() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.FIRST_SHIFT_SCHEDULED,
        first_shift_at=FIRST_SHIFT,
    )

    # T-24h: cutoff not due yet.
    assert machine.tick(app, FIRST_SHIFT - timedelta(hours=24)) == ()

    fired = machine.tick(app, FIRST_SHIFT - timedelta(hours=18))
    assert len(fired) == 1
    result = fired[0]
    assert result.transitioned is True
    # The primary candidate stays scheduled with a backup-active flag.
    assert result.application.state is State.FIRST_SHIFT_SCHEDULED
    assert result.application.backup_active is True
    assert any(m.kind == "backup.activate" for m in result.outbox_messages)

    # A late confirmation still stands the backup down.
    confirmed = machine.dispatch(
        result.application,
        "first_shift_confirmed",
        candidate(),
        now=FIRST_SHIFT - timedelta(hours=17),
    )
    assert confirmed.transitioned is True
    assert confirmed.application.backup_active is False


def test_cutoff_does_not_fire_once_confirmed() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.FIRST_SHIFT_CONFIRMED,
        first_shift_at=FIRST_SHIFT,
        first_shift_confirmed=True,
    )
    assert machine.tick(app, FIRST_SHIFT + timedelta(hours=1)) == ()


# --------------------------------------------------------------- side states


def test_opt_out_reaches_withdrawn() -> None:
    machine = StateMachine()
    app = _contacted_app()
    result = machine.dispatch(
        app, "candidate_opted_out", candidate(), now=T0 + timedelta(minutes=5)
    )
    assert result.transitioned is True
    assert result.application.state is State.WITHDRAWN


def test_day0_worked_unconfirmed_stands_down_backup() -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=State.FIRST_SHIFT_SCHEDULED,
        first_shift_at=FIRST_SHIFT,
        backup_active=True,
    )
    result = machine.dispatch(app, "day0_worked_unconfirmed", candidate(), now=FIRST_SHIFT)
    assert result.transitioned is True
    assert result.application.state is State.FIRST_SHIFT_WORKED
    assert result.application.backup_active is False


@pytest.mark.parametrize(
    ("event", "from_state"),
    [("day0_no_show", State.FIRST_SHIFT_SCHEDULED), ("day0_no_show", State.FIRST_SHIFT_CONFIRMED)],
)
def test_day0_no_show_reaches_no_show(event: str, from_state: State) -> None:
    machine = StateMachine()
    app = replace(
        Application("app-1"),
        state=from_state,
        first_shift_at=FIRST_SHIFT,
        first_shift_confirmed=from_state is State.FIRST_SHIFT_CONFIRMED,
    )
    result = machine.dispatch(
        app,
        event,
        Actor(ActorKind.TIMER, "day0"),
        now=FIRST_SHIFT + timedelta(hours=2),
    )
    assert result.transitioned is True
    assert result.application.state is State.NO_SHOW
