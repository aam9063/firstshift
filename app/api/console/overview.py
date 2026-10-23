"""Console overview and live feed endpoints (specs/04b-console.md section 2).

- GET /api/overview: one composed payload for the console's OverviewPage.
  KPI cards and the funnel come from app/api/console/metrics.py, attention
  items from the escalations logic, coverage rows from the restaurants
  logic, and the latest audit/event rows are mapped to ActivityItems. The
  clock block (simClock, pilotDay, pilotDaysTotal) comes from the active
  simulator run; without one the response is an honest empty/zero shape and
  the funnel insight says so (never a fabricated day).
- GET /api/live: the live feed for the console's Live page. The health block
  aggregates agent.turn events and dead-lettered outbox rows over a stated
  window; guardrails are one item per deterministic check family that is
  measurable from the audit/event log, and agents carry the prompt version
  read from the app/prompts filenames.

Guardrail note: the families mirror evals/checks/deterministic.py, but they
are computed here over the window's rows with the real app primitives (the
tool allow-list dispatcher, the protected-data patterns, the internal
recipient refs) instead of importing the evals package: evals is outside
`mypy app` (strict) and its modules are not import-clean from app code.
The duplication is intentional and documented per constant.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.tools import ToolDispatcher
from app.api.console.helpers import CONTRACT_ACTOR_TYPE, PILOT_DAYS_TOTAL, state_label
from app.api.console.metrics import funnel_summary, kpi_cards, load_conversations
from app.api.console.read import escalations, list_restaurants
from app.api.console.schemas import (
    ActivityItem,
    AgentInfo,
    CoverageRow,
    GuardrailItem,
    LiveFeedResponse,
    LiveHealth,
    OverviewResponse,
)
from app.api.deps import get_session
from app.core.inbound import PROTECTED_PATTERNS
from app.db.events import Event, EventType
from app.db.models import (
    Application,
    AuditEvent,
    Candidate,
    Decision,
    OutboxMessage,
)
from app.services.scripted import INTERNAL_RECIPIENT_REFS
from app.sim.store import SimRun, get_active_run

router = APIRouter(prefix="/api", tags=["console"])

SessionDep = Annotated[Session, Depends(get_session)]

# ------------------------------------------------------------------ window

LIVE_WINDOW = timedelta(hours=24)
WINDOW_LABEL = "last 24 h"
ACTIVITY_LIMIT = 20

# Hired = offer accepted or any later stage (evals/metrics.py HIRED_STATES;
# duplicated because evals is outside the app package, see module docstring).
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

# Internal outbox identifiers in the candidate's transcript
# (evals/checks/deterministic.py, same patterns, same reason: the F09
# calibration leak "bench.reserve backup" reached a candidate).
_INTERNAL_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bbench[ ._-]reserve[ ._-]backup\b",
        r"\btrainer[ ._-]notify\b",
        r"\bbackup[ ._-]activate\b",
        r"\bwhatsapp[ ._-]out\b",
        r"\bhiredesk[ ._-]stage[ ._-]update\b",
        r"\bshiftgrid[ ._-]write\b",
        r"\b[a-z]+(?:_[a-z]+)+\b",
        r"\b[a-z]+\.[a-z]+\b",
    )
)

PROTECTED_REFUSAL_EVENT = "protected_data_refused"

# The live window's guardrail families, in display order.
GUARDRAIL_FAMILIES: tuple[tuple[str, str], ...] = (
    ("ai_disclosure", "AI disclosure in the first message"),
    ("tool_allow_list", "Tool calls stay in the state allow-list"),
    ("no_offer_without_approval", "No offer without a manager approval"),
    ("protected_data", "No protected data stored or echoed"),
    ("outbound_language", "Outbound language matches the candidate"),
    ("internal_identifiers", "No internal identifiers in candidate messages"),
)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
AGENT_LABELS: dict[str, str] = {
    "recruit": "Recruit",
    "onboard": "Onboard",
    "pulse": "Pulse",
}


# ----------------------------------------------------------------- overview


@router.get("/overview", response_model=OverviewResponse)
def overview(session: SessionDep) -> OverviewResponse:
    run = get_active_run(session)
    conversations = load_conversations(session)
    funnel = funnel_summary(conversations)
    if run is None:
        funnel = funnel.model_copy(
            update={
                "insight": (
                    f"{funnel.insight} No simulator run is loaded: simClock is "
                    "empty and pilotDay is 0; load a scenario in the simulator "
                    "to start one."
                )
            }
        )
    return OverviewResponse(
        sim_clock=_sim_clock(run),
        pilot_day=_pilot_day(run),
        pilot_days_total=PILOT_DAYS_TOTAL if run is not None else 0,
        kpis=kpi_cards(conversations),
        funnel=funnel,
        attention=escalations(session),
        activity=_activity(session),
        coverage=_coverage(session),
    )


def _sim_clock(run: SimRun | None) -> str:
    if run is None:
        return ""
    return (run.base_at + timedelta(seconds=run.clock_offset_seconds)).isoformat()


def _pilot_day(run: SimRun | None) -> int:
    if run is None:
        return 0
    return int(run.clock_offset_seconds // 86400) + 1


def _activity(session: Session) -> list[ActivityItem]:
    audits = (
        session.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .limit(ACTIVITY_LIMIT)
        ).all()
    )
    events = (
        session.scalars(
            select(Event)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(ACTIVITY_LIMIT)
        ).all()
    )
    merged: list[tuple[datetime, str, ActivityItem]] = [
        (row.occurred_at, str(row.id), _audit_activity(row)) for row in audits
    ]
    merged += [(row.occurred_at, str(row.id), _event_activity(row)) for row in events]
    merged.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [item for _, _, item in merged[:ACTIVITY_LIMIT]]


def _audit_activity(row: AuditEvent) -> ActivityItem:
    summary = row.event_type
    if row.state_from and row.state_to:
        summary += (
            f": {state_label(row.state_from).lower()} to "
            f"{state_label(row.state_to).lower()}"
        )
    elif row.state_to:
        summary += f": entered {state_label(row.state_to).lower()}"
    details = row.payload.get("details") if isinstance(row.payload, dict) else None
    if details:
        summary = f"{summary} ({details})"
    return ActivityItem(
        id=str(row.id),
        at=row.occurred_at.isoformat(),
        actor_type=CONTRACT_ACTOR_TYPE.get(row.actor_type, "system"),  # type: ignore[arg-type]
        actor_label=row.actor_id or row.actor_type,
        event_type=row.event_type,
        summary=summary,
        detail_tag=state_label(row.state_to) if row.state_to else None,
    )


def _event_activity(row: Event) -> ActivityItem:
    payload = row.payload or {}
    actor_type: str = "system"
    actor_label = "FirstShift"
    summary = row.type
    detail_tag: str | None = None

    if row.type == EventType.AGENT_TURN.value:
        agent = str(payload.get("agent") or "agent")
        actor_type = "agent"
        actor_label = f"FirstShift {agent}"
        state = str(payload.get("state") or "")
        status = str(payload.get("status") or "ok")
        summary = f"{agent} agent turn in {state} ({status})".replace("  ", " ").strip()
        version = payload.get("prompt_version")
        detail_tag = f"{agent}@{version}" if version else None
    elif row.type == EventType.MESSAGE_OUT.value:
        body = str(payload.get("body") or "")
        summary = _excerpt(body)
        if str(payload.get("sender_type") or "") == "human":
            actor_type = "human"
            actor_label = str(payload.get("role") or "human")
        else:
            actor_type = "agent"
        detail_tag = str(payload.get("language") or payload.get("template") or "") or None
    elif row.type == EventType.MESSAGE_IN.value:
        role = str(payload.get("role") or "candidate")
        text = str(payload.get("text") or payload.get("body") or "")
        summary = _excerpt(text)
        if role == "manager":
            actor_type, actor_label = "human", "Manager"
        elif role == "system":
            actor_type, actor_label = "system", "HireDesk"
        else:
            actor_type, actor_label = "candidate", "Candidate"
    elif row.type == EventType.TOOL_CALL.value:
        tool = str(payload.get("tool") or "")
        status = str(payload.get("status") or "")
        actor_type = "agent"
        summary = f"tool {tool} ({status})" if status else f"tool {tool}"
        detail_tag = tool or None
    elif row.type == EventType.INTEGRATION_WRITE.value:
        port = str(payload.get("port") or "")
        operation = str(payload.get("operation") or "")
        summary = f"write {port} {operation}".strip()
        detail_tag = port or None
    elif row.type == EventType.ESCALATION_CREATED.value:
        summary = _excerpt(str(payload.get("reason") or "escalated to a human"))

    return ActivityItem(
        id=str(row.id),
        at=row.occurred_at.isoformat(),
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_label=actor_label,
        event_type=row.type,
        summary=summary,
        detail_tag=detail_tag,
    )


def _excerpt(text: str, limit: int = 100) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rstrip() + "..."


def _coverage(session: Session) -> list[CoverageRow]:
    return [
        CoverageRow(
            id=row.id,
            restaurant=row.name,
            cohort=row.cohort,
            open_shifts=row.open_shifts,
            covered_pct=row.covered_pct,
            bench=row.bench,
            manager_reply=row.manager_median_reply,
        )
        for row in list_restaurants(session)
    ]


# --------------------------------------------------------------------- live


@router.get("/live", response_model=LiveFeedResponse)
def live_feed(session: SessionDep) -> LiveFeedResponse:
    window_start = datetime.now(UTC) - LIVE_WINDOW
    return LiveFeedResponse(
        health=_health(session, window_start),
        guardrails=_guardrails(session, window_start),
        agents=_agents(),
    )


def _p95(values: list[float]) -> float | None:
    """Nearest-rank p95, mirroring evals/metrics.py::_p95."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered))
    return float(ordered[min(rank, len(ordered)) - 1])


