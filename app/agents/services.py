"""Agent services (F07 T1): the persistence boundary between agent tools and
the deterministic core.

Dependency arrow (design/agents.md): agents call tools, tools call these
services, services call the pure core (``app.core.state_machine``), the core
decides. No service ever calls a client system directly: outbound writes land
in the outbox like every other path.

``AgentService`` implements the ``AgentBackend`` protocol the runner speaks:

- ``context()`` builds the ``TurnContext`` (state, candidate summary, allowed
  tools) from the cached pure snapshot,
- ``execute_tool`` validates the call against the per-state allow-list at the
  dispatcher (G6 enforcement point), then runs the tool function in one
  transaction; rejections are recorded as ``tool.call`` events and returned,
  never swallowed,
- ``record_event`` appends one typed event envelope to the events table.

Core facts guards read (notice version, manager slots, document flags) live
on the pure ``Application`` snapshot, cached per service instance, mirroring
``app.services.scripted``: the column store for these facts arrives later.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.agents.base import ToolOutcome, TurnContext
from app.agents.tools import ToolDispatcher
from app.core.state_machine import (
    Actor,
    ActorKind,
    State,
    StateMachine,
)
from app.core.state_machine import (
    Application as CoreApplication,
)
from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import Application, AuditEvent, Candidate, Consent, OpenShift, OutboxMessage

logger = structlog.get_logger(__name__)

EVENT_TYPE_VALUES = frozenset(t.value for t in EventType)

# Outbox kinds this layer can persist; anything else fails loudly (rule 4).
_OUTBOX_MAPPING: dict[str, tuple[str, str]] = {
    "hiredesk.stage_update": ("hiredesk", "update_stage"),
    "whatsapp.out": ("whatsapp", "send"),
    "shiftgrid.write": ("shiftgrid", "assign_shift"),
}


class ToolExecutionError(RuntimeError):
    """A tool could not complete: the core rejected the event or an argument
    was invalid. Recorded as a ``tool.call`` event with status ``error``."""


# ------------------------------------------------------- tool implementations
# Signature: (service, session, application, candidate, **arguments) -> dict.
# Thin wrappers only: facts and transitions come from the core.


def _capture_consent(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    channel: str = "whatsapp",
    language: str | None = None,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    new_snapshot = service._apply(
        session,
        application,
        candidate,
        snapshot,
        "candidate_consents",
        Actor(ActorKind.CANDIDATE),
        {"channel": channel, "language": language},
    )
    session.add(
        Consent(
            id=uuid4(),
            candidate_id=candidate.id,
            channel=channel,
            purpose="screening",
            notice_version=snapshot.notice_version or service.notice_version,
            granted_at=service.now,
        )
    )
    return {"consent_recorded": True, "state": new_snapshot.state.value}


def _save_language_tag(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    language: str,
) -> dict[str, Any]:
    candidate.preferred_language = language
    snapshot = replace(service._snapshot(application), language=language)
    service._store_snapshot(snapshot)
    return {"language": language, "state": snapshot.state.value}


def _save_screening_answers(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    right_to_work: bool,
    minimum_age_confirmed: bool,
    distance_ok: bool,
    transport: str | None = None,
    availability: list[str] | None = None,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    eligibility_ok = bool(right_to_work and minimum_age_confirmed and distance_ok)
    updated = replace(snapshot, eligibility_ok=eligibility_ok)
    service._store_snapshot(updated)
    if snapshot.state is State.CONSENTED:
        updated = service._apply(
            session, application, candidate, updated, "screening_starts",
            Actor(ActorKind.SYSTEM), {},
        )
    return {
        "eligibility_ok": eligibility_ok,
        "state": updated.state.value,
        "transport": transport,
        "availability": availability,
    }


def _get_open_shifts(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    rows = session.scalars(
        select(OpenShift).where(
            OpenShift.restaurant_id == application.restaurant_id,
            OpenShift.status == "open",
        )
    ).all()
    return {
        "shifts": [
            {
                "id": str(row.id),
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat(),
                "role": row.role,
            }
            for row in rows
        ]
    }


def _propose_shifts(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    shift_ids: list[str],
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    updated = replace(snapshot, shift_fit_ok=bool(shift_ids))
    service._store_snapshot(updated)
    if snapshot.state is State.SCREENING:
        updated = service._apply(
            session, application, candidate, updated, "shift_fit_matched",
            Actor(ActorKind.SYSTEM), {"shift_ids": shift_ids},
        )
    return {"proposed": shift_ids, "state": updated.state.value}


def _book_interview_slot(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    slot: str,
) -> dict[str, Any]:
    try:
        slot_dt = datetime.fromisoformat(slot)
    except ValueError as error:
        raise ToolExecutionError(f"invalid slot datetime: {slot!r}") from error
    snapshot = service._apply(
        session, application, candidate, service._snapshot(application),
        "slot_selected", Actor(ActorKind.CANDIDATE),
        {"slot": slot_dt, "stage": "interview_booked"},
    )
    return {"booked": slot, "state": snapshot.state.value}


def _add_to_bench(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    bench_consent: bool = True,
) -> dict[str, Any]:
    snapshot = service._apply(
        session, application, candidate, service._snapshot(application),
        "benched_with_consent", Actor(ActorKind.SYSTEM),
        {"bench_consent": bool(bench_consent)},
    )
    return {"benched": True, "state": snapshot.state.value}


def _request_manager_decision(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    summary: str,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    if snapshot.state is State.INTERVIEWED:
        snapshot = service._apply(
            session, application, candidate, snapshot, "decision_requested",
            Actor(ActorKind.SYSTEM), {"summary": summary},
        )
    elif snapshot.state is State.PENDING_MANAGER_DECISION:
        pass  # idempotent re-send: the request is already recorded
    else:
        raise ToolExecutionError(
            f"request_manager_decision is only valid from interviewed or "
            f"pending_manager_decision, not {snapshot.state.value}"
        )
    return {"state": snapshot.state.value}


def _request_documents(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    upload_link = f"sim://upload/{application.id}"
    service._audit(session, application, candidate, "documents_requested",
                   {"upload_link": upload_link})
    return {"upload_link": upload_link}


def _check_document_status(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    return {"documents_complete": service._snapshot(application).documents_complete}


def _enroll_training(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    module: str = "food_hygiene",
) -> dict[str, Any]:
    service._audit(session, application, candidate, "training_enrolled", {"module": module})
    return {"enrolled": True, "module": module}


def _check_training_status(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    return {"hygiene_module_complete": snapshot.hygiene_module_complete}


def _schedule_first_shift(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    first_shift_at: str,
    shift_type: str = "food_handling",
) -> dict[str, Any]:
    # A proposal only: row 23 is a manager decision (the agent recommends).
    service._audit(
        session, application, candidate, "first_shift_proposed",
        {"first_shift_at": first_shift_at, "shift_type": shift_type},
    )
    return {"proposed_at": first_shift_at, "decided_by": "manager"}


def _send_first_shift_brief(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    body = (
        "Tu primer turno en Lumbre Burger: "
        f"{snapshot.first_shift_at.isoformat() if snapshot.first_shift_at else 'por confirmar'}. "
        "Pregunta por el encargado al llegar."
    )
    append_event(
        session,
        EventEnvelope(
            type=EventType.MESSAGE_OUT,
            candidate_id=candidate.id,
            trace_id=service.trace_id,
            payload={"template": "first_shift_brief", "body": body},
        ),
    )
    return {"body": body}


def _activate_backup(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    snapshot = service._apply(
        session, application, candidate, service._snapshot(application),
        "confirmation_cutoff", Actor(ActorKind.TIMER, "confirmation_cutoff"),
        {"timer": "confirmation_cutoff"},
    )
    return {"backup_active": snapshot.backup_active, "state": snapshot.state.value}


def _get_tracker_status(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    return {
        "documents_complete": snapshot.documents_complete,
        "csv_confirmed": snapshot.csv_confirmed,
        "people_ops_exception": snapshot.people_ops_exception,
        "first_shift_at": snapshot.first_shift_at.isoformat()
        if snapshot.first_shift_at
        else None,
    }


def _get_employee_rota(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
) -> dict[str, Any]:
    snapshot = service._snapshot(application)
    return {
        "shifts": [
            {"scheduled_at": snapshot.first_shift_at.isoformat()}
            for _ in [0]
            if snapshot.first_shift_at is not None
        ]
    }


def _report_issue_to_manager(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    issue: str,
) -> dict[str, Any]:
    service._audit(session, application, candidate, "issue_reported_to_manager",
                   {"issue": issue})
    return {"routed_to": "manager"}


def _request_swap(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    shift_id: str,
    reason: str,
) -> dict[str, Any]:
    # C-O1: the manager decides; the agent only routes the request.
    service._audit(session, application, candidate, "swap_requested",
                   {"shift_id": shift_id, "reason": reason})
    return {"routed_to": "manager", "decided_by": "manager"}


def _record_manager_rating(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    rating: int,
) -> dict[str, Any]:
    if not 1 <= rating <= 5:
        raise ToolExecutionError(f"rating must be 1..5, got {rating}")
    service._audit(session, application, candidate, "manager_rating_recorded",
                   {"rating": rating})
    return {"rating": rating}


def _record_retention_signal(
    service: AgentService,
    session: Session,
    application: Application,
    candidate: Candidate,
    *,
    retained: bool,
    cause: str | None = None,
) -> dict[str, Any]:
    service._audit(session, application, candidate, "retention_signal_recorded",
                   {"retained": bool(retained), "cause": cause})
    return {"retained": bool(retained), "cause": cause}


TOOL_FUNCTIONS: dict[str, Any] = {
    "capture_consent": _capture_consent,
    "save_language_tag": _save_language_tag,
    "save_screening_answers": _save_screening_answers,
    "get_open_shifts": _get_open_shifts,
    "propose_shifts": _propose_shifts,
    "book_interview_slot": _book_interview_slot,
    "add_to_bench": _add_to_bench,
    "request_manager_decision": _request_manager_decision,
    "request_documents": _request_documents,
    "check_document_status": _check_document_status,
    "enroll_training": _enroll_training,
    "check_training_status": _check_training_status,
    "schedule_first_shift": _schedule_first_shift,
    "send_first_shift_brief": _send_first_shift_brief,
    "activate_backup": _activate_backup,
    "get_tracker_status": _get_tracker_status,
    "get_employee_rota": _get_employee_rota,
    "report_issue_to_manager": _report_issue_to_manager,
    "request_swap": _request_swap,
    "record_manager_rating": _record_manager_rating,
    "record_retention_signal": _record_retention_signal,
}


# ----------------------------------------------------------------- service


class AgentService:
    """Persistence-backed agent backend for one application journey."""

    def __init__(
        self,
        engine: Engine,
        *,
        application_id: UUID,
        candidate_id: UUID,
        trace_id: str,
        agent: str = "recruit",
        notice_version: str = "v1",
        manager_open_slots: tuple[datetime, ...] = (),
        now: datetime,
    ) -> None:
        self.engine = engine
        self.application_id = application_id
        self.candidate_id = candidate_id
        self.trace_id = trace_id
        self.agent = agent
        self.notice_version = notice_version
        self.manager_open_slots = manager_open_slots
        self.now = now
        self._snapshots: dict[str, CoreApplication] = {}

    # ------------------------------------------------ runner protocol

    def context(self) -> TurnContext:
        with Session(self.engine) as session:
            application = session.get(Application, self.application_id)
            candidate = session.get(Candidate, self.candidate_id)
            assert application is not None, "application vanished"
            assert candidate is not None, "candidate vanished"
            state = self._snapshot(application).state.value
            return TurnContext(
                state=state,
                candidate_name=candidate.first_name,
                language=candidate.preferred_language,
                allowed_tools=ToolDispatcher().tools_for(self.agent, state),
            )

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolOutcome:
        state = self.context().state
        dispatcher = ToolDispatcher()
        rejection = dispatcher.validate(tool_name, self.agent, state)
        if rejection is not None:
            self.record_event(
                EventType.TOOL_CALL,
                {
                    "agent": self.agent,
                    "tool": tool_name,
                    "status": "rejected",
                    "reason": rejection.reason,
                    "state": state,
                },
            )
            return ToolOutcome(status="rejected", result={}, reason=rejection.reason)

        function = TOOL_FUNCTIONS.get(tool_name)
        assert function is not None, (
            f"allow-list and tool registry drifted apart: {tool_name}"
        )
        try:
            with Session(self.engine) as session, session.begin():
                application = session.get(Application, self.application_id)
                candidate = session.get(Candidate, self.candidate_id)
                assert application is not None, "application vanished"
                assert candidate is not None, "candidate vanished"
                bound = inspect.signature(function).bind(
                    self, session, application, candidate, **arguments
                )
                result = dict(function(*bound.args, **bound.kwargs))
        except ToolExecutionError as error:
            self.record_event(
                EventType.TOOL_CALL,
                {
                    "agent": self.agent,
                    "tool": tool_name,
                    "status": "error",
                    "reason": str(error),
                    "state": state,
                },
            )
            return ToolOutcome(status="error", result={}, reason=str(error))
        except TypeError as error:
            self.record_event(
                EventType.TOOL_CALL,
                {
                    "agent": self.agent,
                    "tool": tool_name,
                    "status": "error",
                    "reason": f"invalid arguments: {error}",
                    "state": state,
                },
            )
            return ToolOutcome(status="error", result={}, reason=str(error))

        self.record_event(
            EventType.TOOL_CALL,
            {
                "agent": self.agent,
                "tool": tool_name,
                "status": "ok",
                "result": result,
                "state": state,
            },
        )
        return ToolOutcome(status="ok", result=result, reason=None)

    def record_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        with Session(self.engine) as session, session.begin():
            append_event(
                session,
                EventEnvelope(
                    type=event_type,
                    candidate_id=self.candidate_id,
                    trace_id=self.trace_id,
                    payload=dict(payload),
                ),
            )

    # ------------------------------------------------------- internals

    def _snapshot(self, application: Application) -> CoreApplication:
        cached = self._snapshots.get(str(application.id))
        if cached is not None:
            return cached
        return CoreApplication(
            application_id=str(application.id),
            state=State(application.state),
            notice_version=self.notice_version,
            manager_open_slots=self.manager_open_slots,
            shift_type="food_handling",
        )

    def _store_snapshot(self, snapshot: CoreApplication) -> None:
        self._snapshots[snapshot.application_id] = snapshot

    def _apply(
        self,
        session: Session,
        application: Application,
        candidate: Candidate,
        snapshot: CoreApplication,
        event: str,
        actor: Actor,
        payload: dict[str, Any],
    ) -> CoreApplication:
        """Dispatch one core event and persist its effects in this transaction."""
        result = StateMachine().dispatch(snapshot, event, actor, now=self.now, payload=payload)
        if not result.transitioned or result.to_state is None:
            raise ToolExecutionError(
                f"core rejected '{event}' in state "
                f"'{snapshot.state.value}': {result.rejection_reason}"
            )
        self._store_snapshot(result.application)

        folded = [e for e in result.events if e.type not in EVENT_TYPE_VALUES]
        for entry in result.audit_entries:
            session.add(
                AuditEvent(
                    id=uuid4(),
                    occurred_at=entry.at or self.now,
                    actor_type=entry.actor_kind,
                    actor_id=entry.actor_name or "firstshift",
                    application_id=application.id,
                    candidate_id=candidate.id,
                    event_type=entry.event,
                    state_from=entry.from_state,
                    state_to=entry.to_state,
                    payload={
                        "details": entry.details,
                        "folded_events": [
                            {"type": e.type, "payload": e.payload} for e in folded
                        ],
                    },
                )
            )
        for core_event in result.events:
            if core_event.type not in EVENT_TYPE_VALUES:
                continue  # folded into the audit payload above
            append_event(
                session,
                EventEnvelope(
                    type=EventType(core_event.type),
                    candidate_id=candidate.id,
                    trace_id=self.trace_id,
                    payload=core_event.payload,
                ),
            )
        self._persist_outbox(session, application, candidate, result.outbox_messages)

        application.state = result.to_state.value
        application.state_changed_at = self.now
        candidate.state = result.to_state.value  # mirror rule
        return result.application

    def _persist_outbox(
        self,
        session: Session,
        application: Application,
        candidate: Candidate,
        outbox_messages: tuple[Any, ...],
    ) -> None:
        for message in outbox_messages:
            mapping = _OUTBOX_MAPPING.get(message.kind)
            if mapping is None:
                raise ToolExecutionError(
                    f"unmapped outbox kind '{message.kind}': the write must not "
                    "be dropped silently (rule 4)"
                )
            port, operation = mapping
            row_id = uuid4()
            session.add(
                OutboxMessage(
                    id=row_id,
                    port=port,
                    operation=operation,
                    payload=dict(message.payload),
                    idempotency_key=f"fs/{port}/{operation}/{application.id}/{row_id}",
                    status="pending",
                    related_entity_id=candidate.id,
                )
            )

    def _audit(
        self,
        session: Session,
        application: Application,
        candidate: Candidate,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=self.now,
                actor_type="agent",
                actor_id=f"agent/{self.agent}",
                application_id=application.id,
                candidate_id=candidate.id,
                event_type=event_type,
                state_from=application.state,
                state_to=application.state,
                payload=payload,
            )
        )
