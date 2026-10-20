"""Deterministic core state machine for the crew hiring pilot.

Pure Python: no I/O, no LLM, no wall clock. The machine receives the current
time injected as ``now`` and returns effects as plain data (transitioned,
audit_entries, outbox_messages, events). Persistence happens outside the core.

The transition table and the timer definitions are declarative so the console
can later render them from GET /api/meta/state-machine. Guards and effects
live in app/core/policies.py as pure predicate and effect functions and are
referenced from the table by name.

Source of truth: design/state-machine.md (states, 32-row transition table,
timers T1 to T4, invariants INV-1 to INV-5), specs/03-solution-design.md
section 5, specs/04-prototype.md section 1.4. This module implements the
happy-path states plus the side states (benched, withdrawn, not_selected,
no_show); the active_week1/active_day30 and erasure rows arrive with later
features.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class State(StrEnum):
    """States of one candidate application against one open shift."""

    NEW = "new"
    CONTACTED = "contacted"
    CONSENTED = "consented"
    SCREENING = "screening"
    MATCHED = "matched"
    INTERVIEW_BOOKED = "interview_booked"
    INTERVIEWED = "interviewed"
    PENDING_MANAGER_DECISION = "pending_manager_decision"
    OFFER_SENT = "offer_sent"
    OFFER_ACCEPTED = "offer_accepted"
    PREBOARDING = "preboarding"
    READY_FOR_ROTA = "ready_for_rota"
    FIRST_SHIFT_SCHEDULED = "first_shift_scheduled"
    FIRST_SHIFT_CONFIRMED = "first_shift_confirmed"
    FIRST_SHIFT_WORKED = "first_shift_worked"
    # Side states
    BENCHED = "benched"
    WITHDRAWN = "withdrawn"
    NOT_SELECTED = "not_selected"
    NO_SHOW = "no_show"


class ActorKind(StrEnum):
    """Actor types from the design transition table.

    Agent actions are recorded as system actions: accountability sits with the
    system, not the model. Only ``manager`` counts as a human actor.
    """

    CANDIDATE = "candidate"
    MANAGER = "manager"
    SYSTEM = "system"
    TIMER = "timer"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    name: str | None = None


@dataclass(frozen=True)
class ManagerApproval:
    """Recorded approval: who, when and the facts the approver saw (INV-1)."""

    manager_id: str
    manager_name: str
    decided_at: datetime | None
    facts_seen: str


@dataclass(frozen=True)
class Application:
    """Immutable snapshot of one application. Callers persist the new snapshot."""

    application_id: str
    state: State = State.NEW
    # Contact and consent
    notice_version: str | None = None
    consent_channel: str | None = None
    language: str | None = None
    contacted_at: datetime | None = None
    nudge_count: int = 0
    # Screening and matching
    eligibility_ok: bool = False
    shift_fit_ok: bool = False
    manager_open_slots: tuple[datetime, ...] = ()
    interview_at: datetime | None = None
    interview_reoffers: int = 0
    # Decision
    decision_requested_at: datetime | None = None
    manager_approval: ManagerApproval | None = None
    offer_sent_at: datetime | None = None
    # Preboarding (O11 tracker)
    documents_complete: bool = False
    csv_confirmed: bool = False
    people_ops_exception: bool = False
    # First shift
    shift_type: str = "food_handling"
    effective_shift_type: str | None = None
    hygiene_module_complete: bool = False
    first_shift_at: datetime | None = None
    first_shift_confirmed: bool = False
    backup_active: bool = False
    # Bookkeeping for timer de-duplication (pure data, no wall clock)
    fired_timers: frozenset[str] = frozenset()


# --------------------------------------------------------------- effect data


@dataclass(frozen=True)
class AuditEntry:
    application_id: str
    at: datetime | None
    actor_kind: str
    actor_name: str | None
    event: str
    from_state: str
    to_state: str
    details: str = ""


@dataclass(frozen=True)
class OutboxMessage:
    kind: str
    payload: dict[str, Any]
    at: datetime | None


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]


@dataclass
class EffectCtx:
    """Mutable scratchpad threaded through the effect functions of one dispatch."""

    app: Application
    payload: Mapping[str, Any]
    actor: Actor
    now: datetime | None
    audit_entries: list[AuditEntry] = field(default_factory=list)
    outbox_messages: list[OutboxMessage] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    def mutate(self, **changes: Any) -> None:
        self.app = replace(self.app, **changes)

    def outbox(self, kind: str, payload: Mapping[str, Any]) -> None:
        self.outbox_messages.append(OutboxMessage(kind=kind, payload=dict(payload), at=self.now))

    def event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.events.append(Event(type=event_type, payload=dict(payload)))


GuardFn = Callable[[Application, Actor, Mapping[str, Any], datetime | None], bool]
EffectFn = Callable[[EffectCtx], None]
ConditionFn = Callable[[Application, datetime | None], bool]


# ------------------------------------------------------- declarative table


@dataclass(frozen=True)
class Transition:
    """One row of the design transition table, as declarative data.

    Guards and effects are referenced by name and resolved against the
    registries in app/core/policies.py, so the table stays serializable for
    the console (GET /api/meta/state-machine).
    """

    from_state: State
    event: str
    to_state: State
    actors: tuple[ActorKind, ...]
    guards: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state.value,
            "event": self.event,
            "to_state": self.to_state.value,
            "actors": [a.value for a in self.actors],
            "guards": list(self.guards),
            "effects": list(self.effects),
            "description": self.description,
        }


def _t(
    from_state: State,
    event: str,
    to_state: State,
    actors: tuple[ActorKind, ...],
    **kw: Any,
) -> Transition:
    return Transition(from_state, event, to_state, actors, **kw)


TRANSITIONS: tuple[Transition, ...] = (
    # Happy path (design rows 1 to 14, 17, 19, 21, 23 to 26)
    _t(State.NEW, "intake_processed", State.CONTACTED, (ActorKind.SYSTEM,),
       guards=("first_message_discloses_ai",),
       effects=("send_first_message", "record_first_contact"),
       description="row 2: first message carries AI disclosure and notice version"),
    _t(State.CONTACTED, "candidate_consents", State.CONSENTED, (ActorKind.CANDIDATE,),
       guards=("consent_notice_shown",),
       effects=("store_consent",),
       description="row 3: consent for this channel with notice version"),
    _t(State.CONTACTED, "candidate_opted_out", State.WITHDRAWN, (ActorKind.CANDIDATE,),
       effects=("stop_processing", "start_retention_clock"),
       description="row 4: processing stops, retention clock starts"),
    _t(State.CONSENTED, "screening_starts", State.SCREENING, (ActorKind.SYSTEM,),
       description="row 6: structured screening starts"),
    _t(State.SCREENING, "shift_fit_matched", State.MATCHED, (ActorKind.SYSTEM,),
       guards=("eligibility_and_shift_fit",),
       effects=("store_recommendation",),
       description="row 7: eligibility facts pass and an open shift fits"),
    _t(State.MATCHED, "slot_selected", State.INTERVIEW_BOOKED, (ActorKind.CANDIDATE,),
       guards=("slot_in_manager_open_slots",),
       effects=("update_hiredesk_stage", "record_interview_slot"),
       description="row 10: slot is one of the manager's open slots"),
    _t(State.INTERVIEW_BOOKED, "interview_attended", State.INTERVIEWED, (ActorKind.CANDIDATE,),
       description="row 11 follow-on: candidate attends"),
    _t(State.INTERVIEWED, "decision_requested", State.PENDING_MANAGER_DECISION, (ActorKind.SYSTEM,),
       effects=("send_manager_summary", "record_decision_request"),
       description="row 13: summary sent to the manager, SLA timers armed"),
    _t(State.PENDING_MANAGER_DECISION, "approval_recorded", State.OFFER_SENT, (ActorKind.MANAGER,),
       guards=("manager_approval_recorded",),
       effects=("log_approval", "dispatch_offer"),
       description="rows 14/15: recorded approval with who, when, facts seen (INV-1)"),
    _t(State.OFFER_SENT, "offer_accepted", State.OFFER_ACCEPTED, (ActorKind.CANDIDATE,),
       guards=("offer_within_window",),
       description="row 17: candidate accepts within the 7-day window"),
    _t(State.OFFER_SENT, "offer_declined", State.WITHDRAWN, (ActorKind.CANDIDATE, ActorKind.TIMER),
       effects=("bench_offer_if_consented",),
       description="row 18: decline or window expiry, retention clock starts"),
    _t(State.OFFER_ACCEPTED, "tracker_opened", State.PREBOARDING, (ActorKind.SYSTEM,),
       effects=("open_o11_tracker",),
       description="row 19: O11 hired-to-rota tracker opens"),
    _t(State.PREBOARDING, "tracker_completed", State.READY_FOR_ROTA, (ActorKind.SYSTEM,),
       guards=("documents_and_csv_confirmed",),
       description="row 21: documents complete and creation CSV-confirmed (C-T4)"),
    _t(
        State.READY_FOR_ROTA,
        "first_shift_picked",
        State.FIRST_SHIFT_SCHEDULED,
        (ActorKind.MANAGER,),
        guards=("documents_or_exception", "first_shift_slot_chosen"),
        effects=("hygiene_fallback_if_needed", "write_shiftgrid", "reserve_backup"),
        description="row 23: INV-3 and INV-4 live here; named backup reserved (H4)",
    ),
    _t(
        State.FIRST_SHIFT_SCHEDULED, "first_shift_confirmed", State.FIRST_SHIFT_CONFIRMED,
        (ActorKind.CANDIDATE,),
        effects=("stand_down_backup", "record_confirmation", "arm_day0_checkin"),
        description="row 24: day-before confirmation stands the backup down",
    ),
    _t(
        State.FIRST_SHIFT_SCHEDULED, "day0_worked_unconfirmed", State.FIRST_SHIFT_WORKED,
        (ActorKind.CANDIDATE,),
        effects=("stand_down_backup", "record_shift_end", "audit_unconfirmed_arrival"),
        description="row 25: day 0 arrives, candidate shows unconfirmed",
    ),
    _t(
        State.FIRST_SHIFT_CONFIRMED,
        "shift_worked",
        State.FIRST_SHIFT_WORKED,
        (ActorKind.CANDIDATE,),
        effects=("record_shift_end",),
        description="row 26: shift end recorded, day-3 check-in armed",
    ),
    # Interview recovery (rows 11 and 12)
    _t(
        State.INTERVIEW_BOOKED,
        "interview_missed_once",
        State.INTERVIEW_BOOKED,
        (ActorKind.MANAGER,),
        guards=("reoffer_available",),
        effects=("manager_reoffer", "record_interview_reoffer"),
        description="row 11: one re-offer only",
    ),
    _t(State.INTERVIEW_BOOKED, "interview_missed_again", State.NO_SHOW, (ActorKind.TIMER,),
       effects=("notify_manager_no_show",),
       description="row 12: second missed interview"),
    # Rejections (INV-2: human actor only)
    _t(State.SCREENING, "rejection_recorded", State.NOT_SELECTED, (ActorKind.MANAGER,),
       guards=("human_actor",),
       effects=("log_decision", "send_rejection_reply", "bench_offer_if_consented"),
       description="row 9: a named human records the rejection"),
    _t(
        State.PENDING_MANAGER_DECISION,
        "rejection_recorded",
        State.NOT_SELECTED,
        (ActorKind.MANAGER,),
        guards=("human_actor",),
        effects=("log_decision", "send_rejection_reply", "bench_offer_if_consented"),
        description="row 16: manager declines",
    ),
    # Bench (O4)
    _t(State.SCREENING, "benched_with_consent", State.BENCHED, (ActorKind.SYSTEM,),
       guards=("bench_consent",),
       effects=("add_bench_entry",),
       description="row 8: no fit now and the candidate consents to the bench"),
    _t(State.BENCHED, "bench_reengaged", State.CONTACTED, (ActorKind.SYSTEM,),
       guards=("reengagement_consent_valid",),
       effects=("send_reengagement_message", "record_first_contact"),
       description="row 31: new gap, re-engagement consent valid and unexpired"),
    # Day-0 no-show (row 27)
    _t(State.FIRST_SHIFT_SCHEDULED, "day0_no_show", State.NO_SHOW, (ActorKind.TIMER,),
       effects=("notify_manager_no_show",),
       description="row 27: operational cause checked against the O12 status"),
    _t(State.FIRST_SHIFT_CONFIRMED, "day0_no_show", State.NO_SHOW, (ActorKind.TIMER,),
       effects=("notify_manager_no_show",),
       description="row 27: day-0 no-show after confirmation"),
    # Timer-driven rows (declarative timer definitions below dispatch them)
    _t(State.CONTACTED, "no_reply_nudge_1", State.CONTACTED, (ActorKind.TIMER,),
       effects=("send_nudge",),
       description="T1: nudge at 2 h unanswered"),
    _t(State.CONTACTED, "no_reply_nudge_2", State.CONTACTED, (ActorKind.TIMER,),
       effects=("send_nudge",),
       description="T1: nudge at 24 h unanswered"),
    _t(State.CONTACTED, "no_reply_benched", State.BENCHED, (ActorKind.TIMER,),
       effects=("add_bench_entry",),
       description="T1/row 5: bench at 48 h with re-engagement consent flag"),
    _t(State.INTERVIEW_BOOKED, "interview_reminder_24h", State.INTERVIEW_BOOKED, (ActorKind.TIMER,),
       effects=("send_interview_reminder",),
       description="T2: reminder 24 h before the slot"),
    _t(State.INTERVIEW_BOOKED, "interview_reminder_2h", State.INTERVIEW_BOOKED, (ActorKind.TIMER,),
       effects=("send_interview_reminder",),
       description="T2: reminder 2 h before the slot"),
    _t(State.PENDING_MANAGER_DECISION, "manager_decision_remind", State.PENDING_MANAGER_DECISION,
       (ActorKind.TIMER,),
       effects=("remind_manager_decision",),
       description="T3: SLA remind at 2 h"),
    _t(State.PENDING_MANAGER_DECISION, "manager_decision_escalate", State.PENDING_MANAGER_DECISION,
       (ActorKind.TIMER,),
       effects=("escalate_to_hrbp",),
       description="T3: escalate to the area HRBP at 8 h (H5)"),
    _t(
        State.FIRST_SHIFT_SCHEDULED, "confirmation_cutoff", State.FIRST_SHIFT_SCHEDULED,
        (ActorKind.TIMER,),
        guards=("first_shift_unconfirmed",),
        effects=("activate_backup",),
        description="T4: T-18h unconfirmed activates the bench backup (H4)",
    ),
)


@dataclass(frozen=True)
class TimerDef:
    """One declarative timer: offset from an Application anchor field.

    The machine never reads a clock; the caller ticks it with an injected
    ``now`` and the timer fires when ``anchor + offset <= now``.
    """

    key: str
    description: str
    anchor: str
    offset: timedelta
    states: frozenset[State]
    event: str
    condition: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "description": self.description,
            "anchor": self.anchor,
            "offset_hours": self.offset.total_seconds() / 3600,
            "states": sorted(s.value for s in self.states),
            "event": self.event,
            "condition": self.condition,
        }


# --------------------------------------------------------------- result type


@dataclass(frozen=True)
class DispatchResult:
    """Effects of one dispatch, as pure data. Persistence happens outside."""

    transitioned: bool
    application: Application
    from_state: State
    to_state: State | None
    audit_entries: tuple[AuditEntry, ...]
    outbox_messages: tuple[OutboxMessage, ...]
    events: tuple[Event, ...]
    rejection_reason: str | None = None


def _policies() -> Any:
    """Late import so policies.py can import the types defined here."""
    from app.core import policies

    return policies


class StateMachine:
    """Pure dispatcher over the declarative transition table."""

    def dispatch(
        self,
        app: Application,
        event: str,
        actor: Actor,
        now: datetime | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> DispatchResult:
        policies = _policies()
        payload = payload or {}
        row = self._find(app.state, event)
        if row is None:
            return self._rejected(app, f"unknown event '{event}' in state '{app.state.value}'")
        if actor.kind not in row.actors:
            return self._rejected(
                app, f"actor kind '{actor.kind.value}' not allowed for event '{event}'"
            )
        for guard_name in row.guards:
            guard: GuardFn = policies.GUARDS[guard_name]
            if not guard(app, actor, payload, now):
                return self._rejected(app, f"guard failed: {guard_name}")
        ctx = EffectCtx(app=app, payload=payload, actor=actor, now=now)
        for effect_name in row.effects:
            effect: EffectFn = policies.EFFECTS[effect_name]
            effect(ctx)
        next_app = replace(ctx.app, state=row.to_state)
        timer_key = payload.get("timer")
        if isinstance(timer_key, str):
            next_app = replace(
                next_app, fired_timers=frozenset({*next_app.fired_timers, timer_key})
            )
        audit_entry = AuditEntry(
            application_id=app.application_id,
            at=now,
            actor_kind=actor.kind.value,
            actor_name=actor.name,
            event=event,
            from_state=app.state.value,
            to_state=row.to_state.value,
            details=str(timer_key) if timer_key else "",
        )
        transition_event = Event(
            type="state.transition",
            payload={
                "application_id": app.application_id,
                "event": event,
                "from_state": app.state.value,
                "to_state": row.to_state.value,
                "actor_kind": actor.kind.value,
                "actor_name": actor.name,
                "at": now.isoformat() if now else None,
            },
        )
        return DispatchResult(
            transitioned=True,
            application=next_app,
            from_state=app.state,
            to_state=row.to_state,
            audit_entries=(audit_entry, *ctx.audit_entries),
            outbox_messages=tuple(ctx.outbox_messages),
            events=(transition_event, *ctx.events),
        )

    def tick(self, app: Application, now: datetime) -> tuple[DispatchResult, ...]:
        """Fire every timer due at the injected ``now``, in declarative order."""
        policies = _policies()
        results: list[DispatchResult] = []
        current = app
        for timer in sorted(policies.TIMER_DEFINITIONS, key=lambda d: d.offset):
            if timer.key in current.fired_timers:
                continue
            if current.state not in timer.states:
                continue
            anchor: datetime | None = getattr(current, timer.anchor)
            if anchor is None:
                continue
            due_at = anchor + timer.offset
            if now < due_at:
                continue
            if timer.condition is not None:
                condition: ConditionFn = policies.CONDITIONS[timer.condition]
                if not condition(current, now):
                    continue
            result = self.dispatch(
                current,
                timer.event,
                Actor(ActorKind.TIMER, timer.key),
                now=now,
                payload={"timer": timer.key, "due_at": due_at.isoformat()},
            )
            results.append(result)
            if result.transitioned:
                current = result.application
        return tuple(results)

    def describe(self) -> dict[str, Any]:
        """Render the table and timers as plain data for GET /api/meta/state-machine."""
        policies = _policies()
        return {
            "states": [s.value for s in State],
            "transitions": [t.as_dict() for t in TRANSITIONS],
            "timers": [t.as_dict() for t in policies.TIMER_DEFINITIONS],
        }

    @staticmethod
    def _find(state: State, event: str) -> Transition | None:
        for row in TRANSITIONS:
            if row.from_state is state and row.event == event:
                return row
        return None

    @staticmethod
    def _rejected(app: Application, reason: str) -> DispatchResult:
        # A rejected dispatch is not a transition: nothing is audited and the
        # stored application data is returned unchanged.
        return DispatchResult(
            transitioned=False,
            application=app,
            from_state=app.state,
            to_state=None,
            audit_entries=(),
            outbox_messages=(),
            events=(),
            rejection_reason=reason,
        )
