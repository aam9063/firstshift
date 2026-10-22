"""Scripted agent turns inside the simulator (F07, T4; specs/04-prototype.md
section 3).

T2's runner stood in for the agent loop with direct "system" dispatches. T4
wires the T1 agent layer in: a scenario step that says an agent message runs
as one real agent turn, driven by a ScriptedModel reply (LLM_MODE=scripted,
fully offline) so tests and the demo replay recorded conversations:

- the reply is Pydantic-validated against AgentOutput (re-ask on failure),
- tool calls go through AgentService.execute_tool, which re-checks the
  per-state allow-list at the dispatcher (G6) and records a ``tool.call``
  event applied or rejected,
- every turn is persisted as ``agent.turn`` with prompt version, model,
  latency and tokens (S6),
- the agent's reply message goes out through the simulator channel adapter
  and is persisted as a ``message.out`` event (template ``agent_reply``).

Why a SimAgentService subclass exists (the only two deltas, everything else is
inherited from AgentService):

1. Snapshot coherence: the direct dispatch path (candidate/manager steps and
   timers) reads and writes the run row's serialized snapshot
   (app/sim/store.py). Agent turns seed their cached snapshot from that same
   run snapshot and write the evolved snapshot back after the turn, so both
   paths continue from the same guard facts, fired timers and state.
2. Simulated time: the events table is append-only at the database
   (INV-5 trigger), so an event's ``occurred_at`` must be right at insert. The
   parent class leaves the envelope default (real wall clock) for the events
   it appends; here every event of the turn is stamped with the run's
   simulated now, keeping the stream's order coherent with the clock control.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.agents.base import AgentRunner, ToolOutcome
from app.agents.model_port import ScriptedModel
from app.agents.services import (
    EVENT_TYPE_VALUES,
    AgentService,
    ToolExecutionError,
)
from app.core.state_machine import Actor
from app.core.state_machine import Application as CoreApplication
from app.db.events import EventEnvelope, EventType, append_event
from app.db.models import Application, AuditEvent, Candidate
from app.ports.messaging import OutboundMessage
from app.sim.dispatch import NOTICE_VERSION
from app.sim.runner import _advance_message_step
from app.sim.store import RunRef, SimRun, snapshot_from_json, snapshot_to_json

AGENT_REPLY_TEMPLATE = "agent_reply"


class SimAgentService(AgentService):
    """AgentService bound to one scenario run: run-snapshot coherence plus
    simulated-time event stamps. Tool execution, allow-list enforcement
    (G6), audit folding and the outbox mapping are inherited unchanged."""

    def __init__(self, engine: Engine, *, run: RunRef, agent: str, now: datetime) -> None:
        super().__init__(
            engine,
            application_id=run.application_id,
            candidate_id=run.candidate_id,
            trace_id=run.trace_id,
            agent=agent,
            notice_version=NOTICE_VERSION,
            now=now,
        )
        self._run = run
        self._seed: CoreApplication | None = None
        if run.snapshot_json is not None:
            self._seed = snapshot_from_json(run.snapshot_json)
            self._snapshots[str(run.application_id)] = self._seed

    def persist_snapshot(self) -> None:
        """Write the evolved snapshot back so the next direct dispatch (or
        timer tick) continues from this exact point."""
        final = self._snapshots.get(str(self._run.application_id), self._seed)
        if final is None:
            return
        with Session(self.engine) as session, session.begin():
            sim_row = session.get(SimRun, self._run.id)
            assert sim_row is not None, f"scenario run vanished: {self._run.id}"
            sim_row.snapshot = snapshot_to_json(final)

    def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        """Widen the inherited signature to the AgentBackend protocol's
        Mapping and delegate unchanged."""
        return super().execute_tool(tool_name, dict(arguments))

    # -------------------------------------------------- sim-time stamps

    def record_event(
        self, event_type: EventType, payload: Mapping[str, Any]
    ) -> None:
        with Session(self.engine) as session, session.begin():
            append_event(
                session,
                EventEnvelope(
                    type=event_type,
                    candidate_id=self.candidate_id,
                    trace_id=self.trace_id,
                    occurred_at=self.now,
                    payload=dict(payload),
                ),
            )

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
        """Same dispatch-and-persist as AgentService._apply with one delta:
        the core envelope events carry the run's simulated time (module
        docstring, point 2)."""
        from app.core.state_machine import StateMachine

        result = StateMachine().dispatch(
            snapshot, event, actor, now=self.now, payload=payload
        )
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
                    occurred_at=self.now,
                    payload=core_event.payload,
                ),
            )
        self._persist_outbox(session, application, candidate, result.outbox_messages)

        application.state = result.to_state.value
        application.state_changed_at = self.now
        candidate.state = result.to_state.value  # mirror rule
        return result.application


def run_agent_turn(
    engine: Engine,
    run: RunRef,
    *,
    agent: str,
    inbound_text: str,
    reply: dict[str, Any],
) -> dict[str, Any]:
    """One scripted agent turn for a scenario run, as plain data.

    The turn advances the run's clock by one message step (like every
    simulated message), runs AgentRunner with the single scripted reply,
    delivers the reply through the simulator channel and persists the evolved
    snapshot back onto the run row.
    """
    now = _advance_message_step(engine, run)
    service = SimAgentService(engine, run=run, agent=agent, now=now)
    if service._seed is None:
        from app.sim.runner import NoActiveRun

        raise NoActiveRun("scenario run has no snapshot")

    result = AgentRunner(service, ScriptedModel([reply]), agent=agent).run_turn(
        inbound_text
    )

    if result.message is not None:
        with Session(engine) as session:
            phone = session.scalar(
                select(Candidate.phone).where(Candidate.id == run.candidate_id)
            )
            assert phone is not None, f"candidate vanished: {run.candidate_id}"
        simulator_channel.send_message(
            OutboundMessage(
                recipient_ref=phone,
                body=result.message.body,
                correlation_id=run.trace_id,
                quick_replies=[],
            )
        )
        with Session(engine) as session, session.begin():
            append_event(
                session,
                EventEnvelope(
                    type=EventType.MESSAGE_OUT,
                    candidate_id=run.candidate_id,
                    trace_id=run.trace_id,
                    occurred_at=now,
                    payload={
                        "template": AGENT_REPLY_TEMPLATE,
                        "agent": agent,
                        "body": result.message.body,
                        "language": result.message.language,
                    },
                ),
            )

    service.persist_snapshot()

    return {
        "status": result.status,
        "agent": agent,
        "state": result.state_after,
        "message": {
            "body": result.message.body,
            "language": result.message.language,
        }
        if result.message is not None
        else None,
        "tools": [
            {"status": outcome.status, "reason": outcome.reason}
            for outcome in result.tool_outcomes
        ],
    }
