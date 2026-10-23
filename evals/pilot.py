"""Simulated pilot (T1-T2, S1, S2): 30 simulated days over the 12 pilot
restaurants on the real pipeline, against a 3-restaurant as-is control model.

Spec source: specs/05-iteration-evals.md section 5, verbatim: "Run the full
system over the 12 pilot restaurants for a simulated 30 days (clock
fast-forward) with persona arrival rates matching the client's seasonality,
and compare with the 3 control restaurants running the 'as-is' process model
from discovery. Produce docs/pilot-sim-day30.md in the format of a real
weekly ops review: headline numbers vs baseline, what went wrong, top
escalations, decisions needed from the client." And: "State its limits
plainly: this is a simulation with synthetic behavior, useful to find failure
modes and to size impact, not proof of real-world effect."

Two arms:

- **Pilot arm, real pipeline.** Every arrival is a generated persona driven
  through ``evals.run.drive_conversation``: the real HireDesk webhook, the
  real sim runner, timers and state machine, the scripted offline model. No
  deterministic check is weakened: any failing check stops the run with exit
  code 2 before any artifact is written.
- **Control arm, a statistical model, clearly labelled.** The as-is process
  is NOT run as code (there is no as-is code to run): it is sampled from the
  discovery funnel (`discovery/funnel-baseline.md`) with a seeded RNG. Its
  arithmetic is pinned by tests to reproduce the discovery baselines within
  a stated tolerance (5 percentage points on conversions, 1.0 day on
  medians, the same tolerance funnel-baseline.md uses against the brief).

Seasonality: arrivals are drawn per restaurant-day as a Poisson process
whose rate carries the client's summer shape (brief section 1: coastal units
add 25% to 40% headcount from June to September): a linear summer ramp from
1.0x to 1.4x across the window, and a weekend uplift (store-footfall QR
applications) of 1.6x.

Determinism: one seeded RNG per concern (pilot arrivals, control arrivals,
control model, persona bundle); the pipeline itself is scripted and
deterministic, so a given seed and day count reproduce the same counts.

CLI: ``uv run python -m evals.pilot --days 30 --seed 42 --label day30``
writes ``docs/pilot-sim-<label>.{json,md}``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from evals.checks.deterministic import run_deterministic_checks
from evals.metrics import ESCALATION_EVENTS, cost_latency, fairness, funnel, median, task_success
from evals.personas.generate import _fitting_shift_ids, generate_personas
from evals.personas.schema import Persona
from evals.run import _ensure_seed, drive_conversation, eval_engine
from mocks.services.seed import load_restaurants

DEFAULT_OUT_DIR = Path("docs")

# --------------------------------------------------------------- seasonality

# A Monday: the start of the summer hiring window the pilot models.
PILOT_START = date(2025, 6, 2)
# 4,500 applications / 15 restaurants / ~180 days is about 1.7; the pilot
# window uses 1.5 per restaurant-day as the summer low-season floor.
BASE_ARRIVALS_PER_RESTAURANT_DAY = 1.5
# Weekend store footfall drives QR applications; weekend days multiply the
# base rate. The uplift is a stated modelling choice, not a measured rate.
WEEKEND_MULTIPLIER = 1.6
# Brief section 1: coastal units add 25% to 40% headcount June to September.
# The window ramps linearly to the top of that band.
SUMMER_RAMP_END = 1.4

PILOT_RESTAURANT_IDS: list[str] = [
    r.restaurant_id for r in load_restaurants() if r.is_pilot
]
CONTROL_RESTAURANT_IDS: list[str] = [
    r.restaurant_id for r in load_restaurants() if not r.is_pilot
]

# Control-arm cost anchor: the group's own cost per hire (brief section 4).
CONTROL_COST_PER_HIRE_EUR = 420

CAVEAT_STATEMENT = (
    "this is a simulation with synthetic behavior, useful to find failure "
    "modes and to size impact, not proof of real-world effect"
)
CAVEAT_LINE = f"Simulation caveat: {CAVEAT_STATEMENT}."


@dataclass(frozen=True)
class Arrival:
    """One application arriving at one restaurant on one simulated day."""

    day_index: int
    restaurant_id: str
    weekend: bool


def _poisson(rng: random.Random, lam: float) -> int:
    """One Poisson draw (Knuth), deterministic for a seeded RNG."""
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def arrival_multiplier(day_index: int, days: int, weekend: bool) -> float:
    """The seasonal rate multiplier for one simulated day."""
    ramp = 1.0 + (SUMMER_RAMP_END - 1.0) * (day_index / max(days - 1, 1))
    return WEEKEND_MULTIPLIER * ramp if weekend else ramp


def build_arrival_schedule(
    days: int, restaurant_ids: list[str], rng: random.Random
) -> list[Arrival]:
    """Every application arriving across the window, day by restaurant.

    Deterministic for a given seed, day count and restaurant list.
    """
    schedule: list[Arrival] = []
    for day_index in range(days):
        weekend = (PILOT_START + timedelta(days=day_index)).weekday() >= 5
        for restaurant_id in restaurant_ids:
            expected = (
                BASE_ARRIVALS_PER_RESTAURANT_DAY
                * arrival_multiplier(day_index, days, weekend)
            )
            for _ in range(_poisson(rng, expected)):
                schedule.append(Arrival(day_index, restaurant_id, weekend))
    return schedule


# ------------------------------------------------------------- control model


@dataclass(frozen=True)
class ControlRates:
    """The as-is funnel, stage by stage, from discovery/funnel-baseline.md.

    Defaults are the seeded discovery dataset's conversions (seed 42, 4,500
    applications) and stage medians; they match the brief baselines inside
    the stated tolerance (conversions within 5 pp, medians within 1.0 day).
    """

    contact_rate: float = 0.590
    days_to_contact: float = 3.9
    screen_rate: float = 0.75
    days_to_screen: float = 2.0
    schedule_rate: float = 0.70
    days_to_interview: float = 4.3
    attend_rate: float = 0.62
    days_to_attend: float = 5.0
    offer_rate: float = 0.60
    days_to_offer: float = 3.1
    docs_rate: float = 0.849
    days_to_docs: float = 2.4
    rota_rate: float = 0.90
    days_to_rota: float = 5.1
    day1_rate: float = 0.821
    days_to_day1: float = 1.5

    @property
    def total_median_days(self) -> float:
        """Median days, application to first worked shift (sum of medians,
        the same approximation funnel-baseline.md uses: about 27.3)."""
        return round(
            self.days_to_contact
            + self.days_to_screen
            + self.days_to_interview
            + self.days_to_attend
            + self.days_to_offer
            + self.days_to_docs
            + self.days_to_rota
            + self.days_to_day1,
            1,
        )

    @property
    def applied_to_day1_rate(self) -> float:
        """Share of applicants that become a first worked shift (7.2%)."""
        return round(
            self.contact_rate
            * self.screen_rate
            * self.schedule_rate
            * self.attend_rate
            * self.offer_rate
            * self.docs_rate
            * self.rota_rate
            * self.day1_rate,
            4,
        )


DISCOVERY_BASELINE = ControlRates()
# Per-stage timing jitter: uniform +/-50% around each stage median, so the
# sampling stays stochastic while every stage (and therefore every sum) keeps
# the baseline median exactly.
JITTER_HALF = 0.5


@dataclass(frozen=True)
class ControlSummary:
    """The as-is model's outcome over one window of arrivals."""

    arrivals: int
    contacted: int
    scheduled_interviews: int
    attended_interviews: int
    offers: int
    hires: int
    contact_rate: float
    median_days_to_contact: float
    interview_show_rate: float
    day1_show_rate: float
    median_days_application_to_first_shift: float


