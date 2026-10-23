"""Pilot metrics: funnel and KPI cards over the event and audit log.

Formulas follow design/metric-tree.md and evals/metrics.py, computed over
the persisted audit rows and message events (rule: the LLM never computes
metrics; this module is pure persistence reading):

- time to first contact: application.entered_at to the first message.out
  event, median hours,
- interview show rate: interviews attended / interviews booked,
- offer to rota: offer_sent to ready_for_rota, median days,
- day-1 show rate: first shifts worked / first shifts scheduled,
- TTFPS proxy: first contact to first_shift_worked, median days (the
  simulated clock compresses waiting time; this is a comparable proxy, not
  a wall-clock promise).

Honesty rules: a metric with no observed data has value "" (control too),
trend [] unless there are at least two distinct days of data, and the
source string says so. Baselines and targets are the metric tree constants,
never recomputed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.console.schemas import FunnelStage, FunnelSummary, KpiCard, MetricStatus
from app.db.events import Event
from app.db.models import Application, AuditEvent, Candidate

# Pipeline order used by the funnel; states beyond the last stage count as
# reaching it. Side states (benched, withdrawn, not_selected, no_show) stop
# the climb wherever the trail ends.
PIPELINE: tuple[tuple[str, str], ...] = (
    ("applied", "Applied"),
    ("contacted", "First contact"),
    ("screening", "Screening"),
    ("matched", "Matched to a shift"),
    ("interview_booked", "Interview booked"),
)
STATE_RANK: dict[str, int] = {
    "new": 0,
    "contacted": 1,
    "consented": 2,
    "screening": 2,
    "matched": 3,
    "interview_booked": 4,
    "interviewed": 4,
    "pending_manager_decision": 4,
    "offer_sent": 4,
    "offer_accepted": 4,
    "preboarding": 4,
    "ready_for_rota": 4,
    "first_shift_scheduled": 4,
    "first_shift_confirmed": 4,
    "first_shift_worked": 4,
    "active_week1": 4,
    "active_day30": 4,
}

# Metric tree constants (design/metric-tree.md): baseline and target strings
# are quoted values, not computed ones.
KPI_DEFS: tuple[dict[str, str], ...] = (
    {
        "id": "ttfps",
        "label": "Time to first productive shift",
        "unit": "days",
        "baseline": "27.3",
        "target": "14",
        "direction": "down",
    },
    {
        "id": "time_to_first_contact",
        "label": "Time to first contact",
        "unit": "h",
        "baseline": "91.2",
        "target": "1",
        "direction": "down",
    },
    {
        "id": "interview_show_rate",
        "label": "Interview show rate",
        "unit": "%",
        "baseline": "62.0",
        "target": "80",
        "direction": "up",
    },
    {
        "id": "offer_to_rota_days",
        "label": "Offer to on rota",
        "unit": "days",
        "baseline": "7.5",
        "target": "3",
        "direction": "down",
    },
    {
        "id": "day1_show_rate",
        "label": "Day-1 show rate",
        "unit": "%",
        "baseline": "82.1",
        "target": "92",
        "direction": "up",
    },
    {
        "id": "manager_minutes_per_hire",
        "label": "Manager minutes per hire",
        "unit": "min",
        "baseline": "",
        "target": "",
        "direction": "down",
    },
)


@dataclass
class Conversation:
    """Everything one candidate contributes to the metric tree."""

    candidate_id: str
    cohort: str  # "pilot" | "control"
    entered_at: datetime | None
    first_out_at: datetime | None
    states: set[str] = field(default_factory=set)
    state_at: dict[str, datetime] = field(default_factory=dict)


def load_conversations(session: Session) -> list[Conversation]:
    """One conversation per candidate, from applications, audit and events."""
    from app.db.models import Restaurant

    restaurants = {
        row.id: ("pilot" if row.bench_enabled else "control")
        for row in session.scalars(select(Restaurant)).all()
    }
    applications: dict[str, tuple[datetime | None, str]] = {}
    for app, candidate in session.execute(
        select(Application, Candidate).where(Application.candidate_id == Candidate.id)
    ).all():
        restaurant_cohort = restaurants.get(app.restaurant_id, "pilot")
        existing = applications.get(str(candidate.id))
        # One conversation per candidate: the latest application wins.
        if existing is None or (
            app.entered_at is not None
            and existing[0] is not None
            and app.entered_at > existing[0]
        ):
            applications[str(candidate.id)] = (app.entered_at, restaurant_cohort)

    conversations = {
        candidate_id: Conversation(
            candidate_id=candidate_id,
            cohort=cohort,
            entered_at=entered_at,
            first_out_at=None,
        )
        for candidate_id, (entered_at, cohort) in applications.items()
    }
    for candidate_id in applications:
        conversations[candidate_id].states.add("new")

    audits = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.candidate_id.is_not(None))
        .order_by(AuditEvent.occurred_at)
    ).all()
    for row in audits:
        conversation = conversations.get(str(row.candidate_id))
        if conversation is None:
            continue
        if row.state_to:
            conversation.states.add(row.state_to)
            conversation.state_at.setdefault(row.state_to, row.occurred_at)

    events = session.scalars(
        select(Event).where(
            Event.candidate_id.is_not(None), Event.type == "message.out"
        ).order_by(Event.occurred_at)
    ).all()
    for event_row in events:
        conversation = conversations.get(str(event_row.candidate_id))
        if conversation is None:
            continue
        if conversation.first_out_at is None:
            conversation.first_out_at = event_row.occurred_at
    return list(conversations.values())


def _rank(conversation: Conversation) -> int:
    return max((STATE_RANK.get(state, 0) for state in conversation.states), default=0)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _by_cohort(conversations: list[Conversation], cohort: str) -> list[Conversation]:
    return [item for item in conversations if item.cohort == cohort]


def funnel_summary(conversations: list[Conversation]) -> FunnelSummary:
    pilot = _by_cohort(conversations, "pilot")
    control = _by_cohort(conversations, "control")
    stages: list[FunnelStage] = []
    for index, (stage_id, label) in enumerate(PIPELINE):
        stages.append(
            FunnelStage(
                id=stage_id,
                label=label,
                pilot_pct=_share(pilot, index),
                control_pct=_share(control, index),
            )
        )
    if not conversations:
        insight = (
            "No candidate history yet: load a simulator scenario to produce "
            "events; percentages stay 0 until then."
        )
    else:
        insight = (
            f"Share of the {len(pilot)} pilot and {len(control)} control candidates "
            "reaching each stage (metric-tree funnel); applied is 100% by definition."
        )
    return FunnelSummary(
        pilot_candidates=len(pilot),
        control_candidates=len(control),
        stages=stages,
        insight=insight,
    )


def _share(conversations: list[Conversation], stage_index: int) -> float:
    if not conversations:
        return 0.0
    reached = sum(1 for item in conversations if _rank(item) >= stage_index)
    return round(100.0 * reached / len(conversations), 1)


def kpi_cards(conversations: list[Conversation]) -> list[KpiCard]:
    cards: list[KpiCard] = []
    for definition in KPI_DEFS:
        pilot = _metric_value(definition["id"], _by_cohort(conversations, "pilot"))
        control = _metric_value(definition["id"], _by_cohort(conversations, "control"))
        cards.append(
            KpiCard(
                id=definition["id"],
                label=definition["label"],
                value=pilot.value,
                unit=definition["unit"],
                status=_status(pilot.value, definition["target"], definition["direction"]),
                control=control.value,
                baseline=definition["baseline"],
                target=definition["target"],
                source=_source(definition, pilot),
                trend=pilot.trend,
            )
        )
    return cards


@dataclass
class MetricSample:
    value: str = ""
    n: int = 0
    trend: list[float] = field(default_factory=list)
    detail: str = ""


def _metric_value(kpi_id: str, conversations: list[Conversation]) -> MetricSample:
    if kpi_id == "manager_minutes_per_hire":
        # Not collected anywhere yet (metric tree: "No per-hire measure
        # exists"). The pilot instruments it from week 1.
        return MetricSample(detail="not collected yet")

    if kpi_id in ("ttfps", "offer_to_rota_days"):
        values: list[float] = []
        for item in conversations:
            start = (
                item.first_out_at
                if kpi_id == "ttfps"
                else item.state_at.get("offer_sent")
            )
            end = (
                item.state_at.get("first_shift_worked")
                if kpi_id == "ttfps"
                else item.state_at.get("ready_for_rota")
            )
            if start is not None and end is not None:
                values.append((end - start).total_seconds() / 86400)
        return _days_sample(values, conversations, kpi_id)

    if kpi_id == "time_to_first_contact":
        hours = [
            (item.first_out_at - item.entered_at).total_seconds() / 3600
            for item in conversations
            if item.first_out_at is not None and item.entered_at is not None
        ]
        median = _median(hours)
        if median is None:
            return MetricSample(detail="no conversation has an outbound message yet")
        return MetricSample(
            value=f"{median:.1f}", n=len(hours), detail=f"median of {len(hours)} conversations"
        )

    if kpi_id in ("interview_show_rate", "day1_show_rate"):
        booked_state = (
            "interview_booked" if kpi_id == "interview_show_rate" else "first_shift_scheduled"
        )
        attended_state = (
            "interviewed" if kpi_id == "interview_show_rate" else "first_shift_worked"
        )
        booked = [item for item in conversations if booked_state in item.states]
        attended = [item for item in booked if attended_state in item.states]
        if not booked:
            return MetricSample(detail=f"no candidate reached {booked_state}")
        pct = round(100.0 * len(attended) / len(booked), 1)
        trend = _daily_rate_trend(booked, attended_state, booked_state)
        return MetricSample(
            value=f"{pct:.1f}", n=len(booked), trend=trend, detail=f"{len(attended)}/{len(booked)}"
        )

    return MetricSample(detail="unknown metric")  # pragma: no cover


def _days_sample(
    values: list[float], conversations: list[Conversation], kpi_id: str
) -> MetricSample:
    median = _median(values)
    if median is None:
        return MetricSample(detail="no conversation reached the end state")
    trend = _daily_median_trend(conversations, kpi_id)
    return MetricSample(
        value=f"{median:.1f}", n=len(values), trend=trend, detail=f"median of {len(values)}"
    )


def _daily_points(
    conversations: list[Conversation], kpi_id: str
) -> dict[date, list[float]]:
    """Per-day observed values for one metric, keyed by the end-event day."""
    points: dict[date, list[float]] = defaultdict(list)
    for item in conversations:
        if kpi_id == "ttfps":
            start, end = item.first_out_at, item.state_at.get("first_shift_worked")
            divisor = 86400.0
        elif kpi_id == "offer_to_rota_days":
            start, end = item.state_at.get("offer_sent"), item.state_at.get("ready_for_rota")
            divisor = 86400.0
        elif kpi_id == "time_to_first_contact":
            start, end = item.entered_at, item.first_out_at
            divisor = 3600.0
        else:
            continue
        if start is None or end is None:
            continue
        points[end.date()].append((end - start).total_seconds() / divisor)
    return points


def _daily_median_trend(conversations: list[Conversation], kpi_id: str) -> list[float]:
    points = _daily_points(conversations, kpi_id)
    if len(points) < 2:
        return []  # no multi-day history: an empty sparkline, said so in source
    medians = (_median(values) for values in points.values())
    return [round(value, 2) for value in medians if value is not None][-7:]


def _daily_rate_trend(
    booked: list[Conversation], attended_state: str, booked_state: str
) -> list[float]:
    by_day: dict[date, list[Conversation]] = defaultdict(list)
    for item in booked:
        day = item.state_at.get(booked_state)
        if day is not None:
            by_day[day.date()].append(item)
    if len(by_day) < 2:
        return []
    values = [
        round(100.0 * sum(1 for c in day_group if attended_state in c.states) / len(day_group), 1)
        for day, day_group in sorted(by_day.items())
    ]
    return values[-7:]


def _status(value: str, target: str, direction: str) -> MetricStatus:
    if value == "" or target == "":
        # Unknown is never presented as on target.
        return "below_target"
    number = float(value)
    goal = float(target)
    if direction == "up":
        return "on_target" if number >= goal else "below_target"
    return "on_target" if number <= goal else "below_target"


def _source(definition: dict[str, str], sample: MetricSample) -> str:
    base = f"/api/metrics/kpis - {definition['id']}"
    if sample.value == "":
        return f"{base} ({sample.detail or 'no observed data yet'})"
    return f"{base} ({sample.detail}; baseline and target from design/metric-tree.md)"