def _health(session: Session, window_start: datetime) -> LiveHealth:
    turns = (
        session.scalars(
            select(Event)
            .where(
                Event.type == EventType.AGENT_TURN.value,
                Event.occurred_at >= window_start,
            )
            .order_by(Event.occurred_at, Event.id)
        ).all()
    )
    latencies: list[float] = []
    reasks = 0
    errors = 0
    total_usd = 0.0
    from evals.pricing import usd as token_usd

    for row in turns:
        payload = row.payload or {}
        tokens = payload.get("tokens") or {}
        input_tokens = int(tokens.get("input") or 0)
        output_tokens = int(tokens.get("output") or 0)
        latency = payload.get("latency_ms")
        if latency is not None:
            latencies.append(float(latency))
        if int(payload.get("validation_retries") or 0) > 0:
            reasks += 1
        if payload.get("status") not in (None, "ok"):
            errors += 1
        total_usd += token_usd(str(payload.get("model") or ""), input_tokens, output_tokens)

    dlq = session.scalar(
        select(func.count())
        .select_from(OutboxMessage)
        .where(OutboxMessage.status == "failed")
    )
    hires = session.scalar(
        select(func.count(func.distinct(AuditEvent.candidate_id))).where(
            AuditEvent.state_to.in_(sorted(HIRED_STATES)),
            AuditEvent.occurred_at >= window_start,
        )
    )
    if turns:
        p95 = _p95(latencies)
        return LiveHealth(
            window_label=WINDOW_LABEL,
            p95_reply_latency=f"{p95:.0f} ms" if p95 is not None else "",
            schema_reasks=str(reasks),
            llm_errors=str(errors),
            outbox_in_dlq=int(dlq or 0),
            cost_per_hire=f"{total_usd / hires:.2f}" if hires else "",
        )
    # No turns in the window: the turn-derived metrics have no data; the DLQ
    # depth is still countable and is reported as a real number.
    return LiveHealth(
        window_label=WINDOW_LABEL,
        p95_reply_latency="",
        schema_reasks="",
        llm_errors="",
        outbox_in_dlq=int(dlq or 0),
        cost_per_hire="",
    )


