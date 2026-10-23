"""Shared helpers for the console API (S2-S5).

Documented assumptions and honest gaps (data rule 4: never fabricate):

- The acting user is a role, not a person: the console sends X-Actor-Role
  (talent, dpo, ops); audit rows record actor_id "console:<role>". Real SSO
  identity is a later phase (specs/04b-console.md section 2).
- AuditEvent.actor_type uses the DB enum (candidate/manager/agent/system/
  timer); console actions are recorded as "system" with the role in
  actor_id and payload, matching the core's rule that agent and system
  actions carry accountability at the system level.
- agentInControl is derived from the latest human_action.takeover /
  human_action.release audit row for the candidate (append-only audit is
  the source of truth; there is no mutable control flag).
- Manager decision SLA: 24 h (MANAGER_SLA_HOURS). The metric tree fixes an
  escalation-acknowledgement SLA (30 min) but no manager decision SLA; this
  value is a stated console assumption, not a client commitment.
- Agent attribution (recruit/onboard/pulse) is derived from the candidate's
  current state; the scripted backend runs no LLM loop yet.
- Cohort (pilot/control) follows the seed rule: bench_enabled marks the
  pilot sites.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Header, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Candidate, Restaurant

ROLES = ("talent", "dpo", "ops")
MANAGER_SLA_HOURS = 24.0
PILOT_DAYS_TOTAL = 90  # the pilot design window (design/metric-tree.md)

TAKEOVER_EVENT = "human_action.takeover"
RELEASE_EVENT = "human_action.release"
RESTAURANT_PAUSED_EVENT = "restaurant.paused"
RESTAURANT_RESUMED_EVENT = "restaurant.resumed"
CONTROL_ACTIONS = (TAKEOVER_EVENT, RELEASE_EVENT)

CONSENT_STATES = ("granted", "revoked")

# Human labels for the internal state values (design/state-machine.md).
STATE_LABELS: dict[str, str] = {
    "new": "Applied",
    "contacted": "Contacted",
    "consented": "Consent granted",
    "screening": "Screening",
    "matched": "Matched to a shift",
    "interview_booked": "Interview booked",
    "interviewed": "Interviewed",
    "pending_manager_decision": "Waiting for manager",
    "offer_sent": "Offer sent",
    "offer_accepted": "Offer accepted",
    "preboarding": "Pre-boarding",
    "ready_for_rota": "Ready for rota",
    "first_shift_scheduled": "First shift scheduled",
    "first_shift_confirmed": "First shift confirmed",
    "first_shift_worked": "First shift worked",
    "benched": "In the bench",
    "withdrawn": "Withdrawn",
    "not_selected": "Not selected",
    "no_show": "No show",
    "erased": "Erased",
}

# Which conversational agent owns each state (no LLM loop runs yet; this is
# the ownership the agent loop will take over, derived from the state).
RECRUIT_STATES = frozenset(
    {
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
        "benched",
        "withdrawn",
        "not_selected",
        "no_show",
    }
)
ONBOARD_STATES = frozenset(
    {
        "preboarding",
        "ready_for_rota",
        "first_shift_scheduled",
        "first_shift_confirmed",
        "first_shift_worked",
    }
)
# everything else (active_week1, active_day30) belongs to pulse

# Audit actor_type (DB enum) to the contract ActorType.
CONTRACT_ACTOR_TYPE = {
    "candidate": "candidate",
    "manager": "human",
    "agent": "agent",
    "system": "system",
    "timer": "system",
}

LANGUAGE_LABELS = {"es": "Spanish", "pt": "Portuguese", "en": "English"}


def require_role(x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None) -> str:
    """The acting role from X-Actor-Role; missing or unknown roles are 400."""
    if x_actor_role is None:
        raise HTTPException(
            status_code=400,
            detail="X-Actor-Role header is required (one of: talent, dpo, ops)",
        )
    if x_actor_role not in ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"X-Actor-Role must be one of: {', '.join(ROLES)}",
        )
    return x_actor_role


def mask_phone(phone: str) -> str:
    """Last three digits visible, everything else masked (S4)."""
    digits = phone[-3:] if len(phone) > 3 else ""
    masked = "•" * max(len(phone) - 3, 3)
    return masked + digits


def state_label(state: str) -> str:
    return STATE_LABELS.get(state, state.replace("_", " ").capitalize())


def agent_for_state(state: str) -> str:
    if state in RECRUIT_STATES:
        return "recruit"
    if state in ONBOARD_STATES:
        return "onboard"
    return "pulse"


def initials_for(first_name: str, last_name: str = "") -> str:
    parts = [part for part in (first_name[:1], last_name[:1]) if part]
    return "".join(part.upper() for part in parts) or "-"


def elapsed_label(since: datetime | None, now: datetime | None = None) -> str:
    """Human elapsed time; empty when there is no timestamp to count from."""
    if since is None:
        return ""
    delta = (now or datetime.now(UTC)) - since
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h {minutes % 60}m"
    days = hours // 24
    return f"{days}d {hours % 24}h"


def sla_risk_for(state: str, state_changed_at: datetime | None, now: datetime) -> SlaRiskValue:
    """ok / at_risk (waiting for a manager) / breached (beyond the 24 h SLA)."""
    if state != "pending_manager_decision":
        return "ok"
    if state_changed_at is None:
        return "at_risk"
    waiting_hours = (now - state_changed_at).total_seconds() / 3600
    if waiting_hours > MANAGER_SLA_HOURS:
        return "breached"
    return "at_risk"


# mypy-friendly alias: the Literal values from schemas without importing them
# at module top (schemas imports nothing from here, so the cycle is safe).
from app.api.console.schemas import Cohort, SlaRisk  # noqa: E402

SlaRiskValue = SlaRisk


def cohort_for(restaurant: Restaurant) -> Cohort:
    """Pilot sites run the bench (seed rule); control sites do not."""
    return "pilot" if restaurant.bench_enabled else "control"


def append_audit(
    session: Session,
    *,
    event_type: str,
    actor_id: str,
    candidate_id: Any = None,
    payload: dict[str, Any] | None = None,
    state_from: str | None = None,
    state_to: str | None = None,
) -> AuditEvent:
    """Append one audit row (INV-5: the only write path for human actions).

    occurred_at is strictly increasing per table: two console actions in the
    same clock tick (coarse Windows timers do this) must still order
    deterministically, because takeover/release and pause/resume state is
    derived from the latest row.
    """
    now = datetime.now(UTC)
    latest_at = session.scalar(select(func.max(AuditEvent.occurred_at)))
    if latest_at is not None and latest_at >= now:
        now = latest_at + timedelta(microseconds=1)
    row = AuditEvent(
        id=uuid4(),
        occurred_at=now,
        actor_type="system",
        actor_id=actor_id,
        candidate_id=candidate_id,
        event_type=event_type,
        state_from=state_from,
        state_to=state_to,
        payload=payload or {},
    )
    session.add(row)
    session.flush()
    return row


def audit_human_action(
    session: Session,
    *,
    role: str,
    action: str,
    candidate_id: Any = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Every console action is audited with the acting role (S5, rule 3)."""
    return append_audit(
        session,
        event_type=f"human_action.{action}",
        actor_id=f"console:{role}",
        candidate_id=candidate_id,
        payload={"action": action, "role": role, **(payload or {})},
    )


