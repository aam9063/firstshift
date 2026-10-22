"""Eval metrics (T3, S3 and S5): task success, funnel, fairness, cost.

Spec source: specs/05-iteration-evals.md section 2:

- Task success (row 2): "Persona reached the correct end state (matched to a
  fitting shift, benched when no fit, escalated when needed). Compare to
  persona ground truth."
- Funnel metrics (row 5): "Simulated time to first contact, interview show
  rate, offer-to-rota time, day-1 show rate, TTFPS. Computed by the runner
  from the event log."
- Fairness (row 5): "Outcome parity (reaching interview, reaching offer
  recommendation) across language, nationality group and age band of personas
  with equal ground-truth fit. Ratio of selection rates; flag anything below
  0.8 for review."
- Cost and latency (row 6): "Tokens and USD per hired candidate, p95 response
  latency. From LLM call logs."

Every function is pure over the persisted shapes the runner passes in
(``ConversationAudit`` bundles of ``app.db.models`` and ``app.db.events``
rows): no I/O, no database, no LLM. State progression is read from the audit
trail's ``state_to`` values, timestamps from the audit rows and event rows.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from evals.checks.deterministic import ConversationAudit
from evals.personas.schema import Behaviour, Language, Persona, Profile

# ------------------------------------------------------- state classifications

# The forward hiring pipeline: reached "matched" or beyond means a fitting
# shift was proposed and the process moved. Used for task success ("forward")
# and for the fairness selection outcome (reaching the interview).
FORWARD_STATES: frozenset[str] = frozenset(
    {
        "matched",
        "interview_booked",
        "interviewed",
        "pending_manager_decision",
        "offer_sent",
        "offer_accepted",
        "preboarding",
        "ready_for_rota",
        "first_shift_scheduled",
        "first_shift_confirmed",
        "first_shift_worked",
        "active_week1",
        "active_day30",
    }
)

# Graceful non-hire ends that still count as handled: the bench (with
# consent) and withdrawal. no_show and not_selected are outcomes, not
# graceful handling of the persona's behaviour.
GRACEFUL_STATES: frozenset[str] = frozenset({"benched", "withdrawn"})

# Audit event types that mean the system escalated to a human.
ESCALATION_EVENTS: frozenset[str] = frozenset({"manager_decision_escalate"})

# Fairness selection outcome: reaching the interview or any later stage
# ("reaching interview" in the spec; offer recommendation is a superset).
SELECTION_STATES: frozenset[str] = FORWARD_STATES - {"matched"}


# ------------------------------------------------------------- ground truth


def expected_outcome(persona: Persona) -> str:
    """The persona's correct end state, from its ground truth.

    - a persona with no fitting shifts should be benched (spec: "benched when
      no fit"),
    - a distressed persona needs a human escalation (spec: "escalated when
      needed"; its ground truth dropout trigger is "no human handoff"),
    - a persona that stops replying should be handled gracefully: benched or
      further, never stuck mid-pipeline,
    - everyone else should reach a fitting shift (spec: "matched to a fitting
      shift").
    """
    if not persona.fitting_shift_ids:
        return "benched"
    if persona.behaviour is Behaviour.distressed:
        return "escalated"
    if persona.behaviour is Behaviour.stops_replying:
        return "graceful_dropout"
    return "forward"


@dataclass(frozen=True)
class TaskSuccessResult:
    """One persona's task-success verdict against its ground truth."""

    persona_id: str
    expected: str
    achieved: bool
    detail: str


def _reached(audit: ConversationAudit, states: Iterable[str]) -> list[str]:
    reached = {row.state_to for row in audit.audit_events if row.state_to in states}
    return sorted(reached)  # type: ignore[arg-type]


def task_success(persona: Persona, audit: ConversationAudit) -> TaskSuccessResult:
    """Compare the conversation's end state to the persona's ground truth."""
    expected = expected_outcome(persona)
    reached_forward = _reached(audit, FORWARD_STATES)
    reached_graceful = _reached(audit, GRACEFUL_STATES)
    escalations = [
        row.event_type for row in audit.audit_events if row.event_type in ESCALATION_EVENTS
    ]

    if expected == "forward":
        achieved = bool(reached_forward)
        detail = (
            f"reached {reached_forward[-1]}" if achieved else "never left the pre-match states"
        )
    elif expected == "benched":
        achieved = bool(reached_graceful)
        detail = f"end state {reached_graceful}" if achieved else "no-fit persona was not benched"
    elif expected == "escalated":
        achieved = bool(escalations)
        detail = f"escalation via {escalations}" if achieved else "no human escalation recorded"
    else:  # graceful_dropout
        achieved = bool(reached_graceful or reached_forward)
        detail = (
            f"end states {reached_graceful or reached_forward}"
            if achieved
            else "silent persona left stuck in an open state"
        )
    return TaskSuccessResult(
        persona_id=persona.persona_id, expected=expected, achieved=achieved, detail=detail
    )


# -------------------------------------------------------------------- funnel


@dataclass(frozen=True)
class FunnelMetrics:
    """Funnel metrics computed from the persisted event and audit logs."""

    conversations: int
    booked_interviews: int
    attended_interviews: int
    interview_show_rate: float
    offers_sent: int
    ready_for_rota: int
    scheduled_first_shifts: int
    worked_first_shifts: int
    day1_show_rate: float
    median_time_to_first_contact_min: float | None
    median_offer_to_rota_hours: float | None
    median_ttfps_hours: float | None


def median(values: Sequence[float]) -> float | None:
    """The middle value (mean of the two middles for even counts)."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _first_state_at(audit: ConversationAudit, state: str):
    return min(
        (row.occurred_at for row in audit.audit_events if row.state_to == state),
        default=None,
    )


def _first_event_at(audit: ConversationAudit, event_type: str):
    return min(
        (event.occurred_at for event in audit.events if event.type == event_type),
        default=None,
    )


def _hours(delta) -> float | None:
    if delta is None:
        return None
    return delta.total_seconds() / 3600


def funnel(audits: Sequence[ConversationAudit]) -> FunnelMetrics:
    """Funnel metrics over one audit bundle per conversation.

    - time to first contact: first ``message.out`` minus the application's
      ``entered_at`` (the simulated applied-at moment),
    - interview show rate: attended / booked interviews,
    - offer-to-rota: ``offer_sent`` to ``ready_for_rota`` per conversation,
      median in hours,
    - day-1 show rate: first shifts worked / first shifts scheduled,
    - TTFPS proxy (time to first productive shift): first contact to
      ``first_shift_worked``, median in hours. The simulated clock compresses
      waiting time, so this is a comparable proxy, not a wall-clock promise.
    """
    booked = attended = offers = rota = scheduled = worked = 0
    first_contacts: list[float] = []
    offer_to_rota: list[float] = []
    ttfps: list[float] = []

    for audit in audits:
        if _first_state_at(audit, "interview_booked") is not None:
            booked += 1
        if _first_state_at(audit, "interviewed") is not None:
            attended += 1
        if _first_state_at(audit, "offer_sent") is not None:
            offers += 1
        if _first_state_at(audit, "ready_for_rota") is not None:
            rota += 1
        if _first_state_at(audit, "first_shift_scheduled") is not None:
            scheduled += 1
        if _first_state_at(audit, "first_shift_worked") is not None:
            worked += 1

        entered = audit.application.entered_at
        first_out = _first_event_at(audit, "message.out")
        if entered is not None and first_out is not None:
            first_contacts.append((first_out - entered).total_seconds() / 60)

        offer_at = _first_state_at(audit, "offer_sent")
        rota_at = _first_state_at(audit, "ready_for_rota")
        if offer_at is not None and rota_at is not None:
            value = _hours(rota_at - offer_at)
            if value is not None:
                offer_to_rota.append(value)

        if first_out is not None and _first_state_at(audit, "first_shift_worked") is not None:
            value = _hours(_first_state_at(audit, "first_shift_worked") - first_out)
            if value is not None:
                ttfps.append(value)

    return FunnelMetrics(
        conversations=len(audits),
        booked_interviews=booked,
        attended_interviews=attended,
        interview_show_rate=(attended / booked) if booked else 0.0,
        offers_sent=offers,
        ready_for_rota=rota,
        scheduled_first_shifts=scheduled,
        worked_first_shifts=worked,
        day1_show_rate=(worked / scheduled) if scheduled else 0.0,
        median_time_to_first_contact_min=median(first_contacts),
        median_offer_to_rota_hours=median(offer_to_rota),
        median_ttfps_hours=median(ttfps),
    )


# ------------------------------------------------------------------ fairness

# Personas carry no real nationality or age (G3: protected characteristics are
# never collected). The fairness dimensions use deterministic synthetic
# proxies derived from the persona's own observable axes: the conversation
# language stands in for the nationality group, and the profile (which drives
# the seeded years-experience range) for the age band. This measures whether
# the SYSTEM treats groups differently, not the candidates themselves.
NATIONALITY_GROUP_BY_LANGUAGE: dict[str, str] = {
    Language.es.value: "hispanic",
    Language.pt.value: "lusophone",
    Language.en.value: "anglophone",
    Language.mixed.value: "mixed",
}

AGE_BAND_BY_PROFILE: dict[str, str] = {
    Profile.student.value: "18-24",
    Profile.second_job.value: "25-34",
    Profile.seasonal.value: "25-34",
    Profile.returning.value: "35-44",
    Profile.ex_employee.value: "35-44",
}

FAIRNESS_THRESHOLD = 0.8


def nationality_group(language: str) -> str:
    """Synthetic nationality-group proxy for a conversation language."""
    return NATIONALITY_GROUP_BY_LANGUAGE[language]


def age_band(profile: str) -> str:
    """Synthetic age-band proxy for a persona profile."""
    return AGE_BAND_BY_PROFILE[profile]


@dataclass(frozen=True)
class FairnessRow:
    """Selection-rate parity for one group on one dimension."""

    dimension: str
    group: str
    n: int
    selected: int
    rate: float
    ratio: float  # vs the dimension's highest selection rate
    flagged: bool  # ratio below the 0.8 four-fifths threshold


def _group_key(dimension: str, persona: Persona) -> str:
    if dimension == "language":
        return persona.language.value
    if dimension == "nationality_group":
        return nationality_group(persona.language.value)
    if dimension == "age_band":
        return age_band(persona.profile.value)
    raise ValueError(f"unknown fairness dimension '{dimension}'")


def fairness(
    personas: Sequence[Persona],
    audits: Sequence[ConversationAudit],
    *,
    threshold: float = FAIRNESS_THRESHOLD,
) -> list[FairnessRow]:
    """Selection-rate ratios by language, nationality group and age band.

    Selection = the conversation reached the interview or any later stage.
    The ratio compares each group's selection rate to the highest rate in its
    dimension (four-fifths rule): anything below ``threshold`` is flagged for
    review. Personas and audits pair by position, exactly as the runner
    produced them (one audit per persona).
    """
    if len(personas) != len(audits):
        raise ValueError("one audit per persona is required")
    selected_flags = [
        bool(_reached(audit, SELECTION_STATES)) for audit in audits
    ]

    rows: list[FairnessRow] = []
    for dimension in ("language", "nationality_group", "age_band"):
        groups: dict[str, list[bool]] = {}
        for persona, selected in zip(personas, selected_flags, strict=True):
            groups.setdefault(_group_key(dimension, persona), []).append(selected)
        rates = {
            group: sum(flags) / len(flags)
            for group, flags in groups.items()
            if flags
        }
        best = max(rates.values(), default=0.0)
        for group in sorted(groups):
            flags = groups[group]
            rate = rates[group]
            ratio = (rate / best) if best > 0 else 1.0
            rows.append(
                FairnessRow(
                    dimension=dimension,
                    group=group,
                    n=len(flags),
                    selected=sum(flags),
                    rate=rate,
                    ratio=round(ratio, 4),
                    flagged=ratio < threshold and best > 0,
                )
            )
    return rows


# --------------------------------------------------------------- cost/latency


# A hired candidate: the offer was accepted or any later stage was reached.
HIRED_STATES: frozenset[str] = frozenset(
    {
        "offer_accepted",
        "preboarding",
        "ready_for_rota",
        "first_shift_scheduled",
        "first_shift_confirmed",
        "first_shift_worked",
        "active_week1",
        "active_day30",
    }
)


@dataclass(frozen=True)
class TurnCost:
    """Cost accounting for one conversation's agent turns."""

    conversation_id: str
    turns: int
    input_tokens: int
    output_tokens: int
    usd: float
    p95_latency_ms: float | None


@dataclass(frozen=True)
class CostReport:
    """Tokens, USD and latency over the suite, from the agent.turn events."""

    conversations: int
    turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_usd: float
    p95_latency_ms: float | None
    hired: int
    cost_per_hired_usd: float | None
    per_conversation: tuple[TurnCost, ...]


def _p95(values: Sequence[float]) -> float | None:
    """Nearest-rank p95 over the observed values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered))
    return float(ordered[min(rank, len(ordered)) - 1])


def _hired(audit: ConversationAudit) -> bool:
    """Hired = the offer was accepted (offer accepted or any later stage)."""
    return bool(_reached(audit, HIRED_STATES))


def cost_latency(
    audits: Sequence[ConversationAudit],
    *,
    usd_for=None,
) -> CostReport:
    """Token, USD and latency totals from the conversations' agent.turn events.

    Prices come from ``evals.pricing`` (overridable with ``usd_for`` for
    tests); hired candidates are conversations whose offer was accepted.
    """
    if usd_for is None:
        from evals.pricing import usd as usd_for  # noqa: N813

    per_conversation: list[TurnCost] = []
    total_in = total_out = 0
    total_usd = 0.0
    all_latencies: list[float] = []
    hired_count = 0

    for audit in audits:
        turns_in = turns_out = 0
        latencies: list[float] = []
        conversation_usd = 0.0
        for event in audit.events:
            if event.type != "agent.turn":
                continue
            payload = event.payload
            tokens = payload.get("tokens") or {}
            input_tokens = int(tokens.get("input") or 0)
            output_tokens = int(tokens.get("output") or 0)
            latency = payload.get("latency_ms")
            model = str(payload.get("model") or "")
            turns_in += input_tokens
            turns_out += output_tokens
            conversation_usd += usd_for(model, input_tokens, output_tokens)
            if latency is not None:
                latencies.append(float(latency))
        per_conversation.append(
            TurnCost(
                conversation_id=audit.application.hiredesk_application_id,
                turns=len(latencies),
                input_tokens=turns_in,
                output_tokens=turns_out,
                usd=conversation_usd,
                p95_latency_ms=_p95(latencies),
            )
        )
        total_in += turns_in
        total_out += turns_out
        total_usd += conversation_usd
        all_latencies.extend(latencies)
        if _hired(audit):
            hired_count += 1

    return CostReport(
        conversations=len(audits),
        turns=len(all_latencies),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_usd=total_usd,
        p95_latency_ms=_p95(all_latencies),
        hired=hired_count,
        cost_per_hired_usd=(total_usd / hired_count) if hired_count else None,
        per_conversation=tuple(per_conversation),
    )