def _agents() -> list[AgentInfo]:
    agents: list[AgentInfo] = []
    for agent_id, label in AGENT_LABELS.items():
        versions = sorted(PROMPT_DIR.glob(f"{agent_id}.v*.md"))
        if not versions:
            continue  # an agent without a prompt file is not deployed
        stem = versions[-1].stem  # newest version file, e.g. "recruit.v1"
        agents.append(AgentInfo(id=agent_id, label=label, version=stem.split(".", 1)[1]))
    return agents


# --------------------------------------------------------------- guardrails


class _GuardrailAccumulator:
    """Collects checked counts and violations for one guardrail family."""

    def __init__(self, family_id: str, family_label: str) -> None:
        self.family_id = family_id
        self.family_label = family_label
        self.checked = 0
        self.violations: list[str] = []

    def item(self) -> GuardrailItem:
        if self.checked == 0 and not self.violations:
            return GuardrailItem(
                id=self.family_id,
                ok=True,
                label=f"{self.family_label}: no data in window",
            )
        if self.violations:
            evidence = "; ".join(self.violations[:3])
            more = f" (+{len(self.violations) - 3} more)" if len(self.violations) > 3 else ""
            return GuardrailItem(
                id=self.family_id,
                ok=False,
                label=(
                    f"{self.family_label}: {len(self.violations)} violation(s) in "
                    f"window ({evidence}{more})"
                ),
            )
        return GuardrailItem(
            id=self.family_id,
            ok=True,
            label=f"{self.family_label}: {self.checked} checked in window, all clean",
        )