def agent_in_control(session: Session, candidate_id: Any) -> bool:
    """True unless the latest takeover/release audit row is a takeover."""
    latest = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.candidate_id == candidate_id,
            AuditEvent.event_type.in_(CONTROL_ACTIONS),
        )
        .order_by(desc(AuditEvent.occurred_at))
        .limit(1)
    ).first()
    if latest is None:
        return True
    return latest.event_type == RELEASE_EVENT


def restaurant_paused(session: Session, code: str) -> bool:
    """Derived from the latest pause/resume audit row for this restaurant."""
    latest = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.event_type.in_((RESTAURANT_PAUSED_EVENT, RESTAURANT_RESUMED_EVENT)),
            AuditEvent.payload["restaurant_code"].astext == code,
        )
        .order_by(desc(AuditEvent.occurred_at))
        .limit(1)
    ).first()
    if latest is None:
        return False
    return latest.event_type == RESTAURANT_PAUSED_EVENT


def manager_median_reply_label(session: Session, restaurant_id: Any) -> str:
    """Median manager decision time in hours, or "" when nothing is recorded.

    Computed from audit rows: state_to pending_manager_decision until the
    same application's next row leaving that state.
    """
    from app.db.models import Application

    application_ids = session.scalars(
        select(Application.id).where(Application.restaurant_id == restaurant_id)
    ).all()
    if not application_ids:
        return ""
    rows = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.application_id.in_(application_ids),
            AuditEvent.state_to.is_not(None) | AuditEvent.state_from.is_not(None),
        )
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    ).all()
    entered: dict[Any, datetime] = {}
    waits: list[float] = []
    for row in rows:
        if row.state_to == "pending_manager_decision" and row.application_id:
            entered.setdefault(row.application_id, row.occurred_at)
        elif row.state_from == "pending_manager_decision" and row.application_id in entered:
            started = entered.pop(row.application_id)
            waits.append((row.occurred_at - started).total_seconds() / 3600)
    if not waits:
        return ""
    waits.sort()
    mid = len(waits) // 2
    median = waits[mid] if len(waits) % 2 else (waits[mid - 1] + waits[mid]) / 2
    return f"{median:.1f} h"


def candidate_or_404(session: Session, candidate_id: Any) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="unknown candidate")
    return candidate