def simulate_control_arm(
    arrival_count: int,
    rates: ControlRates = DISCOVERY_BASELINE,
    *,
    rng: random.Random,
) -> ControlSummary:
    """Sample the as-is process once per arrival with a seeded RNG.

    This is a model of the as-is process, not a run of any real code: each
    candidate walks the discovery funnel stage by stage (a Bernoulli draw per
    stage conversion, a jittered stage duration around each median). Stages
    are the funnel's own: contact, screen, schedule, attend, offer,
    documents, rota, first shift.
    """
    contacted_count = scheduled = attended = offers = rota = hires = 0
    contact_days: list[float] = []
    worked_days: list[float] = []

    for _ in range(arrival_count):
        if rng.random() >= rates.contact_rate:
            continue  # the silent queue: never contacted, never hires
        day = rates.days_to_contact * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        contact_days.append(day)
        contacted_count += 1

        if rng.random() >= rates.screen_rate:
            continue
        day += rates.days_to_screen * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.schedule_rate:
            continue
        scheduled += 1
        day += rates.days_to_interview * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.attend_rate:
            continue
        attended += 1
        day += rates.days_to_attend * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.offer_rate:
            continue
        offers += 1
        day += rates.days_to_offer * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.docs_rate:
            continue
        day += rates.days_to_docs * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.rota_rate:
            continue
        rota += 1
        day += rates.days_to_rota * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        if rng.random() >= rates.day1_rate:
            continue  # hired on paper, never showed up on day 1
        day += rates.days_to_day1 * (1.0 + rng.uniform(-JITTER_HALF, JITTER_HALF))
        worked_days.append(day)
        hires += 1

    return ControlSummary(
        arrivals=arrival_count,
        contacted=contacted_count,
        scheduled_interviews=scheduled,
        attended_interviews=attended,
        offers=offers,
        hires=hires,
        contact_rate=round(contacted_count / arrival_count, 4) if arrival_count else 0.0,
        median_days_to_contact=round(median(contact_days) or 0.0, 2),
        interview_show_rate=round(attended / scheduled, 4) if scheduled else 0.0,
        day1_show_rate=round(hires / rota, 4) if rota else 0.0,
        median_days_application_to_first_shift=round(median(worked_days) or 0.0, 2),
    )