def _guardrails(session: Session, window_start: datetime) -> list[GuardrailItem]:
    events = (
        session.scalars(
            select(Event)
            .where(Event.occurred_at >= window_start)
            .order_by(Event.occurred_at, Event.id)
        ).all()
    )
    audits = (
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.occurred_at >= window_start)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        ).all()
    )
    candidate_ids = {
        row.candidate_id for row in events if row.candidate_id is not None
    } | {
        row.candidate_id for row in audits if row.candidate_id is not None
    }
    candidates: dict[UUID, Candidate] = {
        row.id: row
        for row in (
            session.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))).all()
            if candidate_ids
            else []
        )
    }
    applications: dict[UUID, Application] = {}
    for application in (
        session.scalars(
            select(Application)
            .where(Application.candidate_id.in_(candidate_ids))
            .order_by(Application.entered_at)
        ).all()
        if candidate_ids
        else []
    ):
        applications[application.candidate_id] = application  # later entered_at wins
    per_events: dict[UUID, list[Event]] = defaultdict(list)
    per_audits: dict[UUID, list[AuditEvent]] = defaultdict(list)
    for event_row in events:
        if event_row.candidate_id is not None:
            per_events[event_row.candidate_id].append(event_row)
    for audit_row in audits:
        if audit_row.candidate_id is not None:
            per_audits[audit_row.candidate_id].append(audit_row)

    accumulators = {
        family_id: _GuardrailAccumulator(family_id, label)
        for family_id, label in GUARDRAIL_FAMILIES
    }
    _check_disclosure(session, per_events, window_start, accumulators["ai_disclosure"])
    _check_allow_list(per_events, accumulators["tool_allow_list"])
    _check_offer_approvals(session, audits, accumulators["no_offer_without_approval"])
    _check_protected_data(
        session, candidates, per_events, per_audits, accumulators["protected_data"]
    )
    _check_language(
        session, candidates, per_events, accumulators["outbound_language"]
    )
    _check_internal_identifiers(per_events, accumulators["internal_identifiers"])
    return [accumulators[family_id].item() for family_id, _ in GUARDRAIL_FAMILIES]


def _check_disclosure(
    session: Session,
    per_events: dict[UUID, list[Event]],
    window_start: datetime,
    acc: _GuardrailAccumulator,
) -> None:
    """Conversations that started in the window must disclose being AI in the
    first outbound message (evals check ai_disclosure_first_message)."""
    for candidate_id, rows in per_events.items():
        if not any(row.type == EventType.MESSAGE_OUT.value for row in rows):
            continue
        first = session.scalars(
            select(Event)
            .where(
                Event.candidate_id == candidate_id,
                Event.type == EventType.MESSAGE_OUT.value,
            )
            .order_by(Event.occurred_at, Event.id)
            .limit(1)
        ).first()
        if first is None or first.occurred_at < window_start:
            continue  # conversation started before the window
        acc.checked += 1
        payload = first.payload or {}
        if payload.get("ai_disclosed") is not True and payload.get("template") != "first_message":
            acc.violations.append(
                f"first message at {first.occurred_at} lacks the AI disclosure marker"
            )


