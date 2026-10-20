"""Pure policies for the core state machine: guards, effects, timer conditions.

Everything here is a pure function of its inputs: no I/O, no clock, no LLM.
Guards, effects and conditions are registered by name so the declarative
transition table in app/core/state_machine.py stays serializable for the
console (GET /api/meta/state-machine).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from app.core.state_machine import (
    Actor,
    Application,
    AuditEntry,
    EffectCtx,
    EffectFn,
    ManagerApproval,
    State,
    TimerDef,
)

OFFER_ACCEPTANCE_WINDOW = timedelta(days=7)
FALLBACK_SHIFT_TYPES = ("till", "front_of_house")


# ------------------------------------------------------------------ helpers


def _approval(value: Any) -> ManagerApproval | None:
    if value is None:
        return None
    if isinstance(value, ManagerApproval):
        return value
    if isinstance(value, Mapping):
        return ManagerApproval(
            manager_id=str(value.get("manager_id", "")),
            manager_name=str(value.get("manager_name", "")),
            decided_at=value.get("decided_at"),
            facts_seen=str(value.get("facts_seen", "")),
        )
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ------------------------------------------------------------------- guards
# Signature: (app, actor, payload, now) -> bool


def first_message_discloses_ai(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return bool(payload.get("notice_version")) and payload.get("ai_disclosed") is True


def consent_notice_shown(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    # The notice version must have been shown on this channel before consent.
    return app.notice_version is not None and bool(payload.get("channel"))


def eligibility_and_shift_fit(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return app.eligibility_ok and app.shift_fit_ok


def slot_in_manager_open_slots(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    slot = payload.get("slot")
    return slot is not None and slot in app.manager_open_slots


def manager_approval_recorded(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    # INV-1: who, when and the facts seen must all be recorded.
    approval = _approval(payload.get("approval")) or app.manager_approval
    if approval is None:
        return False
    return (
        bool(approval.manager_name)
        and approval.decided_at is not None
        and bool(approval.facts_seen)
    )


def offer_within_window(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    if app.offer_sent_at is None or now is None:
        return False
    return now - app.offer_sent_at <= OFFER_ACCEPTANCE_WINDOW


def documents_and_csv_confirmed(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    # Row 21: documents complete in Nominia360 and creation confirmed by the CSV.
    return app.documents_complete and app.csv_confirmed


def documents_or_exception(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    # INV-3: documents complete or an explicit People Ops exception recorded.
    return app.documents_complete or app.people_ops_exception


def first_shift_slot_chosen(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return payload.get("first_shift_at") is not None


def human_actor(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    # INV-2: a named human. Manager is the only human actor kind.
    return actor.kind.value == "manager" and bool(actor.name)


def bench_consent(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return payload.get("bench_consent") is True


def reoffer_available(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return app.interview_reoffers < 1


def reengagement_consent_valid(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    if payload.get("reengagement_consent") is not True:
        return False
    expires_at = payload.get("consent_expires_at")
    if expires_at is None or now is None:
        return True
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    return now <= expires_at


def first_shift_unconfirmed(
    app: Application, actor: Actor, payload: Mapping[str, Any], now: datetime | None
) -> bool:
    return not app.first_shift_confirmed


GUARDS: dict[str, Any] = {
    "first_message_discloses_ai": first_message_discloses_ai,
    "consent_notice_shown": consent_notice_shown,
    "eligibility_and_shift_fit": eligibility_and_shift_fit,
    "slot_in_manager_open_slots": slot_in_manager_open_slots,
    "manager_approval_recorded": manager_approval_recorded,
    "offer_within_window": offer_within_window,
    "documents_and_csv_confirmed": documents_and_csv_confirmed,
    "documents_or_exception": documents_or_exception,
    "first_shift_slot_chosen": first_shift_slot_chosen,
    "human_actor": human_actor,
    "bench_consent": bench_consent,
    "reoffer_available": reoffer_available,
    "reengagement_consent_valid": reengagement_consent_valid,
    "first_shift_unconfirmed": first_shift_unconfirmed,
}


# ------------------------------------------------------- timer conditions
# Signature: (app, now) -> bool


def now_before_interview(app: Application, now: datetime | None) -> bool:
    return app.interview_at is not None and now is not None and now < app.interview_at


def first_shift_unconfirmed_condition(app: Application, now: datetime | None) -> bool:
    return not app.first_shift_confirmed


CONDITIONS: dict[str, Any] = {
    "now_before_interview": now_before_interview,
    "first_shift_unconfirmed": first_shift_unconfirmed_condition,
}


# ------------------------------------------------- declarative timer definitions
# T1 to T4 from design/state-machine.md. The machine never reads a clock: the
# caller ticks it with an injected ``now`` and a timer fires when
# ``anchor + offset <= now`` and the application is still in a timer state.

H = timedelta(hours=1)

TIMER_DEFINITIONS: tuple[TimerDef, ...] = (
    TimerDef("no_reply_nudge_1", "no-reply nudge at 2 h", "contacted_at", 2 * H,
             frozenset({State.CONTACTED}), "no_reply_nudge_1"),
    TimerDef("no_reply_nudge_2", "no-reply nudge at 24 h", "contacted_at", 24 * H,
             frozenset({State.CONTACTED}), "no_reply_nudge_2"),
    TimerDef("no_reply_bench", "bench at 48 h unanswered (T1, row 5)", "contacted_at", 48 * H,
             frozenset({State.CONTACTED}), "no_reply_benched"),
    TimerDef("interview_reminder_24h", "interview reminder 24 h before (T2)",
             "interview_at", -24 * H,
             frozenset({State.INTERVIEW_BOOKED}), "interview_reminder_24h",
             condition="now_before_interview"),
    TimerDef("interview_reminder_2h", "interview reminder 2 h before (T2)",
             "interview_at", -2 * H,
             frozenset({State.INTERVIEW_BOOKED}), "interview_reminder_2h",
             condition="now_before_interview"),
    TimerDef("manager_decision_remind", "manager decision SLA remind at 2 h (T3)",
             "decision_requested_at", 2 * H,
             frozenset({State.PENDING_MANAGER_DECISION}), "manager_decision_remind"),
    TimerDef("manager_decision_escalate", "manager decision SLA escalate at 8 h (T3, H5)",
             "decision_requested_at", 8 * H,
             frozenset({State.PENDING_MANAGER_DECISION}), "manager_decision_escalate"),
    TimerDef("confirmation_cutoff", "first-shift confirmation cutoff T-18h (T4, H4)",
             "first_shift_at", -18 * H,
             frozenset({State.FIRST_SHIFT_SCHEDULED}), "confirmation_cutoff",
             condition="first_shift_unconfirmed"),
)


# ------------------------------------------------------------------ effects
# Signature: (ctx) -> None; ctx.mutate carries snapshot changes back out.


def send_first_message(ctx: EffectCtx) -> None:
    ctx.mutate(notice_version=ctx.payload.get("notice_version"))
    ctx.outbox(
        "whatsapp.out",
        {
            "to": ctx.app.application_id,
            "template": "first_message",
            "notice_version": ctx.payload.get("notice_version"),
            "ai_disclosed": True,
        },
    )
    ctx.event("message.out", {"template": "first_message"})


def record_first_contact(ctx: EffectCtx) -> None:
    ctx.mutate(contacted_at=ctx.now)


def store_consent(ctx: EffectCtx) -> None:
    ctx.mutate(consent_channel=ctx.payload.get("channel"), language=ctx.payload.get("language"))
    ctx.event(
        "consent.recorded",
        {"channel": ctx.payload.get("channel"), "notice_version": ctx.app.notice_version},
    )


def stop_processing(ctx: EffectCtx) -> None:
    ctx.event("processing.stopped", {"reason": "opt_out"})


def start_retention_clock(ctx: EffectCtx) -> None:
    ctx.event("retention.clock_started", {"at": _iso(ctx.now)})


def store_recommendation(ctx: EffectCtx) -> None:
    ctx.event("recommendation.stored", {"eligibility_ok": True, "shift_fit_ok": True})


def update_hiredesk_stage(ctx: EffectCtx) -> None:
    ctx.outbox(
        "hiredesk.stage_update",
        {
            "application_id": ctx.app.application_id,
            "stage": ctx.payload.get("stage", "interview_booked"),
        },
    )
    ctx.event("integration.write", {"system": "hiredesk", "kind": "stage_update"})


def record_interview_slot(ctx: EffectCtx) -> None:
    ctx.mutate(interview_at=ctx.payload.get("slot"))


def send_manager_summary(ctx: EffectCtx) -> None:
    ctx.outbox(
        "whatsapp.out",
        {"to": "manager", "template": "decision_request", "buttons": ["approve", "decline"]},
    )
    ctx.event("message.out", {"template": "decision_request"})


def record_decision_request(ctx: EffectCtx) -> None:
    ctx.mutate(decision_requested_at=ctx.now)


def log_approval(ctx: EffectCtx) -> None:
    approval = _approval(ctx.payload.get("approval")) or ctx.app.manager_approval
    if approval is not None:
        ctx.mutate(manager_approval=approval)
    ctx.event("approval.recorded", {"by": approval.manager_name if approval else None})


def dispatch_offer(ctx: EffectCtx) -> None:
    ctx.mutate(offer_sent_at=ctx.now)
    ctx.outbox("whatsapp.out", {"to": ctx.app.application_id, "template": "offer"})
    ctx.event("message.out", {"template": "offer"})


def open_o11_tracker(ctx: EffectCtx) -> None:
    ctx.event("tracker.opened", {"tracker": "o11_hired_to_rota"})


def write_shiftgrid(ctx: EffectCtx) -> None:
    effective = ctx.app.effective_shift_type or ctx.app.shift_type
    ctx.mutate(first_shift_at=ctx.payload.get("first_shift_at"))
    ctx.outbox(
        "shiftgrid.write",
        {
            "application_id": ctx.app.application_id,
            "first_shift_at": _iso(ctx.payload.get("first_shift_at")),
            "shift_type": effective,
        },
    )
    ctx.event("integration.write", {"system": "shiftgrid", "kind": "first_shift"})


def reserve_backup(ctx: EffectCtx) -> None:
    ctx.outbox(
        "bench.reserve_backup",
        {
            "application_id": ctx.app.application_id,
            "first_shift_at": _iso(ctx.payload.get("first_shift_at")),
        },
    )
    ctx.event("backup.reserved", {"from": "bench"})


def hygiene_fallback_if_needed(ctx: EffectCtx) -> None:
    # INV-4: food-handling first shifts require the hygiene module. Otherwise
    # the shift is scheduled as till or front-of-house and the trainer is told.
    if ctx.app.shift_type == "food_handling" and not ctx.app.hygiene_module_complete:
        fallback = ctx.payload.get("fallback_shift_type", "till")
        assert fallback in FALLBACK_SHIFT_TYPES
        ctx.mutate(effective_shift_type=fallback)
        ctx.outbox(
            "trainer.notify",
            {
                "application_id": ctx.app.application_id,
                "reason": "hygiene_module_pending",
                "shift_type": fallback,
            },
        )
        ctx.event("hygiene.fallback", {"effective_shift_type": fallback})
    else:
        ctx.mutate(effective_shift_type=ctx.app.shift_type)


def stand_down_backup(ctx: EffectCtx) -> None:
    if ctx.app.backup_active:
        ctx.event("backup.stood_down", {"first_shift_at": _iso(ctx.app.first_shift_at)})
    ctx.mutate(backup_active=False)


def record_confirmation(ctx: EffectCtx) -> None:
    ctx.mutate(first_shift_confirmed=True)


def arm_day0_checkin(ctx: EffectCtx) -> None:
    ctx.event("timers.armed", {"timers": ["day0_checkin"]})


def record_shift_end(ctx: EffectCtx) -> None:
    ctx.event("shift.worked", {"at": _iso(ctx.now)})


def audit_unconfirmed_arrival(ctx: EffectCtx) -> None:
    # Row 25: the audit notes that the day-before confirmation never came.
    ctx.audit_entries.append(
        AuditEntry(
            application_id=ctx.app.application_id,
            at=ctx.now,
            actor_kind=ctx.actor.kind.value,
            actor_name=ctx.actor.name,
            event="confirmation_never_received",
            from_state=ctx.app.state.value,
            to_state=ctx.app.state.value,
            details="day 0 arrival without the day-before confirmation",
        )
    )


def bench_offer_if_consented(ctx: EffectCtx) -> None:
    if ctx.payload.get("bench_consent") is True:
        ctx.outbox("whatsapp.out", {"to": ctx.app.application_id, "template": "bench_offer"})


def log_decision(ctx: EffectCtx) -> None:
    ctx.event(
        "decision.recorded",
        {
            "by": ctx.actor.name,
            "kind": "rejection",
            "reason": ctx.payload.get("reason"),
        },
    )


def send_rejection_reply(ctx: EffectCtx) -> None:
    ctx.outbox("whatsapp.out", {"to": ctx.app.application_id, "template": "rejection"})


def add_bench_entry(ctx: EffectCtx) -> None:
    ctx.event("bench.added", {"restaurant_scope": True, "reengagement_consent": True})


def send_reengagement_message(ctx: EffectCtx) -> None:
    ctx.outbox("whatsapp.out", {"to": ctx.app.application_id, "template": "bench_reengagement"})


def send_nudge(ctx: EffectCtx) -> None:
    nudge_number = ctx.app.nudge_count + 1
    ctx.mutate(nudge_count=nudge_number)
    ctx.outbox(
        "whatsapp.out",
        {"to": ctx.app.application_id, "template": f"nudge_{nudge_number}"},
    )
    ctx.event("message.out", {"template": f"nudge_{nudge_number}"})


def send_interview_reminder(ctx: EffectCtx) -> None:
    hours = 24 if ctx.payload.get("timer") == "interview_reminder_24h" else 2
    ctx.outbox(
        "whatsapp.out",
        {"to": ctx.app.application_id, "template": "interview_reminder", "hours_before": hours},
    )
    ctx.event("message.out", {"template": "interview_reminder"})


def remind_manager_decision(ctx: EffectCtx) -> None:
    ctx.outbox("whatsapp.out", {"to": "manager", "template": "decision_reminder"})
    ctx.event("message.out", {"template": "decision_reminder"})


def escalate_to_hrbp(ctx: EffectCtx) -> None:
    ctx.outbox(
        "whatsapp.out",
        {"to": "area_hrbp", "template": "decision_escalation", "sla_hours": 8},
    )
    ctx.event("decision.escalated", {"to": "area_hrbp", "after_hours": 8})


def activate_backup(ctx: EffectCtx) -> None:
    ctx.mutate(backup_active=True)
    ctx.outbox(
        "backup.activate",
        {"application_id": ctx.app.application_id, "first_shift_at": _iso(ctx.app.first_shift_at)},
    )
    ctx.event("backup.activated", {"from": "bench"})


def manager_reoffer(ctx: EffectCtx) -> None:
    ctx.outbox("whatsapp.out", {"to": "manager", "template": "interview_reoffer"})


def record_interview_reoffer(ctx: EffectCtx) -> None:
    ctx.mutate(interview_reoffers=ctx.app.interview_reoffers + 1)


def notify_manager_no_show(ctx: EffectCtx) -> None:
    ctx.outbox(
        "whatsapp.out",
        {"to": "manager", "template": "no_show", "application_id": ctx.app.application_id},
    )
    ctx.event("no_show.recorded", {"application_id": ctx.app.application_id})


_EFFECT_NAMES = frozenset({
    "send_first_message", "record_first_contact", "store_consent", "stop_processing",
    "start_retention_clock", "store_recommendation", "update_hiredesk_stage",
    "record_interview_slot", "send_manager_summary", "record_decision_request",
    "log_approval", "dispatch_offer", "open_o11_tracker", "write_shiftgrid",
    "reserve_backup", "hygiene_fallback_if_needed", "stand_down_backup",
    "record_confirmation", "arm_day0_checkin", "record_shift_end",
    "audit_unconfirmed_arrival", "bench_offer_if_consented", "log_decision",
    "send_rejection_reply", "add_bench_entry", "send_reengagement_message",
    "send_nudge", "send_interview_reminder", "remind_manager_decision",
    "escalate_to_hrbp", "activate_backup", "manager_reoffer",
    "record_interview_reoffer", "notify_manager_no_show",
})


EFFECTS: dict[str, EffectFn] = {
    name: fn
    for name, fn in globals().items()
    if name in _EFFECT_NAMES and callable(fn)
}