def baseline_violations(
    summary: ControlSummary,
    baseline: ControlRates = DISCOVERY_BASELINE,
    *,
    rate_tolerance: float = 0.05,
    day_tolerance: float = 1.0,
) -> list[str]:
    """Where a control summary misses the baseline rates it claims to model.

    Tolerances mirror funnel-baseline.md: conversions within 5 percentage
    points, medians within 1.0 day. Empty means the model is faithful.
    """
    violations: list[str] = []
    if abs(summary.contact_rate - baseline.contact_rate) > rate_tolerance:
        violations.append(
            f"contact rate {summary.contact_rate} vs baseline {baseline.contact_rate} "
            f"(tolerance {rate_tolerance})"
        )
    if abs(summary.interview_show_rate - baseline.attend_rate) > rate_tolerance:
        violations.append(
            f"interview show rate {summary.interview_show_rate} vs baseline "
            f"{baseline.attend_rate} (tolerance {rate_tolerance})"
        )
    if abs(summary.day1_show_rate - baseline.day1_rate) > rate_tolerance:
        violations.append(
            f"day-1 show rate {summary.day1_show_rate} vs baseline {baseline.day1_rate} "
            f"(tolerance {rate_tolerance})"
        )
    if abs(summary.median_days_to_contact - baseline.days_to_contact) > day_tolerance:
        violations.append(
            f"median days to first contact {summary.median_days_to_contact} vs baseline "
            f"{baseline.days_to_contact} (tolerance {day_tolerance})"
        )
    if (
        abs(summary.median_days_application_to_first_shift - baseline.total_median_days)
        > day_tolerance
    ):
        violations.append(
            f"median days application to first shift "
            f"{summary.median_days_application_to_first_shift} vs baseline "
            f"{baseline.total_median_days} (tolerance {day_tolerance})"
        )
    if abs(summary.hires / summary.arrivals - baseline.applied_to_day1_rate) > 0.02:
        violations.append(
            f"applied-to-day-1 rate {summary.hires / summary.arrivals:.4f} vs baseline "
            f"{baseline.applied_to_day1_rate} (tolerance 0.02)"
        )
    return violations


# ------------------------------------------------------------ persona intake


def assign_personas(schedule: list[Arrival], *, seed: int) -> list[Persona]:
    """One generated persona per arrival, placed at its arrival restaurant.

    The seeded bundle is generated for the arrival volume, then each persona
    is moved to its arrival's restaurant and its ground truth (fitting
    shifts) is recomputed against that restaurant's seeded open shifts, the
    same way `evals.personas.generate` computes it.
    """
    from evals.personas.generate import SHIFT_SEED_DATE
    from mocks.services.seed import generate_open_shifts, load_restaurants

    restaurants = [r for r in load_restaurants() if r.is_pilot]
    all_shifts = generate_open_shifts(restaurants, SHIFT_SEED_DATE, seed=seed)
    shifts_by_restaurant: dict[str, list] = {r.restaurant_id: [] for r in restaurants}
    for shift in all_shifts:
        shifts_by_restaurant[shift.restaurant_id].append(shift)

    personas = generate_personas(seed=seed, count=len(schedule))
    placed: list[Persona] = []
    for index, (persona, arrival) in enumerate(zip(personas, schedule, strict=True)):
        placed.append(
            persona.model_copy(
                update={
                    "restaurant_id": arrival.restaurant_id,
                    "fitting_shift_ids": _fitting_shift_ids(
                        index,
                        persona.profile,
                        persona.availability,
                        arrival.restaurant_id,
                        shifts_by_restaurant,
                    ),
                }
            )
        )
    return placed