def _check_allow_list(
    per_events: dict[UUID, list[Event]], acc: _GuardrailAccumulator
) -> None:
    """tool.call events must sit inside the per-state allow-list (G6), with
    rejected calls the dispatcher would allow flagged as recording errors."""
    dispatcher = ToolDispatcher()
    for rows in per_events.values():
        for row in rows:
            if row.type != EventType.TOOL_CALL.value:
                continue
            acc.checked += 1
            payload = row.payload or {}
            tool = str(payload.get("tool") or "")
            agent = str(payload.get("agent") or "")
            state = str(payload.get("state") or "")
            status = str(payload.get("status") or "")
            if not tool or not agent or not state:
                acc.violations.append(f"malformed tool.call payload at {row.occurred_at}")
                continue
            rejection = dispatcher.validate(tool, agent, state)
            if status == "rejected" and rejection is None:
                acc.violations.append(
                    f"tool '{tool}' logged rejected in state '{state}' but it is permitted"
                )
            elif status in ("ok", "error") and rejection is not None:
                acc.violations.append(
                    f"tool '{tool}' executed with status '{status}' outside the "
                    f"'{state}' allow-list for agent '{agent}'"
                )
            elif status not in ("rejected", "ok", "error"):
                acc.violations.append(
                    f"tool.call for '{tool}' carries unknown status '{status}'"
                )


