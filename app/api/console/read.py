"""Console read endpoints (specs/04b-console.md section 2, T2-T5).

- GET /api/candidates: paginated, filterable list (state, restaurant, agent,
  sla_risk, language, cohort).
- GET /api/candidates/{id}: the full journey view (profile minimized to a
  masked phone and status rows, threads from the event log, writes from the
  outbox).
- GET /api/restaurants and /api/restaurants/{id}/shifts.
- GET /api/metrics/funnel and /api/metrics/kpis.
- GET /api/escalations, /api/audit, /api/evals and /api/evals/{version}.

The SSE stream is NOT here: GET /api/events/stream already exists in
app/api/events_stream.py and is kept untouched.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from app.api.console.helpers import (
    CONTRACT_ACTOR_TYPE,
    LANGUAGE_LABELS,
    MANAGER_SLA_HOURS,
    agent_for_state,
    agent_in_control,
    cohort_for,
    elapsed_label,
    initials_for,
    manager_median_reply_label,
    mask_phone,
    restaurant_paused,
    sla_risk_for,
    state_label,
)
from app.api.console.metrics import funnel_summary, kpi_cards, load_conversations
from app.api.console.schemas import (
    AttentionItem,
    AuditResponse,
    AuditRow,
    CandidateDetail,
    CandidateListItem,
    CandidateListResponse,
    EvalSummaryRow,
    FunnelSummary,
    IntegrationWrite,
    JourneyStep,
    KpiCard,
    MatchedShift,
    RecordRow,
    RestaurantRow,
    RestaurantShiftsResponse,
    ShiftRow,
    ThreadMessage,
)
from app.api.deps import get_session
from app.db.events import Event, EventType
from app.db.models import (
    Application,
    AuditEvent,
    BenchEntry,
    Candidate,
    Consent,
    FirstShift,
    OpenShift,
    OutboxMessage,
    Restaurant,
)

router = APIRouter(prefix="/api", tags=["console"])

SessionDep = Annotated[Session, Depends(get_session)]

EVALS_DIR = Path("evals/reports")
MANAGER_THREAD_RECIPIENT = "manager-sim"
SHIFTS_WINDOW_DAYS = 14
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# JourneyStateId mapping: the contract journey has six stages. States beyond
# interview_booked fold into it (the note keeps the real state name); side
# states (benched, withdrawn, not_selected, no_show) fold into the previous
# reached stage so the trail is never silently dropped.
JOURNEY_STATE_MAP: dict[str, str] = {
    "new": "new",
    "contacted": "contacted",
    "consented": "consent",
    "screening": "screening",
    "matched": "matched",
    "interview_booked": "interview_booked",
    "interviewed": "interview_booked",
    "pending_manager_decision": "interview_booked",
    "offer_sent": "interview_booked",
    "offer_accepted": "interview_booked",
    "preboarding": "interview_booked",
    "ready_for_rota": "interview_booked",
    "first_shift_scheduled": "interview_booked",
    "first_shift_confirmed": "interview_booked",
    "first_shift_worked": "interview_booked",
    "active_week1": "interview_booked",
    "active_day30": "interview_booked",
}
JOURNEY_LABELS = {
    "new": "Applied",
    "contacted": "First contact",
    "consent": "Consent granted",
    "screening": "Screening",
    "matched": "Matched to a shift",
    "interview_booked": "Interview booked",
}


# ---------------------------------------------------------------- candidates


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    state: str | None = None,
    restaurant: str | None = None,
    agent: str | None = None,
    sla_risk: str | None = Query(default=None, alias="sla_risk"),
    language: str | None = None,
    cohort: str | None = None,
) -> CandidateListResponse:
    now = datetime.now(UTC)
    rows = _candidate_rows(session)
    filtered = [
        row
        for row in rows
        if _matches_filters(row, state, restaurant, agent, sla_risk, language, cohort, now)
    ]
    filtered.sort(key=lambda row: row.last_activity_at, reverse=True)
    total = len(filtered)
    start = (page - 1) * page_size
    items = [_list_item(row, session) for row in filtered[start : start + page_size]]
    return CandidateListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


class CandidateRowData:
    """Joined candidate + application + restaurant view for list and detail."""

    def __init__(
        self,
        candidate: Candidate,
        application: Application | None,
        restaurant: Restaurant | None,
        last_activity_at: str,
    ) -> None:
        self.candidate = candidate
        self.application = application
        self.restaurant = restaurant
        self.last_activity_at = last_activity_at


def _candidate_rows(session: Session) -> list[CandidateRowData]:
    candidates = session.scalars(select(Candidate).order_by(Candidate.id)).all()
    applications = session.scalars(select(Application)).all()
    by_candidate: dict[UUID, Application] = {}
    for app in applications:
        current = by_candidate.get(app.candidate_id)
        if current is None or (
            app.entered_at is not None
            and current.entered_at is not None
            and app.entered_at > current.entered_at
        ):
            by_candidate[app.candidate_id] = app
    restaurants = {row.id: row for row in session.scalars(select(Restaurant)).all()}
    last_activity = _last_activity_by_candidate(session)

    rows: list[CandidateRowData] = []
    for candidate in candidates:
        application = by_candidate.get(candidate.id)
        restaurant = restaurants.get(application.restaurant_id) if application else None
        rows.append(
            CandidateRowData(
                candidate=candidate,
                application=application,
                restaurant=restaurant,
                last_activity_at=last_activity.get(candidate.id, ""),
            )
        )
    return rows


def _last_activity_by_candidate(session: Session) -> dict[UUID, str]:
    latest = session.scalars(
        select(Event).where(Event.candidate_id.is_not(None)).order_by(Event.occurred_at)
    ).all()
    found: dict[UUID, datetime] = {}
    for row in latest:
        if row.candidate_id is not None:
            found[row.candidate_id] = row.occurred_at  # ordered: last write wins
    return {candidate_id: at.isoformat() for candidate_id, at in found.items()}


def _matches_filters(
    row: CandidateRowData,
    state: str | None,
    restaurant: str | None,
    agent: str | None,
    sla_risk: str | None,
    language: str | None,
    cohort: str | None,
    now: datetime,
) -> bool:
    candidate, application = row.candidate, row.application
    if state and candidate.state != state:
        return False
    if restaurant and (row.restaurant is None or row.restaurant.code != restaurant):
        return False
    if agent and agent_for_state(candidate.state) != agent:
        return False
    if sla_risk and sla_risk_for(
        candidate.state,
        application.state_changed_at if application else None,
        now,
    ) != sla_risk:
        return False
    if language and candidate.preferred_language != language:
        return False
    return not (
        cohort and row.restaurant and cohort_for(row.restaurant) != cohort
    )



def _list_item(row: CandidateRowData, session: Session) -> CandidateListItem:
    candidate, application = row.candidate, row.application
    now = datetime.now(UTC)
    matched = _matched_shift(session, application) if application else None
    return CandidateListItem(
        id=str(candidate.id),
        first_name=candidate.first_name,
        initials=initials_for(candidate.first_name),
        state=candidate.state,
        state_label=state_label(candidate.state),
        restaurant=row.restaurant.name if row.restaurant else "",
        restaurant_code=row.restaurant.code if row.restaurant else "",
        cohort=cohort_for(row.restaurant) if row.restaurant else "pilot",
        languages=[candidate.preferred_language],
        agent_version="",  # scripted backend: no agent loop, never invented
        agent_in_control=agent_in_control(session, candidate.id),
        sla_risk=sla_risk_for(
            candidate.state,
            application.state_changed_at if application else None,
            now,
        ),
        last_activity_at=row.last_activity_at,
        matched_shift_label=matched.label if matched else "",
        phone_masked=mask_phone(candidate.phone),
        elapsed_label=elapsed_label(
            application.entered_at if application else None, now
        ),
    )


# ------------------------------------------------------------ candidate detail


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def candidate_detail(candidate_id: UUID, session: SessionDep) -> CandidateDetail:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="unknown candidate")
    application = session.scalars(
        select(Application)
        .where(Application.candidate_id == candidate.id)
        .order_by(Application.entered_at.desc())
        .limit(1)
    ).first()
    restaurant = (
        session.get(Restaurant, application.restaurant_id) if application else None
    )
    now = datetime.now(UTC)

    matched = _matched_shift(session, application) if application else None
    audit_rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.candidate_id == candidate.id)
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    ).all()
    events = session.scalars(
        select(Event)
        .where(Event.candidate_id == candidate.id)
        .order_by(Event.occurred_at, Event.id)
    ).all()
    outbox_rows = session.scalars(
        select(OutboxMessage).where(OutboxMessage.related_entity_id == candidate.id)
    ).all()
    consent = session.scalars(
        select(Consent)
        .where(Consent.candidate_id == candidate.id)
        .order_by(Consent.granted_at.desc())
        .limit(1)
    ).first()
    first_shift = None
    if application:
        first_shift = session.scalars(
            select(FirstShift)
            .where(FirstShift.application_id == application.id)
            .limit(1)
        ).first()

    return CandidateDetail(
        id=str(candidate.id),
        first_name=candidate.first_name,
        last_name="",  # FirstShift stores no surname (data minimization)
        initials=initials_for(candidate.first_name),
        state_label=state_label(candidate.state),
        restaurant=restaurant.name if restaurant else "",
        languages=[candidate.preferred_language],
        agent_version="",
        agent_in_control=agent_in_control(session, candidate.id),
        elapsed_label=elapsed_label(application.entered_at if application else None, now),
        phone_masked=mask_phone(candidate.phone),
        journey=_journey(audit_rows, application),
        candidate_thread=_thread(events, manager_thread=False),
        manager_thread=_thread(events, manager_thread=True),
        matched_shift=matched
        or MatchedShift(label="", restaurant="", detail="", shift_ids=[], held=""),
        summary_rows=_summary_rows(candidate, application, restaurant, first_shift),
        summary_note=(
            "Rows show recorded facts only; documents and training are not "
            "tracked by the backend yet, so their status is an explicit "
            "not_requested, never assumed."
        ),
        consent_row=_consent_row(consent),
        pre_boarding=_pre_boarding_rows(first_shift),
        writes=[
            IntegrationWrite(
                id=str(row.id),
                status_code=200 if row.status in ("api_confirmed", "csv_confirmed") else 0,
                target=row.port,
                operation=row.operation,
                idempotency_key=row.idempotency_key,
            )
            for row in outbox_rows
        ],
    )


def _journey(
    audit_rows: Sequence[AuditEvent], application: Application | None
) -> list[JourneyStep]:
    steps: list[JourneyStep] = []
    if application is not None:
        steps.append(
            JourneyStep(
                id="new",
                label=JOURNEY_LABELS["new"],
                at=application.entered_at.isoformat() if application.entered_at else "",
                actor_label="HireDesk",
                actor_type="system",
                note="Application received from HireDesk",
                current=False,
            )
        )
    for row in audit_rows:
        if not row.state_to:
            continue
        mapped = JOURNEY_STATE_MAP.get(row.state_to)
        actor_type = CONTRACT_ACTOR_TYPE.get(row.actor_type, "system")
        actor_label = row.actor_id or row.actor_type
        if mapped is None:
            # Side state: fold into the previous step's note, never drop it.
            if steps:
                previous = steps[-1]
                previous.note = " ".join(
                    part
                    for part in (previous.note, f"state '{row.state_to}' recorded")
                    if part
                )
            continue
        note = row.payload.get("details") or None if isinstance(row.payload, dict) else None
        if steps and steps[-1].id == mapped:
            # States beyond the six contract stages fold into the last one:
            # merge consecutive duplicates and record the real state names.
            previous = steps[-1]
            previous.note = " ".join(
                part for part in (previous.note, f"then {row.state_to}") if part
            )
            continue
        steps.append(
            JourneyStep(
                id=mapped,  # type: ignore[arg-type]
                label=JOURNEY_LABELS[mapped],
                at=row.occurred_at.isoformat(),
                actor_label=actor_label,
                actor_type=actor_type,  # type: ignore[arg-type]
                note=str(note) if note else None,
                current=False,
            )
        )
    if steps:
        steps[-1].current = True
    return steps


def _thread(events: Sequence[Event], *, manager_thread: bool) -> list[ThreadMessage]:
    messages: list[ThreadMessage] = []
    for row in events:
        payload = row.payload or {}
        if row.type == EventType.MESSAGE_IN.value:
            role = str(payload.get("role", "candidate"))
            if manager_thread:
                if role != "manager":
                    continue
                messages.append(
                    ThreadMessage(
                        id=str(row.id),
                        at=row.occurred_at.isoformat(),
                        sender_type="human",
                        sender_label="Manager",
                        text=str(payload.get("text", "")),
                    )
                )
            else:
                if role == "manager":
                    continue
                # role "system" stands in for the agent loop until T1 lands.
                sender: str = "candidate" if role == "candidate" else "agent"
                messages.append(
                    ThreadMessage(
                        id=str(row.id),
                        at=row.occurred_at.isoformat(),
                        sender_type=sender,  # type: ignore[arg-type]
                        sender_label=None if sender == "candidate" else "FirstShift",
                        agent_version=None,
                        text=str(payload.get("text", "")),
                    )
                )
        elif row.type == EventType.MESSAGE_OUT.value:
            recipient = str(payload.get("recipient_ref", ""))
            to_manager = recipient == MANAGER_THREAD_RECIPIENT
            if to_manager != manager_thread:
                continue
            if str(payload.get("sender_type", "")) == "human":
                messages.append(
                    ThreadMessage(
                        id=str(row.id),
                        at=row.occurred_at.isoformat(),
                        sender_type="human",
                        sender_label=str(payload.get("role", "human")),
                        text=str(payload.get("body", "")),
                    )
                )
            else:
                messages.append(
                    ThreadMessage(
                        id=str(row.id),
                        at=row.occurred_at.isoformat(),
                        sender_type="agent",
                        sender_label="FirstShift",
                        text=str(payload.get("body", "")),
                    )
                )
    return messages


def _matched_shift(session: Session, application: Application) -> MatchedShift | None:
    if application is None:
        return None
    shift = session.scalars(
        select(OpenShift).where(OpenShift.matched_application_id == application.id).limit(1)
    ).first()
    if shift is None and application.target_open_shift_ids:
        shift = session.scalars(
            select(OpenShift)
            .where(OpenShift.id.in_(application.target_open_shift_ids))
            .limit(1)
        ).first()
    if shift is None:
        return None
    restaurant = session.get(Restaurant, shift.restaurant_id)
    start = shift.starts_at
    end = shift.ends_at
    return MatchedShift(
        label=f"{shift.role} shift, {start:%a %d %b}",
        restaurant=restaurant.name if restaurant else "",
        detail=f"{start:%H:%M}-{end:%H:%M} ({restaurant.timezone if restaurant else 'UTC'}), "
        f"food hygiene {'required' if shift.requires_food_hygiene else 'not required'}",
        shift_ids=[shift.shiftgrid_shift_id],
        held="",  # shift holds are not tracked by the backend yet
    )


def _summary_rows(
    candidate: Candidate,
    application: Application | None,
    restaurant: Restaurant | None,
    first_shift: FirstShift | None,
) -> list[RecordRow]:
    rows = [
        RecordRow(
            label="Language",
            value=LANGUAGE_LABELS.get(
                candidate.preferred_language, candidate.preferred_language
            ),
            status="ok",
        ),
        RecordRow(
            label="Source",
            value=candidate.source.replace("_", " "),
            status="ok",
        ),
        RecordRow(
            label="Restaurant",
            value=restaurant.name if restaurant else "not assigned yet",
            status="ok" if restaurant else "pending",
        ),
        RecordRow(
            label="Documents",
            value="not tracked yet",
            status="not_requested",
        ),
        RecordRow(
            label="Food hygiene training",
            value="not tracked yet",
            status="not_requested",
        ),
    ]
    if first_shift is not None:
        rows.append(
            RecordRow(
                label="Rota blocker",
                value=first_shift.current_blocker.replace("_", " "),
                status="ok" if first_shift.current_blocker == "none" else "pending",
            )
        )
    return rows


def _consent_row(consent: Consent | None) -> RecordRow:
    if consent is None:
        return RecordRow(label="Consent", value="none recorded", status="not_requested")
    revoked = consent.revoked_at is not None
    value = (
        f"{consent.channel}, notice {consent.notice_version}, "
        f"granted {consent.granted_at:%Y-%m-%d %H:%M} UTC"
        + (" (revoked)" if revoked else "")
    )
    return RecordRow(label="Consent", value=value, status="ok")


def _pre_boarding_rows(first_shift: FirstShift | None) -> list[RecordRow]:
    if first_shift is None:
        return [RecordRow(label="Pre-boarding", value="not started", status="not_requested")]
    rows = [
        RecordRow(
            label="First shift",
            value=first_shift.scheduled_at.strftime("%a %d %b %H:%M"),
            status="ok",
        ),
        RecordRow(
            label="Documents complete",
            value=(
                first_shift.docs_complete_at.strftime("%Y-%m-%d")
                if first_shift.docs_complete_at
                else "pending"
            ),
            status="ok" if first_shift.docs_complete_at else "pending",
        ),
        RecordRow(
            label="Contract to rota",
            value=first_shift.current_blocker.replace("_", " "),
            status="ok" if first_shift.current_blocker == "none" else "pending",
        ),
    ]
    return rows


# ---------------------------------------------------------------- restaurants


@router.get("/restaurants", response_model=list[RestaurantRow])
def list_restaurants(session: SessionDep) -> list[RestaurantRow]:
    window_start = datetime.now(UTC) - timedelta(days=1)
    window_end = datetime.now(UTC) + timedelta(days=SHIFTS_WINDOW_DAYS)
    rows: list[RestaurantRow] = []
    for restaurant in session.scalars(select(Restaurant).order_by(Restaurant.code)).all():
        shifts = session.scalars(
            select(OpenShift).where(
                OpenShift.restaurant_id == restaurant.id,
                OpenShift.starts_at >= window_start,
                OpenShift.starts_at <= window_end,
            )
        ).all()
        covered = sum(1 for shift in shifts if shift.status in ("matched", "filled"))
        bench = len(
            session.scalars(
                select(BenchEntry).where(
                    BenchEntry.restaurant_id == restaurant.id,
                    BenchEntry.status == "active",
                )
            ).all()
        )
        open_candidates = len(
            session.scalars(
                select(Application).where(
                    Application.restaurant_id == restaurant.id,
                    Application.state.in_(OPEN_PIPELINE_STATES),
                )
            ).all()
        )
        rows.append(
            RestaurantRow(
                id=str(restaurant.id),
                code=restaurant.code,
                name=restaurant.name,
                city=restaurant.city,
                cohort=cohort_for(restaurant),
                open_shifts=sum(1 for shift in shifts if shift.status == "open"),
                covered_pct=round(100.0 * covered / len(shifts), 1) if shifts else 0.0,
                bench=bench,
                open_candidates=open_candidates,
                manager_median_reply=manager_median_reply_label(session, restaurant.id),
                paused=restaurant_paused(session, restaurant.code),
            )
        )
    return rows


OPEN_PIPELINE_STATES = (
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
    "preboarding",
    "ready_for_rota",
    "first_shift_scheduled",
    "first_shift_confirmed",
)


@router.get("/restaurants/{restaurant_id}/shifts", response_model=RestaurantShiftsResponse)
def restaurant_shifts(restaurant_id: UUID, session: SessionDep) -> RestaurantShiftsResponse:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    window_start = datetime.now(UTC) - timedelta(days=1)
    window_end = datetime.now(UTC) + timedelta(days=SHIFTS_WINDOW_DAYS)
    shifts = session.scalars(
        select(OpenShift)
        .where(
            OpenShift.restaurant_id == restaurant.id,
            OpenShift.starts_at >= window_start,
            OpenShift.starts_at <= window_end,
        )
        .order_by(OpenShift.starts_at)
    ).all()
    rows: list[ShiftRow] = []
    for shift in shifts:
        matched_name: str | None = None
        matched_id: str | None = None
        if shift.matched_application_id:
            application = session.get(Application, shift.matched_application_id)
            if application:
                matched = session.get(Candidate, application.candidate_id)
                if matched is not None:
                    matched_id = str(matched.id)
                    matched_name = matched.first_name
        rows.append(
            ShiftRow(
                id=shift.shiftgrid_shift_id,
                label=f"{shift.role}, {shift.starts_at:%a %d %b %H:%M}-{shift.ends_at:%H:%M}",
                starts_at=shift.starts_at.isoformat(),
                ends_at=shift.ends_at.isoformat(),
                role=shift.role,
                requires_food_hygiene=shift.requires_food_hygiene,
                status=shift.status,
                matched_candidate_id=matched_id,
                matched_candidate_name=matched_name,
            )
        )
    return RestaurantShiftsResponse(
        restaurant=RestaurantRow(
            id=str(restaurant.id),
            code=restaurant.code,
            name=restaurant.name,
            city=restaurant.city,
            cohort=cohort_for(restaurant),
            open_shifts=sum(1 for row in rows if row.status == "open"),
            covered_pct=(
                round(
                    100.0
                    * sum(1 for r in rows if r.status in ("matched", "filled"))
                    / len(rows),
                    1,
                )
                if rows
                else 0.0
            ),
            bench=len(
                session.scalars(
                    select(BenchEntry).where(
                        BenchEntry.restaurant_id == restaurant.id,
                        BenchEntry.status == "active",
                    )
                ).all()
            ),
            open_candidates=len(
                session.scalars(
                    select(Application).where(
                        Application.restaurant_id == restaurant.id,
                        Application.state.in_(OPEN_PIPELINE_STATES),
                    )
                ).all()
            ),
            manager_median_reply=manager_median_reply_label(session, restaurant.id),
            paused=restaurant_paused(session, restaurant.code),
        ),
        shifts=rows,
    )


# ------------------------------------------------------------------- metrics


@router.get("/metrics/funnel", response_model=FunnelSummary)
def metrics_funnel(session: SessionDep) -> FunnelSummary:
    return funnel_summary(load_conversations(session))


@router.get("/metrics/kpis", response_model=list[KpiCard])
def metrics_kpis(session: SessionDep) -> list[KpiCard]:
    return kpi_cards(load_conversations(session))


# --------------------------------------------------------------- escalations


@router.get("/escalations", response_model=list[AttentionItem])
def escalations(session: SessionDep) -> list[AttentionItem]:
    now = datetime.now(UTC)
    items: list[AttentionItem] = []

    # Manager decisions pending (with the 24 h SLA, stated in helpers).
    for application, candidate in session.execute(
        select(Application, Candidate)
        .where(
            Application.candidate_id == Candidate.id,
            Application.state == "pending_manager_decision",
        )
    ).all():
        waiting = elapsed_label(application.state_changed_at, now)
        breached = (
            application.state_changed_at is not None
            and (now - application.state_changed_at).total_seconds() / 3600
            > MANAGER_SLA_HOURS
        )
        items.append(
            AttentionItem(
                id=f"manager-{application.id}",
                kind="sla_breach" if breached else "human_needed",
                title=f"Manager decision pending: {candidate.first_name}",
                detail=(
                    f"{state_label(application.state)} at "
                    f"{_restaurant_name(session, application.restaurant_id)}"
                ),
                ago=waiting,
            )
        )

    # First shifts scheduled but unconfirmed in the next 48 h.
    horizon = now + timedelta(days=2)
    for first_shift, application in session.execute(
        select(FirstShift, Application).where(
            FirstShift.application_id == Application.id,
            FirstShift.confirmation_status == "pending",
            FirstShift.scheduled_at >= now,
            FirstShift.scheduled_at <= horizon,
        )
    ).all():
        matched_candidate = session.get(Candidate, application.candidate_id)
        name = (
            matched_candidate.first_name
            if matched_candidate is not None
            else "candidate"
        )
        items.append(
            AttentionItem(
                id=f"shift-{first_shift.id}",
                kind="first_shift",
                title=f"First shift unconfirmed: {name}",
                detail=f"Scheduled {first_shift.scheduled_at:%a %d %b %H:%M}",
                ago=elapsed_label(first_shift.scheduled_at, now) or "upcoming",
            )
        )

    # Dead-lettered outbox rows (DLQ).
    for row in session.scalars(
        select(OutboxMessage).where(OutboxMessage.status == "failed")
    ).all():
        items.append(
            AttentionItem(
                id=f"dlq-{row.id}",
                kind="dlq",
                title=f"Dead letter: {row.port} {row.operation}",
                detail=row.last_error or "failed without a recorded error",
                ago=f"{row.attempts} attempts",
            )
        )

    # Eval reports with failing deterministic checks.
    latest = _latest_eval_report()
    if latest is not None:
        failures = latest.get("deterministic_checks", {}).get("failing", 0)
        if isinstance(failures, int) and failures > 0:
            items.append(
                AttentionItem(
                    id=f"eval-{latest.get('meta', {}).get('label', 'latest')}",
                    kind="eval",
                    title="Eval report with failing checks",
                    detail=f"{failures} deterministic check failures in the latest report",
                    ago=str(latest.get("meta", {}).get("generated_at", "")),
                )
            )
    return items


def _restaurant_name(session: Session, restaurant_id: UUID) -> str:
    restaurant = session.get(Restaurant, restaurant_id)
    return f"{restaurant.name} ({restaurant.code})" if restaurant else "unknown restaurant"


def _latest_eval_report() -> dict[str, Any] | None:
    reports = sorted(EVALS_DIR.glob("eval-*.json"))
    if not reports:
        return None
    report: dict[str, Any] = json.loads(reports[-1].read_text(encoding="utf-8"))
    return report


# --------------------------------------------------------------------- audit


@router.get("/audit", response_model=AuditResponse)
def audit_log(
    session: SessionDep,
    q: str | None = None,
    candidate_id: Annotated[UUID | None, Query(alias="candidateId")] = None,
    event_type: Annotated[str | None, Query(alias="eventType")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditResponse:
    query = select(AuditEvent)
    if candidate_id is not None:
        query = query.where(AuditEvent.candidate_id == candidate_id)
    if event_type is not None:
        query = query.where(AuditEvent.event_type == event_type)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                AuditEvent.event_type.ilike(pattern),
                AuditEvent.actor_id.ilike(pattern),
                AuditEvent.state_from.ilike(pattern),
                AuditEvent.state_to.ilike(pattern),
                AuditEvent.payload.cast(Text).ilike(pattern),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    ordered = query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id)
    rows = session.scalars(ordered.limit(limit).offset(offset)).all()
    return AuditResponse(
        items=[_audit_row(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def _audit_row(row: AuditEvent) -> AuditRow:
    summary_parts = [row.event_type]
    if row.state_from and row.state_to:
        summary_parts.append(
            f"{state_label(row.state_from).lower()} to {state_label(row.state_to).lower()}"
        )
    elif row.state_to:
        summary_parts.append(f"entered {state_label(row.state_to).lower()}")
    return AuditRow(
        id=str(row.id),
        at=row.occurred_at.isoformat(),
        actor_type=CONTRACT_ACTOR_TYPE.get(row.actor_type, "system"),  # type: ignore[arg-type]
        actor_label=row.actor_id,
        event_type=row.event_type,
        state_from=row.state_from,
        state_to=row.state_to,
        summary=", ".join(summary_parts),
        payload=dict(row.payload or {}),
    )


# --------------------------------------------------------------------- evals


@router.get("/evals", response_model=list[EvalSummaryRow])
def list_evals() -> list[EvalSummaryRow]:
    rows: list[EvalSummaryRow] = []
    for path in sorted(EVALS_DIR.glob("eval-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        meta = report.get("meta", {})
        summary = report.get("summary", {})
        version = path.stem.removeprefix("eval-")
        rows.append(
            EvalSummaryRow(
                version=version,
                label=str(meta.get("label", version)),
                generated_at=str(meta.get("generated_at", "")),
                task_success_rate=(
                    float(summary["task_success_rate"])
                    if isinstance(summary.get("task_success_rate"), (int, float))
                    else None
                ),
                cost_per_hire_usd=(
                    float(summary["cost_per_hired_usd"])
                    if isinstance(summary.get("cost_per_hired_usd"), (int, float))
                    else None
                ),
            )
        )
    return rows


@router.get("/evals/{version}")
def eval_report(version: str) -> dict[str, Any]:
    path = EVALS_DIR / f"eval-{version}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"unknown eval version {version}")
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return report