# ------------------------------------------------------------ pilot arm runs


ESCALATION_DETAILS: dict[str, str] = {
    "manager_decision_escalate": (
        "Manager decision SLA breached: the decision reminder and escalation "
        "timer fired and a human must decide"
    ),
    "protected_data_refused": (
        "Candidate volunteered protected data; the agent refused to store it "
        "(guardrail G3) and a human may need to follow up"
    ),
}


def _first_state_at(audit, state: str):
    return min(
        (row.occurred_at for row in audit.audit_events if row.state_to == state),
        default=None,
    )


def _first_event_at(audit, event_type: str):
    return min(
        (event.occurred_at for event in audit.events if event.type == event_type),
        default=None,
    )


def _failure_modes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What went wrong, derived from the conversations actually run."""
    modes: list[dict[str, Any]] = []
    final_states = Counter(str(r["final_state"]) for r in records)

    no_show = final_states.get("no_show", 0)
    if no_show:
        modes.append(
            {
                "mode": "day-1 no-show",
                "count": no_show,
                "detail": (
                    "hires whose first shift was scheduled but never worked "
                    "(hidden reliability below the confirm threshold); the "
                    "pipeline booked and prepared them and still lost the day"
                ),
            }
        )
    benched = final_states.get("benched", 0)
    if benched:
        by_behaviour = Counter(
            str(r["persona"].behaviour.value)
            for r in records
            if r["final_state"] == "benched"
        )
        split = ", ".join(f"{k} x{v}" for k, v in sorted(by_behaviour.items()))
        modes.append(
            {
                "mode": "went silent and were benched",
                "count": benched,
                "detail": (
                    f"candidates who stopped replying and hit the graceful "
                    f"endings (48 h bench timer or the no-reply policy); "
                    f"behaviours: {split}"
                ),
            }
        )
    withdrawn = final_states.get("withdrawn", 0)
    if withdrawn:
        modes.append(
            {
                "mode": "withdrew",
                "count": withdrawn,
                "detail": "candidates who dropped out of the process themselves",
            }
        )
    not_selected = final_states.get("not_selected", 0)
    if not_selected:
        modes.append(
            {
                "mode": "not selected by the manager",
                "count": not_selected,
                "detail": "the manager decided against an offer",
            }
        )
    missed = [r for r in records if not r["task_success"]]
    if missed:
        modes.append(
            {
                "mode": "missed ground-truth outcome",
                "count": len(missed),
                "detail": (
                    "personas that did not reach their ground-truth end state: "
                    + "; ".join(
                        f"{r['persona'].persona_id} ({r['persona'].behaviour.value}, "
                        f"expected {r['expected_outcome']}, ended {r['final_state']})"
                        for r in missed[:10]
                    )
                ),
            }
        )
    unrefused = [
        r
        for r in records
        if r["persona"].behaviour.value == "volunteers_protected_info"
        and not any(
            row.event_type == "protected_data_refused" for row in r["audit"].audit_events
        )
    ]
    if unrefused:
        modes.append(
            {
                "mode": "volunteered protected data without a recorded refusal",
                "count": len(unrefused),
                "detail": (
                    "candidates volunteered medical information and no "
                    "protected_data_refused event was recorded: the G3 refusal "
                    "detector's pattern list does not match the volunteered "
                    "wording (medicación, ansiedad, medicação, ansiedade, "
                    "anxiety). The G3 "
                    "storage check still passed (nothing was stored), but the "
                    "designed refusal event is silent on the exact lines the "
                    "persona pool actually sends"
                ),
            }
        )
    return modes


def _decisions(modes: list[dict[str, Any]], escalations: list[dict[str, Any]]) -> list[dict]:
    """Decisions the client must take, each traced to an observed failure
    mode or escalation count. Rendered only when the evidence exists."""
    decisions: list[dict] = []
    counts = {m["mode"]: m["count"] for m in modes}

    decision_escalations = next(
        (e for e in escalations if e["event_type"] == "manager_decision_escalate"), None
    )
    if decision_escalations:
        decisions.append(
            {
                "for": "Marta",
                "decision": (
                    "staff the human decision queue before launch: the agent "
                    "escalates hiring decisions on SLA breach and a human must "
                    "answer inside restaurant opening hours"
                ),
                "evidence": (
                    f"{decision_escalations['count']} decision SLA breaches fired "
                    "in 30 simulated days"
                ),
            }
        )
    protected = next(
        (e for e in escalations if e["event_type"] == "protected_data_refused"), None
    )
    if protected:
        decisions.append(
            {
                "for": "Marta (with the DPO)",
                "decision": (
                    "confirm the refused-data wording the DPO signed off in the "
                    "DPIA: candidates volunteer protected information unprompted "
                    "and the agent declines to store it every time"
                ),
                "evidence": f"{protected['count']} refusals in 30 simulated days",
            }
        )
    unrefused = counts.get("volunteered protected data without a recorded refusal")
    if unrefused:
        decisions.append(
            {
                "for": "Marta (with the DPO)",
                "decision": (
                    "fix the G3 refusal detector before launch as its own task: "
                    "candidates volunteer medical information in words the "
                    "refusal recorder does not match, so the refusal event the "
                    "DPO relies on never fires; nothing is stored today, but "
                    "the audit trail must show every refusal"
                ),
                "evidence": (
                    f"{unrefused} candidates volunteered protected data with no "
                    "recorded refusal in 30 simulated days"
                ),
            }
        )
    if counts.get("day-1 no-show"):
        decisions.append(
            {
                "for": "Raul",
                "decision": (
                    "approve a day-1 confirmation policy: a WhatsApp confirmation "
                    "the day before the first shift plus a same-morning fallback, "
                    "and decide who calls the hires that still go quiet"
                ),
                "evidence": (
                    f"{counts['day-1 no-show']} simulated hires were scheduled, "
                    "prepared and still did not show up on day 1"
                ),
            }
        )
    if counts.get("went silent and were benched"):
        decisions.append(
            {
                "for": "Marta",
                "decision": (
                    "approve the nudge cadence and the bench reuse rule: silence "
                    "is the normal case, not the exception, and the bench only "
                    "has value if managers actually call it"
                ),
                "evidence": (
                    f"{counts['went silent and were benched']} candidates went "
                    "silent mid-process and were benched by the timers"
                ),
            }
        )
    if counts.get("missed ground-truth outcome"):
        decisions.append(
            {
                "for": "Marta and Raul",
                "decision": (
                    "review the conversations that missed their expected outcome "
                    "before the pilot goes live; every trace is replayable"
                ),
                "evidence": f"{counts['missed ground-truth outcome']} conversations",
            }
        )
    return decisions


# ---------------------------------------------------------------- the run


class _null_engine:
    """Context-manager wrapper so an injected test engine needs no copy."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def __enter__(self) -> Engine:
        return self._engine

    def __exit__(self, *exc: object) -> None:
        return None