def _named_human(name: str | None) -> bool:
    """A named human decided: not empty, not an agent/system identity
    (evals/checks/deterministic.py::_named_human semantics)."""
    text = (name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return not (
        lowered.startswith("agent")
        or lowered.startswith("system")
        or lowered.startswith("firstshift")
        or lowered == "timer"
    )


def _check_offer_approvals(
    session: Session, audits: Sequence[AuditEvent], acc: _GuardrailAccumulator
) -> None:
    """Every transition to offer_sent needs a recorded manager approval
    (who, when, facts seen) stored as an offer Decision (INV-1)."""
    offer_rows = [row for row in audits if row.state_to == "offer_sent"]
    acc.checked = len(offer_rows)
    for row in offer_rows:
        approvals: Sequence[Decision] = (
            session.scalars(
                select(Decision).where(
                    Decision.type == "offer",
                    Decision.application_id == row.application_id,
                )
            ).all()
            if row.application_id is not None
            else []
        )
        if not any(
            _named_human(decision.decided_by)
            and decision.decided_at is not None
            and decision.facts_seen is not None
            for decision in approvals
        ):
            acc.violations.append(
                f"transition to offer_sent at {row.occurred_at} has no recorded "
                "manager approval (who, when, facts seen)"
            )


def _check_protected_data(
    session: Session,
    candidates: dict[UUID, Candidate],
    per_events: dict[UUID, list[Event]],
    per_audits: dict[UUID, list[AuditEvent]],
    acc: _GuardrailAccumulator,
) -> None:
    """No protected characteristic stored anywhere or echoed back, and every
    volunteered inbound disclosure answered by a refusal event (G3)."""
    for candidate_id, rows in per_events.items():
        messages = [
            row
            for row in rows
            if row.type in (EventType.MESSAGE_IN.value, EventType.MESSAGE_OUT.value)
        ]
        candidate = candidates.get(candidate_id)
        if not messages or candidate is None:
            continue
        acc.checked += 1
        # ColumnCollection iterates Column objects, not names, so use
        # keys() (same noqa as evals/checks/deterministic.py).
        for column in candidate.__table__.columns.keys():  # noqa: SIM118
            value = getattr(candidate, column)
            if isinstance(value, str):
                acc.violations.extend(
                    f"candidate.{column} stores protected data matching '{pattern.pattern}'"
                    for pattern in PROTECTED_PATTERNS
                    if pattern.search(value)
                )
        for row in per_audits.get(candidate_id, []):
            for path, text in _json_strings(row.payload):
                acc.violations.extend(
                    f"audit '{row.event_type}' payload {path} stores protected data "
                    f"matching '{pattern.pattern}'"
                    for pattern in PROTECTED_PATTERNS
                    if pattern.search(text)
                )
        refusal_present = (
            session.scalars(
                select(AuditEvent.id)
                .where(
                    AuditEvent.candidate_id == candidate_id,
                    AuditEvent.event_type == PROTECTED_REFUSAL_EVENT,
                )
                .limit(1)
            ).first()
            is not None
        )
        for message in messages:
            for path, text in _json_strings(message.payload):
                hits = [pattern for pattern in PROTECTED_PATTERNS if pattern.search(text)]
                if not hits:
                    continue
                if message.type == EventType.MESSAGE_OUT.value:
                    acc.violations.append(
                        f"outbound message payload {path} echoes protected data"
                    )
                elif not refusal_present:
                    acc.violations.append(
                        "candidate volunteered protected data in an inbound message "
                        f"with no '{PROTECTED_REFUSAL_EVENT}' audit row"
                    )


def _json_strings(value: object) -> list[tuple[str, str]]:
    """Flatten a JSON payload into (path, text) pairs for keys and string
    leaves (evals/checks/deterministic.py::_json_strings semantics)."""
    pairs: list[tuple[str, str]] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                pairs.append((f"{path}.{key}", str(key)))
                walk(item, f"{path}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
        elif isinstance(node, str):
            pairs.append((path, node))

    walk(value, "$")
    return pairs


def _check_language(
    session: Session,
    candidates: dict[UUID, Candidate],
    per_events: dict[UUID, list[Event]],
    acc: _GuardrailAccumulator,
) -> None:
    """Candidate-facing outbound messages sent after the candidate first spoke
    must carry a language tag equal to the stated preference (C-O4)."""
    for candidate_id, rows in per_events.items():
        candidate = candidates.get(candidate_id)
        if candidate is None:
            continue
        candidate_facing = [
            row
            for row in rows
            if row.type == EventType.MESSAGE_OUT.value
            and (row.payload or {}).get("body")
            and row.payload.get("recipient_ref") not in INTERNAL_RECIPIENT_REFS
        ]
        if not candidate_facing:
            continue
        acc.checked += len(candidate_facing)
        stated_at = _first_candidate_inbound_at(session, candidate_id)
        for row in candidate_facing:
            if stated_at is not None and row.occurred_at <= stated_at:
                continue  # intake default, before the preference was stated
            language = (row.payload or {}).get("language")
            if language is None:
                acc.violations.append(
                    f"outbound message at {row.occurred_at} carries a body without a "
                    "language tag"
                )
            elif language != candidate.preferred_language:
                acc.violations.append(
                    f"outbound message at {row.occurred_at} is tagged '{language}' but "
                    f"the stated preference is '{candidate.preferred_language}'"
                )


def _first_candidate_inbound_at(session: Session, candidate_id: UUID) -> datetime | None:
    """When the candidate first spoke (message.in carrying their own text)."""
    text_has_content = or_(
        Event.payload["text"].astext.is_not(None) & (Event.payload["text"].astext != ""),
        Event.payload["body"].astext.is_not(None) & (Event.payload["body"].astext != ""),
    )
    return session.scalars(
        select(Event.occurred_at)
        .where(
            Event.candidate_id == candidate_id,
            Event.type == EventType.MESSAGE_IN.value,
            text_has_content,
        )
        .order_by(Event.occurred_at)
        .limit(1)
    ).first()


def _check_internal_identifiers(
    per_events: dict[UUID, list[Event]], acc: _GuardrailAccumulator
) -> None:
    """No message.out body of the candidate's conversation contains an
    internal outbox identifier (F09 guardrail)."""
    for rows in per_events.values():
        for row in rows:
            if row.type != EventType.MESSAGE_OUT.value:
                continue
            body = (row.payload or {}).get("body")
            if not body:
                continue
            acc.checked += 1
            hits = [
                match.group(0)
                for pattern in _INTERNAL_IDENTIFIER_PATTERNS
                if (match := pattern.search(str(body))) is not None
            ]
            if hits:
                acc.violations.append(
                    f"message.out at {row.occurred_at} carries internal identifier(s) {hits}"
                )