def run_pilot(
    days: int = 30,
    seed: int = 42,
    label: str = "day30",
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    engine: Engine | None = None,
    log=print,
) -> dict[str, Any]:
    """Run both arms for `days` simulated days and write the ops review.

    Pilot arm: real pipeline (webhook, sim runner, timers, state machine,
    scripted model), one conversation per arrival, every conversation audited
    through the deterministic checks. Control arm: the as-is model sampled
    from the discovery funnel. Deterministic for a given seed and day count.
    """
    started = datetime.now(UTC)
    pilot_rng = random.Random(f"pilot-arrivals:{seed}")
    control_arrival_rng = random.Random(f"control-arrivals:{seed}")
    control_model_rng = random.Random(f"control-model:{seed}")

    schedule = build_arrival_schedule(days, PILOT_RESTAURANT_IDS, pilot_rng)
    control_schedule = build_arrival_schedule(days, CONTROL_RESTAURANT_IDS, control_arrival_rng)
    control_summary = simulate_control_arm(len(control_schedule), rng=control_model_rng)
    personas = assign_personas(schedule, seed=seed)

    def _per_week(counts: list[int]) -> list[int]:
        per_week = [0] * ((days + 6) // 7)
        for day_index in range(days):
            per_week[day_index // 7] += counts[day_index]
        return per_week

    pilot_per_day = [0] * days
    control_per_day = [0] * days
    for arrival in schedule:
        pilot_per_day[arrival.day_index] += 1
    for arrival in control_schedule:
        control_per_day[arrival.day_index] += 1

    with (
        eval_engine() if engine is None else _null_engine(engine)
    ) as eng:
        _ensure_seed(eng, seed)
        records: list[dict[str, Any]] = []
        for persona in personas:
            conversation = drive_conversation(eng, persona)
            audit = conversation["audit"]
            checks = run_deterministic_checks(audit)
            failures = [c for c in checks if not c.passed]
            if failures:
                for check in failures:
                    log(
                        f"DETERMINISTIC CHECK FAILED [{persona.persona_id}] "
                        f"{check.name}: {check.evidence}"
                    )
                log(
                    f"deterministic checks failed ({len(failures)} failure(s)): the "
                    "pilot requires 100%; no report was written"
                )
                raise SystemExit(2)
            success = task_success(persona, audit)
            records.append(
                {
                    "persona": persona,
                    "audit": audit,
                    "final_state": conversation["final_state"],
                    "expected_outcome": success.expected,
                    "task_success": success.achieved,
                }
            )
            log(f"  {persona.persona_id}: {conversation['final_state']}")

        audits = [r["audit"] for r in records]
        funnel_metrics = funnel(audits)
        cost = cost_latency(audits)
        fairness_rows = fairness(personas, audits)

        first_contacts: list[float] = []
        ttfps_days: list[float] = []
        for audit in audits:
            entered = audit.application.entered_at
            first_out = _first_event_at(audit, "message.out")
            if entered is not None and first_out is not None:
                first_contacts.append((first_out - entered).total_seconds() / 60)
            worked_at = _first_state_at(audit, "first_shift_worked")
            if entered is not None and worked_at is not None:
                ttfps_days.append((worked_at - entered).total_seconds() / 86400)

        escalation_counter: Counter[str] = Counter()
        for audit in audits:
            for row in audit.audit_events:
                if row.event_type in ESCALATION_EVENTS or row.event_type in ESCALATION_DETAILS:
                    escalation_counter[row.event_type] += 1
        escalations = [
            {
                "event_type": event_type,
                "count": count,
                "detail": ESCALATION_DETAILS.get(event_type, "escalation to a human"),
            }
            for event_type, count in escalation_counter.most_common()
        ]

        contact_rate = round(len(first_contacts) / len(audits), 4) if audits else 0.0
        final_states = dict(sorted(Counter(str(r["final_state"]) for r in records).items()))
        payload: dict[str, Any] = {
            "meta": {
                "days": days,
                "seed": seed,
                "label": label,
                "generated_at": started.isoformat(timespec="seconds"),
                "window_start": PILOT_START.isoformat(),
                "window_end": (PILOT_START + timedelta(days=days - 1)).isoformat(),
                "pipeline": (
                    "real (evals.run.drive_conversation: HireDesk webhook, sim runner, "
                    "timers, state machine, scripted offline model)"
                ),
            },
            "arrivals": {
                "pilot": len(schedule),
                "control": len(control_schedule),
                "pilot_per_week": _per_week(pilot_per_day),
                "control_per_week": _per_week(control_per_day),
                "base_per_restaurant_day": BASE_ARRIVALS_PER_RESTAURANT_DAY,
                "weekend_multiplier": WEEKEND_MULTIPLIER,
                "summer_ramp_end": SUMMER_RAMP_END,
            },
            "baseline": asdict(DISCOVERY_BASELINE),
            "pilot": {
                "arrivals": len(schedule),
                "contact_rate": contact_rate,
                "median_first_contact_minutes": (
                    round(median(first_contacts), 1) if first_contacts else None
                ),
                "interview_show_rate": funnel_metrics.interview_show_rate,
                "day1_show_rate": funnel_metrics.day1_show_rate,
                "hires": cost.hired,
                "worked_first_shifts": funnel_metrics.worked_first_shifts,
                "ttfps_days_median": round(median(ttfps_days), 2) if ttfps_days else None,
                "cost_per_hire_usd": (
                    round(cost.cost_per_hired_usd, 6)
                    if cost.cost_per_hired_usd is not None
                    else None
                ),
                "total_cost_usd": round(cost.total_usd, 6),
                "task_success_rate": (
                    round(sum(1 for r in records if r["task_success"]) / len(records), 4)
                    if records
                    else 0.0
                ),
                "final_states": final_states,
            },
            "control": {
                "model": (
                    "statistical model of the as-is process sampled from "
                    "discovery/funnel-baseline.md (seeded, not a run of the real code)"
                ),
                "arrivals": control_summary.arrivals,
                "contact_rate": control_summary.contact_rate,
                "median_days_to_contact": control_summary.median_days_to_contact,
                "interview_show_rate": control_summary.interview_show_rate,
                "day1_show_rate": control_summary.day1_show_rate,
                "hires": control_summary.hires,
                "median_days_application_to_first_shift": (
                    control_summary.median_days_application_to_first_shift
                ),
                "cost_per_hire_eur": CONTROL_COST_PER_HIRE_EUR,
                "baseline_violations": baseline_violations(control_summary),
            },
            "deterministic_checks": {
                "failing": 0,
                "checked": len(records),
            },
            "failure_modes": _failure_modes(records),
            "escalations": escalations,
            "fairness": [asdict(row) for row in fairness_rows],
            "decisions": _decisions(_failure_modes(records), escalations),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"pilot-sim-{label}.json"
    md_path = out_dir / f"pilot-sim-{label}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    log(f"wrote {json_path} and {md_path}")
    return payload


# ------------------------------------------------------------------ report


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _days(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} days"


def render_markdown(payload: dict[str, Any]) -> str:
    """The weekly ops review, generated from the run payload so every number
    in the document traces to the JSON artifact next to it."""
    meta = payload["meta"]
    pilot = payload["pilot"]
    control = payload["control"]
    baseline = payload["baseline"]
    arrivals = payload["arrivals"]
    discovery = DISCOVERY_BASELINE

    lines: list[str] = [
        f"# FirstShift simulated pilot: day-{meta['days']} ops review "
        f"(Lumbre Burger Group, weeks 1-{(meta['days'] + 6) // 7})",
        "",
        f"Simulated window {meta['window_start']} to {meta['window_end']} "
        f"({meta['days']} days, seed {meta['seed']}, label {meta['label']}). "
        f"Pilot arm: {arrivals['pilot']} applications across the 12 pilot "
        "restaurants through the real pipeline (HireDesk webhook, sim runner, "
        "timers, state machine, scripted offline model). Control arm: "
        f"{arrivals['control']} applications across the 3 control restaurants "
        "through a statistical model of the as-is process sampled from "
        "`discovery/funnel-baseline.md`; the control is a model, not a run of "
        "real code. Arrivals carry the summer shape: a linear ramp to "
        f"{arrivals['summer_ramp_end']}x across the window and a "
        f"{arrivals['weekend_multiplier']}x weekend uplift. Weekly pilot "
        f"arrivals: {arrivals['pilot_per_week']}.",
        "",
        "## Headline numbers",
        "",
        f"> {CAVEAT_LINE} Every number below is a simulated outcome.",
        "",
        "| metric | pilot (real pipeline) | control (as-is model) | discovery baseline |",
        "| --- | --- | --- | --- |",
        f"| Applications in window | {pilot['arrivals']} | {control['arrivals']} | "
        f"4,500 over 6 months |",
        f"| Contact rate | {_pct(pilot['contact_rate'])} | {_pct(control['contact_rate'])} | "
        f"{_pct(baseline['contact_rate'])} |",
        f"| Median time to first contact | "
        f"{pilot['median_first_contact_minutes']:.0f} min | "
        f"{_days(control['median_days_to_contact'])} | "
        f"{_days(discovery.days_to_contact)} (brief: 3.8) |",
        f"| Interview show rate | {_pct(pilot['interview_show_rate'])} | "
        f"{_pct(control['interview_show_rate'])} | {_pct(baseline['attend_rate'])} |",
        f"| Day-1 show rate | {_pct(pilot['day1_show_rate'])} | "
        f"{_pct(control['day1_show_rate'])} | {_pct(baseline['day1_rate'])} |",
        f"| First shifts worked | {pilot['worked_first_shifts']} | {control['hires']} | "
        f"325 of 4,500 (7.2%) |",
        f"| Median days, application to first worked shift (TTFPS proxy) | "
        f"{_days(pilot['ttfps_days_median'])} | "
        f"{_days(control['median_days_application_to_first_shift'])} | "
        f"{discovery.total_median_days} |",
        f"| Cost per hire | {pilot['cost_per_hire_usd']} USD agent cost "
        "(scripted-model tokens; human cost extra) | "
        f"{control['cost_per_hire_eur']} EUR human cost, no agent | "
        f"{CONTROL_COST_PER_HIRE_EUR} EUR (brief section 4) |",
        f"| Deterministic check failures | "
        f"{payload['deterministic_checks']['failing']} of "
        f"{payload['deterministic_checks']['checked']} conversations | n/a (model) | n/a |",
        "",
        "The TTFPS proxy compares simulated clocks, not wall-clock promises: the "
        "pilot arm compresses the scheduling and preboarding waits the design "
        "targets (documents pre-collected, Nómina360 creation tracked), which is "
        "exactly the gap discovery measured at 5.1 median days.",
        "",
    ]
    if control["baseline_violations"]:
        lines += [
            "Control sampling note: at "
            f"{control['arrivals']} arrivals the 5 percentage-point tolerance is "
            "tighter than the sampling noise of the small control window. The "
            "model is pinned against the discovery volume (4,500 applications), "
            "where it reproduces every baseline within tolerance (see "
            "tests/test_pilot_sim.py). This window's flags, kept visible rather "
            "than tuned away:",
            "",
        ]
        lines += [f"- {violation}" for violation in control["baseline_violations"]]
        lines.append("")

    lines += [
        "## What went wrong",
        "",
        f"> {CAVEAT_LINE} Failure modes are the ones the simulation actually "
        "produced, with counts.",
        "",
    ]
    modes = payload["failure_modes"]
    if modes:
        for mode in modes:
            detail = mode["detail"]
            lines.append(
                f"- **{mode['mode']}: {mode['count']}.** "
                f"{detail[0].upper()}{detail[1:]}."
            )
    else:
        lines.append("- No failure mode reached a count in this window.")
    lines += [
        "",
        "Two structural caveats the simulation itself creates: every booked "
        "interview is attended (the simulated world confirms attendance, so the "
        "38% interview no-show problem is only visible in the control model), "
        "and the persona pool's hidden reliability was drawn for evaluation "
        "coverage, not calibrated to the client's applicant pool, so the pilot "
        "arm's absolute day-1 show rate is not directly comparable to the "
        "baseline.",
        "",
    ]

    lines += [
        "## Top escalations",
        "",
        f"> {CAVEAT_LINE} Counts come from the persisted audit trail.",
        "",
        "| escalation | count | what it means |",
        "| --- | --- | --- |",
    ]
    if payload["escalations"]:
        for escalation in payload["escalations"]:
            lines.append(
                f"| `{escalation['event_type']}` | {escalation['count']} | "
                f"{escalation['detail']} |"
            )
    else:
        lines.append("| none | 0 | no escalation fired in this window |")
    lines.append("")

    lines += [
        "## Fairness",
        "",
        f"> {CAVEAT_LINE} Groups are synthetic proxies (language for the "
        "nationality group, profile for the age band); four-fifths rule at 0.8.",
        "",
        "| dimension | group | n | selected | rate | ratio | flagged |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["fairness"]:
        lines.append(
            f"| {row['dimension']} | {row['group']} | {row['n']} | {row['selected']} | "
            f"{row['rate']:.2f} | {row['ratio']:.2f} | "
            f"{'REVIEW' if row['flagged'] else ''} |"
        )
    flagged = [row for row in payload["fairness"] if row["flagged"]]
    if flagged:
        lines.append("")
        lines.append(
            "Flagged groups need an explanation and an action before any "
            "scale-up decision (metric tree, fairness guardrail)."
        )
    lines.append("")

    lines += [
        "## Decisions needed from the client",
        "",
        "Each decision below is traced to a count the simulation produced; "
        "nothing here is hypothetical.",
        "",
    ]
    if payload["decisions"]:
        for decision in payload["decisions"]:
            lines.append(
                f"- **{decision['for']}:** {decision['decision']} "
                f"(evidence: {decision['evidence']})."
            )
    else:
        lines.append("- No observed failure mode requires a client decision in this window.")
    lines.append("")

    lines += [
        "## Limits of this simulation",
        "",
        f"{CAVEAT_LINE}",
        "",
        "- The candidate side is synthetic: personas, hidden reliability and "
        "arrival rates are modelled, not measured, and the arrival volume is "
        "scaled to the pilot window rather than the six-month discovery "
        "dataset.",
        "- The manager side is scripted: approvals are instant, interviews are "
        "always attended, and documents complete on request, so the pilot arm "
        "cannot reproduce the human bottlenecks discovery found.",
        "- The control arm is a statistical model of the as-is funnel, "
        "faithful to the baseline rates within tolerance and labelled as a "
        "model throughout; it is not a run of the real code.",
        "- Cohorts arriving late in the window are followed to their terminal "
        "state, so late-window outcomes assume the pipeline they met would "
        "have run to completion, the same full-maturation caveat the "
        "discovery dataset carries.",
        "- What the simulation is for: to find failure modes, size impact, "
        "and force the client decisions above before a real candidate is "
        "contacted.",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.pilot",
        description=(
            "Run the simulated pilot (specs/05-iteration-evals.md section 5) and "
            "write docs/pilot-sim-<label>.{json,md}."
        ),
    )
    parser.add_argument("--days", type=int, default=30, help="simulated days of arrivals")
    parser.add_argument("--seed", type=int, default=42, help="arrival and persona seed")
    parser.add_argument("--label", default="day30", help="artifact label, e.g. day30")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    run_pilot(days=args.days, seed=args.seed, label=args.label, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
