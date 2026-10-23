"""Eval runner (T5, S6): drive personas through the real sim runner and
publish the versioned eval report.

Spec source: specs/05-iteration-evals.md section 3, verbatim: "uv run python
-m evals.run --suite full --seed 42 --label vN produces evals/reports/eval-vN.md
with: summary table vs previous version, failing deterministic checks (must be
zero), worst 5 conversations by judge score with links, fairness table, cost
per hire, and a 'what changed' section filled from the iteration log." Plus:
"Keep a fast suite (10 personas, under 3 minutes) for every change and a full
suite before closing an iteration."

How one conversation runs (the harness is the simulated world; the system
under test is everything it observes):

1. A fresh candidate and application enter through the real HireDesk webhook
   path (same dispatch as a real application), with the persona's own name,
   phone and pilot restaurant. A sim run is created over a scripted snapshot
   that seeds the manager's open interview slot (the only world fact the
   conversation needs up front).
2. The CandidateSimulator plays the persona over the simulator channel with
   its own clock; each persona turn is delivered through the sim runner's
   message path (``send_person_turn``) and the run clock is advanced to the
   persona's send time first, so nudges fire on the real timer path.
3. The system's agent turn is a scripted model reply (LLM_MODE=scripted,
   deterministic, fully offline). The harness composes the reply per state
   from the same data the tools return (open shifts from the mock seed, the
   manager slot from the snapshot): the scripted model stands in for the LLM
   that would have seen those tool results. Tool calls go through the real
   dispatcher and allow-list; every turn is persisted as ``agent.turn``.
4. The world reacts: candidates attend interviews (interview attendance is
   always confirmed in this simulation; the hidden ``reliability`` gates the
   day-1 show), managers approve offers, documents complete, shifts are
   picked. A distressed persona's manager breaches the decision SLA so the
   real escalation timer fires. A persona who goes silent is either benched
   by the 48 h timer (still in contact) or benched by the agent's
   no-reply policy (screening), which are the designed graceful endings.
5. The persisted audit trail is bundled as a ``ConversationAudit`` and run
   through the six deterministic checks. Any failing check stops the suite
   with exit code 2 before any report is written (the checks must be 100%).
6. Task success, funnel, fairness, cost and judge scores are computed by
   ``evals.metrics`` over the bundles, and the JSON + markdown reports are
   written to ``evals/reports/eval-<label>.{json,md}``.

Reproducibility: seeded personas, seeded clocks, scripted model, scripted
judge (``ScriptedJudge``, CI default; any ``JudgePort`` implementation can be
injected). No network anywhere in the default path.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.webhooks import NOTICE_VERSION, HireDeskNewApplication, hiredesk_webhook
from app.core.state_machine import Actor, ActorKind, State
from app.core.state_machine import Application as CoreApplication
from app.db.events import Event
from app.db.models import Application, AuditEvent, Candidate, Consent, Decision
from app.db.seed import seed_restaurants
from app.settings import settings
from app.sim.agent_loop import run_agent_turn
from app.sim.runner import advance_clock, resolve_run
from app.sim.scenarios import get_scenario
from app.sim.store import (
    RunRef,
    reset_and_create_run,
    snapshot_to_json,
)
from evals.checks.deterministic import (
    ConversationAudit,
    _protected_hits,
    run_deterministic_checks,
)
from evals.judge.port import (
    ConversationTranscript,
    ConversationTurn,
    JudgePort,
    ScriptedJudge,
)
from evals.judge.rubrics import load_all_rubrics
from evals.metrics import (
    cost_latency,
    fairness,
    funnel,
    task_success,
)
from evals.personas.generate import DEFAULT_COUNT, generate_personas
from evals.personas.schema import Behaviour, Persona
from evals.personas.simulator import (
    PERSONA_EPOCH,
    CandidateSimulator,
    send_person_turn,
)

DEFAULT_REPORTS_DIR = Path("evals/reports")
DEFAULT_ITERATION_LOG = Path("docs/iteration-log.md")
SUITES: dict[str, int] = {"fast": 10, "full": DEFAULT_COUNT}

# World constants of the simulated pilot: the manager's open interview slot
# (seeded into the run snapshot) and the first shift the manager picks.
MANAGER_SLOT_OFFSET = timedelta(days=1)
FIRST_SHIFT_OFFSET = timedelta(days=6)
# Hidden reliability at or above which the persona shows up on day 1.
SHOW_THRESHOLD = 0.5
MAX_PERSONA_TURNS = 8

DONE_STATES = frozenset(
    {"first_shift_worked", "no_show", "benched", "withdrawn", "not_selected"}
)

# Scenario per behaviour: distressed runs against the manager-SLA scenario,
# injection and protected-info personas against their red-team scenarios.
SCENARIO_BY_BEHAVIOUR: dict[Behaviour, str] = {
    Behaviour.distressed: "D5",
    Behaviour.prompt_injection: "D6",
    Behaviour.volunteers_protected_info: "D7",
}
DEFAULT_SCENARIO = "D1"

# Candidate preferred_language is an es/pt/en enum: mixed personas are
# tagged and answered in Spanish (the conversation opens mixed anyway).
LANGUAGE_TAGS: dict[str, str] = {"es": "es", "pt": "pt", "en": "en", "mixed": "es"}

# Scripted agent message bodies (WhatsApp-sized, per language). The proposal
# body carries the pay information the persona rules wait for.
AGENT_BODIES: dict[str, dict[str, str]] = {
    "consent": {
        "es": (
            "Hola {name}: soy la asistente de IA de Lumbre Burger. "
            "¿Me das tu consentimiento para seguir por aquí?"
        ),
        "pt": (
            "Olá {name}: sou a assistente de IA da Lumbre Burger. "
            "Autoriza continuar por aqui?"
        ),
        "en": (
            "Hi {name}: I am Lumbre Burger's AI assistant. "
            "Do you consent to continue here?"
        ),
    },
    "proposal": {
        "es": "Encajas con el turno propuesto: paga 12 euros por hora. ¿Te encaja?",
        "pt": "Encaixas no turno proposto: paga 12 euros por hora. Te interessa?",
        "en": "You fit the proposed shift: it pays 12 euros per hour. Does it work?",
    },
    "booked": {
        "es": "Te apunto la entrevista para la hora acordada con el manager.",
        "pt": "Marco a tua entrevista para a hora acordada com o manager.",
        "en": "I have booked your interview for the agreed time with the manager.",
    },
    "decided": {
        "es": "He pasado tu resumen al manager para la decisión de contratación.",
        "pt": "Passei o teu resumo ao manager para a decisão de contratação.",
        "en": "I have sent your summary to the manager for the hiring decision.",
    },
    "bench": {
        "es": (
            "Te guardo en la bolsa de empleo del restaurante y te escribo "
            "cuando haya un turno para ti."
        ),
        "pt": (
            "Deixo-te na bolsa de emprego do restaurante e escrevo-te "
            "quando houver um turno para ti."
        ),
        "en": (
            "I am keeping you on the restaurant bench and will write "
            "when a shift fits you."
        ),
    },
}

# Screening asks one question per turn (iteration-4): the ordered per-language
# question bodies. The first question keeps the three-questions framing so the
# candidate knows why more messages are coming; each message carries exactly
# one question (clarity-v1 anchor 2, brevity-v1 anchor 2). The consent-once
# test's screening locator (tests/test_consent_ask_once.py) keys on the same
# framing.
SCREENING_QUESTIONS: dict[str, tuple[str, str, str]] = {
    "es": (
        "Gracias. Tres preguntas, una a una. ¿Puedes trabajar en España?",
        "¿Tienes 18 o más?",
        "¿Llegas bien al local?",
    ),
    "pt": (
        "Obrigado. Três perguntas, uma a uma. Podes trabalhar em Portugal?",
        "Tens 18 ou mais?",
        "Chegas bem ao local?",
    ),
    "en": (
        "Thanks. Three questions, one at a time. Can you work here?",
        "Are you 18 or older?",
        "Can you get to the site?",
    ),
}

DECISION_SUMMARY = (
    "Resumen de screening: elegible, encaje con el turno propuesto, entrevista completada."
)


# --------------------------------------------------------------- engine setup


@contextlib.contextmanager
def eval_engine() -> Iterator[Engine]:
    """A throwaway Postgres schema migrated to head, dropped on exit.

    Same pattern as the test fixtures: the eval suite must never touch the
    development schema (audit rows are append-only).
    """
    admin = create_engine(settings.database_url)
    schema = f"fs_eval_{uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.commit()
    saved = os.environ.get("DATABASE_URL")
    from urllib.parse import quote

    os.environ["DATABASE_URL"] = (
        f"{settings.database_url}?options=-csearch_path%3D{quote(schema)}"
    )
    try:
        from alembic.config import Config

        from alembic import command

        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "alembic")
        cfg.set_main_option("prepend_sys_path", ".")
        command.upgrade(cfg, "head")
        engine = create_engine(os.environ["DATABASE_URL"])
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved
        with admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.commit()
        admin.dispose()


def _ensure_seed(engine: Engine, seed: int) -> None:
    """Idempotently seed the world's client data into the throwaway schema.

    The restaurants come from the seed CSV (upsert on the site code); the
    open shifts from the same seeded generator the persona ground truth uses
    (``generate_open_shifts`` at SHIFT_SEED_DATE), upserted on the ShiftGrid
    id, so the system under test proposes real shifts and the ground truth
    refers to the same shift universe.
    """
    from app.db.models import OpenShift, Restaurant
    from evals.personas.generate import SHIFT_SEED_DATE
    from mocks.services.seed import generate_open_shifts, load_restaurants

    with engine.begin() as conn:
        seed_restaurants(conn)
        pilot = [r for r in load_restaurants() if r.is_pilot]
        restaurant_ids = dict(
            conn.execute(select(Restaurant.code, Restaurant.id)).all()
        )
        existing = set(conn.execute(select(OpenShift.shiftgrid_shift_id)).scalars())
        for shift in generate_open_shifts(pilot, SHIFT_SEED_DATE, seed=seed):
            if shift.shiftgrid_shift_id in existing:
                continue
            existing.add(shift.shiftgrid_shift_id)  # the generator can repeat a slot
            conn.execute(
                insert(OpenShift).values(
                    id=uuid4(),
                    restaurant_id=restaurant_ids[shift.restaurant_id],
                    shiftgrid_shift_id=shift.shiftgrid_shift_id,
                    starts_at=shift.starts_at,
                    ends_at=shift.ends_at,
                    role=shift.role,
                    requires_food_hygiene=shift.role == "kitchen",
                    status="open",
                )
            )


# ------------------------------------------------------------ suite selection


def select_personas(suite: str, personas: list[Persona]) -> list[Persona]:
    """fast = the first 10 personas of the seeded bundle; full = all of them.

    The seeded bundle's order is deterministic for the same seed and count,
    so the fast suite is a stable prefix and its numbers stay comparable
    across versions.
    """
    if suite not in SUITES:
        raise ValueError(f"unknown suite '{suite}': expected one of {sorted(SUITES)}")
    return personas[: SUITES[suite]]


# ------------------------------------------------------------- run lifecycle


def _start_run(engine: Engine, persona: Persona) -> RunRef:
    """A fresh candidate/application through the real webhook, plus the run row."""
    scenario_id = SCENARIO_BY_BEHAVIOUR.get(persona.behaviour, DEFAULT_SCENARIO)
    scenario = get_scenario(scenario_id)
    simulator_channel.sent.clear()
    token = uuid4().hex[:10]
    with Session(engine) as session, session.begin():
        payload = HireDeskNewApplication(
            event="new_application",
            event_id=f"eval-{persona.persona_id.lower()}-{token}",
            application_id=f"hd-eval-{persona.persona_id.lower()}-{token}",
            candidate_id=f"hdc-eval-{token}",
            restaurant_id=persona.restaurant_id,
            first_name=persona.first_name,
            phone=persona.phone,
            source="qr",
            # The persona's language is the intake's stated language: the
            # candidate record carries it from creation, so timer nudges and
            # canned guard replies composed before the first agent turn
            # (save_language_tag) already follow the stated preference (C-O4).
            language=LANGUAGE_TAGS[persona.language.value],
        )
        created = hiredesk_webhook(payload=payload, session=session)
        assert isinstance(created, dict), "a fresh eval application cannot be a replay"
        application = session.get(Application, UUID(created["application_id"]))
        assert application is not None
        application_id = application.id
        base_at = application.state_changed_at
        snapshot = CoreApplication(
            application_id=str(application.id),
            state=State(application.state),
            notice_version=NOTICE_VERSION,
            # The persona's language, not a literal: the core snapshot carries
            # the candidate's language from intake on (iteration-2), so the
            # language guardrail measures the candidate's real language.
            language=LANGUAGE_TAGS[persona.language.value],
            contacted_at=base_at,
            # The only world fact seeded up front: the manager's open slot.
            manager_open_slots=(base_at + MANAGER_SLOT_OFFSET,),
        )
        reset_and_create_run(
            session,
            scenario_id=scenario_id,
            trace_id=payload.event_id,
            hiredesk_application_id=payload.application_id,
            candidate_id=application.candidate_id,
            application_id=application.id,
            manager_id=scenario.manager.id,
            manager_name=scenario.manager.name,
            base_at=base_at,
            clock_offset_seconds=0.0,
            snapshot=snapshot_to_json(snapshot),
            created_at=datetime.now(UTC),
        )
    return resolve_run(engine, str(application_id))


def _current_state(engine: Engine, run: RunRef) -> str:
    with Session(engine) as session:
        return str(
            session.scalar(
                select(Application.state).where(Application.id == run.application_id)
            )
        )


def _refresh(engine: Engine, run: RunRef) -> RunRef:
    """Re-read the run row: RunRef.snapshot_json goes stale after every turn.

    The dispatch path seeds from the run row's serialized snapshot, so every
    agent turn, dispatch and clock advance must start from a fresh RunRef.
    """
    return resolve_run(engine, str(run.application_id))


def _sim_now(engine: Engine, run: RunRef) -> datetime:
    from app.sim.store import SimRun

    with Session(engine) as session:
        row = session.get(SimRun, run.id)
        offset = float(row.clock_offset_seconds) if row else 0.0
    return run.base_at + timedelta(seconds=offset)


def _advance_to(engine: Engine, run: RunRef, when: datetime) -> RunRef:
    """Move the run clock to `when`, firing every timer due on the way."""
    run = _refresh(engine, run)
    delta = (when - _sim_now(engine, run)).total_seconds() / 60
    if delta > 0:
        advance_clock(engine, run, minutes=delta)
    return _refresh(engine, run)


def _record_protected_refusal(engine: Engine, run: RunRef, inbound_text: str) -> None:
    """G3: a volunteered protected characteristic is never stored; the agent
    records the refusal event (the scripted agent's designed behavior)."""
    if not _protected_hits(inbound_text):
        return
    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=_sim_now(engine, run),
                actor_type="agent",
                actor_id="agent/recruit",
                application_id=run.application_id,
                candidate_id=run.candidate_id,
                event_type="protected_data_refused",
                state_from=None,
                state_to=None,
                payload={
                    "reason": (
                        "candidate volunteered protected data in an inbound message; "
                        "not stored and not followed up (G3)"
                    )
                },
            )
        )


# ----------------------------------------------------------- scripted replies


def _open_shift_ids(engine: Engine, run: RunRef, limit: int = 3) -> list[str]:
    """The open shifts the get_open_shifts tool would return, top of the list.

    The scripted model composes its proposal from the same data the tool
    returns; the persona's hidden ground truth is never consulted here.
    """
    from app.db.models import OpenShift

    with Session(engine) as session:
        restaurant_id = session.scalar(
            select(Application.restaurant_id).where(Application.id == run.application_id)
        )
        rows = session.scalars(
            select(OpenShift)
            .where(OpenShift.restaurant_id == restaurant_id, OpenShift.status == "open")
            .order_by(OpenShift.starts_at)
        ).all()
        return [str(row.id) for row in rows[:limit]]


def _body(key: str, persona: Persona) -> str:
    tag = LANGUAGE_TAGS[persona.language.value]
    return AGENT_BODIES[key][tag].format(name=persona.first_name)


def _consent_row_exists(engine: Engine, run: RunRef) -> bool:
    """Whether a consent record is already stored for this candidate (G2):
    the consent ask is only composed while none exists."""
    with Session(engine) as session:
        row = session.scalar(
            select(Consent.id).where(Consent.candidate_id == run.candidate_id).limit(1)
        )
        return row is not None


def _asked_screening_questions(engine: Engine, run: RunRef, tag: str) -> int:
    """How many of the three screening questions this conversation already
    asked (iteration-4). The scripted composer only ever asks the next one in
    order, so the count is the index of the next question; the flow stays in
    `consented` until all three are asked and answered."""
    asked = set(SCREENING_QUESTIONS[tag])
    with Session(engine) as session:
        bodies = session.scalars(
            select(Event.payload["body"]).where(
                Event.trace_id == run.trace_id,
                Event.type == "message.out",
            )
        ).all()
    return sum(1 for body in bodies if body in asked)


def _capture_outstanding_consent(engine: Engine, run: RunRef, persona: Persona) -> RunRef:
    """One change (iteration-3): a candidate reply while a consent ask is
    outstanding answers it, so consent is captured through the core before
    the agent composes its next message. The HireDesk first contact sends the
    consent ask without capturing consent, so without this the scripted reply
    for ("new", "contacted") asked again before its own capture_consent tool
    call ran: the candidate saw the same ask twice.

    As before (the capture_consent tool path), the scripted eval treats the
    candidate's first reply as the consent reply regardless of its wording,
    and the Consent row mirrors what the tool records (channel, purpose,
    notice version, simulated timestamp)."""
    tag = LANGUAGE_TAGS[persona.language.value]
    run = _dispatch(
        engine,
        run,
        event="candidate_consents",
        role=ActorKind.CANDIDATE,
        payload={"channel": "whatsapp", "language": tag},
    )
    with Session(engine) as session, session.begin():
        session.add(
            Consent(
                id=uuid4(),
                candidate_id=run.candidate_id,
                channel="whatsapp",
                purpose="screening",
                notice_version=NOTICE_VERSION,
                granted_at=_sim_now(engine, run),
            )
        )
    return run


def _scripted_reply(engine: Engine, run: RunRef, persona: Persona) -> dict[str, Any]:
    """The recruit agent's scripted reply for the current state (deterministic).

    Composed per state from the data the tools would have returned; tool
    calls still go through the real dispatcher and its allow-list (G6).
    """
    tag = LANGUAGE_TAGS[persona.language.value]
    state = _current_state(engine, run)

    # The consent ask is composed only while no consent record exists (G2):
    # once consent is stored the conversation moves on, it never asks again.
    if state in ("new", "contacted") and not _consent_row_exists(engine, run):
        return {
            "message": {"body": _body("consent", persona), "language": tag},
            "tool_calls": [
                {"name": "capture_consent", "arguments": {"channel": "whatsapp", "language": tag}}
            ],
        }
    if state == "consented":
        # One change (iteration-4): screening asks one question per turn and
        # the flow stays in `consented` while questions are outstanding. Each
        # reply is answered with the next question; the answers are captured
        # together, exactly once, after the third (save_screening_answers), so
        # the core receives the same facts as the single three-question turn
        # did. The tool allow-list is untouched: save_screening_answers
        # transitions to `screening` inside this turn, so get_open_shifts and
        # propose_shifts run within the screening allow-list exactly as they
        # did in the old screening-state turn.
        asked = _asked_screening_questions(engine, run, tag)
        if asked < len(SCREENING_QUESTIONS[tag]):
            return {
                "message": {
                    "body": SCREENING_QUESTIONS[tag][asked],
                    "language": tag,
                },
                "tool_calls": (
                    [{"name": "save_language_tag", "arguments": {"language": tag}}]
                    if asked == 0
                    else []
                ),
            }
        # All three questions asked and answered: capture the screening facts
        # and proceed exactly as the old screening-state turn did.
        shift_ids = _open_shift_ids(engine, run)
        return {
            "message": {"body": _body("proposal", persona), "language": tag},
            "tool_calls": [
                {
                    "name": "save_screening_answers",
                    "arguments": {
                        "right_to_work": True,
                        "minimum_age_confirmed": True,
                        "distance_ok": True,
                        "availability": [persona.availability.value],
                    },
                },
                {"name": "get_open_shifts", "arguments": {}},
                {"name": "propose_shifts", "arguments": {"shift_ids": shift_ids}},
            ],
        }
    if state == "screening":
        shift_ids = _open_shift_ids(engine, run)
        return {
            "message": {"body": _body("proposal", persona), "language": tag},
            "tool_calls": [
                {"name": "get_open_shifts", "arguments": {}},
                {"name": "propose_shifts", "arguments": {"shift_ids": shift_ids}},
            ],
        }
    if state == "matched":
        slot = (run.base_at + MANAGER_SLOT_OFFSET).isoformat()
        return {
            "message": {"body": _body("booked", persona), "language": tag},
            "tool_calls": [{"name": "book_interview_slot", "arguments": {"slot": slot}}],
        }
    if state == "interviewed":
        return {
            "message": {"body": _body("decided", persona), "language": tag},
            "tool_calls": [
                {"name": "request_manager_decision", "arguments": {"summary": DECISION_SUMMARY}}
            ],
        }
    # interview_booked and any later state: an acknowledging reply, no tools.
    return {"message": {"body": _body("booked", persona), "language": tag}, "tool_calls": []}


def _dispatch(
    engine: Engine, run: RunRef, *, event: str, role: ActorKind, payload: dict | None = None,
    snapshot_updates: dict | None = None, when: datetime | None = None,
) -> RunRef:
    from app.sim.dispatch import dispatch_and_persist

    run = _refresh(engine, run)
    dispatch_and_persist(
        engine,
        run,
        event=event,
        actor=Actor(role, run.manager_name if role is ActorKind.MANAGER else "firstshift-sim"),
        now=when or _sim_now(engine, run),
        payload=payload or {},
        snapshot_updates=snapshot_updates,
    )
    return _refresh(engine, run)


def _record_approval_decision(engine: Engine, run: RunRef, when: datetime) -> None:
    """The simulated manager's approval is recorded as a Decision row (INV-1:
    who, when and the facts seen), as the approval effect expects."""
    with Session(engine) as session, session.begin():
        session.add(
            Decision(
                id=uuid4(),
                application_id=run.application_id,
                type="offer",
                recommended_by="agent/recruit (scripted)",
                decided_by=run.manager_name,
                decided_at=when,
                facts_seen=uuid4(),  # the summary reference in the sim world
            )
        )


def _world_steps(engine: Engine, run: RunRef, persona: Persona) -> None:
    """The simulated world's reactions, until it waits on the candidate.

    Interview attendance is always confirmed in this simulation (the hidden
    ``reliability`` gates the day-1 show); a distressed persona's manager
    breaches the decision SLA so the real escalation timer fires (H5).
    """
    while True:
        state = _current_state(engine, run)
        if state == "interview_booked":
            run = _dispatch(engine, run, event="interview_attended", role=ActorKind.CANDIDATE)
        elif state == "pending_manager_decision":
            if persona.behaviour is Behaviour.distressed:
                run = _advance_to(engine, run, _sim_now(engine, run) + timedelta(hours=9))
                # SLA breach: the real timer path fires remind + escalate.
            run = _dispatch(
                engine, run, event="approval_recorded", role=ActorKind.MANAGER,
                payload={
                    "approval": {
                        "manager_id": run.manager_id,
                        "manager_name": run.manager_name,
                        "decided_at": _sim_now(engine, run),
                        "facts_seen": DECISION_SUMMARY,
                    }
                },
            )
            _record_approval_decision(engine, run, _sim_now(engine, run))
        elif state == "offer_sent":
            run = _dispatch(engine, run, event="offer_accepted", role=ActorKind.CANDIDATE)
        elif state == "offer_accepted":
            run = _dispatch(engine, run, event="tracker_opened", role=ActorKind.SYSTEM)
        elif state == "preboarding":
            run = _dispatch(
                engine, run, event="tracker_completed", role=ActorKind.SYSTEM,
                snapshot_updates={"documents_complete": True, "csv_confirmed": True},
            )
        elif state == "ready_for_rota":
            run = _dispatch(
                engine, run, event="first_shift_picked", role=ActorKind.MANAGER,
                payload={"first_shift_at": run.base_at + FIRST_SHIFT_OFFSET},
                snapshot_updates={"hygiene_module_complete": True},
            )
        elif state == "first_shift_scheduled":
            first_shift_at = run.base_at + FIRST_SHIFT_OFFSET
            if persona.reliability >= SHOW_THRESHOLD:
                run = _dispatch(
                    engine, run, event="first_shift_confirmed", role=ActorKind.CANDIDATE,
                    when=first_shift_at - timedelta(hours=20),
                )
                run = _advance_to(engine, run, first_shift_at + timedelta(hours=8))
                run = _dispatch(
                    engine, run, event="shift_worked", role=ActorKind.CANDIDATE,
                    when=_sim_now(engine, run),
                )
            else:
                run = _advance_to(engine, run, first_shift_at + timedelta(hours=1))
                run = _dispatch(
                    engine, run, event="day0_no_show", role=ActorKind.TIMER,
                    when=_sim_now(engine, run),
                )
        else:
            return


def _handle_silence(engine: Engine, run: RunRef, persona: Persona) -> None:
    """The persona went silent: the designed graceful endings apply.

    Still in contact: the real 48 h bench timer path. Mid-screening (questions
    outstanding, so the flow is in `consented`) or in screening: the agent's
    no-reply policy benches with consent (benched_with_consent).
    """
    state = _current_state(engine, run)
    if state == "contacted":
        run = _advance_to(engine, run, _sim_now(engine, run) + timedelta(days=2))
        # nudge at 2 h, nudge at 24 h, bench at 48 h: the real timer path
    elif state == "consented" and _asked_screening_questions(
        engine, run, LANGUAGE_TAGS[persona.language.value]
    ):
        # The candidate went silent while screening questions are outstanding
        # (the flow stays in `consented` until the third answer, iteration-4):
        # the agent's no-reply policy still benches with consent, the same
        # graceful ending the screening state had. Core path: two system
        # dispatches, screening starts (the questions were asked), then the
        # bench with consent.
        tag = LANGUAGE_TAGS[persona.language.value]
        result = run_agent_turn(
            engine,
            _refresh(engine, run),
            agent="recruit",
            inbound_text="(sin respuesta)",
            reply={
                "message": {
                    "body": _body("bench", persona),
                    "language": tag,
                },
                "tool_calls": [],
            },
        )
        assert result["state"] == "consented", result
        run = _dispatch(engine, run, event="screening_starts", role=ActorKind.SYSTEM)
        run = _dispatch(
            engine, run, event="benched_with_consent", role=ActorKind.SYSTEM,
            payload={"bench_consent": True},
        )
        assert _current_state(engine, run) == "benched"
    elif state == "screening":
        result = run_agent_turn(
            engine,
            _refresh(engine, run),
            agent="recruit",
            inbound_text="(sin respuesta)",
            reply={
                "message": {"body": _body("bench", persona), "language": LANGUAGE_TAGS[
                    persona.language.value
                ]},
                "tool_calls": [
                    {"name": "add_to_bench", "arguments": {"bench_consent": True}}
                ],
            },
        )
        assert result["state"] == "benched", result


# ------------------------------------------------------------- audit bundling


def _collect_audit(engine: Engine, run: RunRef) -> ConversationAudit:
    """Bundle the persisted rows of one conversation for the eval layers."""
    with Session(engine) as session:
        candidate = session.get(Candidate, run.candidate_id)
        application = session.get(Application, run.application_id)
        assert candidate is not None and application is not None
        events = session.scalars(
            select(Event)
            .where(Event.trace_id == run.trace_id)
            .order_by(Event.occurred_at, Event.id)
        ).all()
        audit_events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.candidate_id == run.candidate_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        ).all()
        consents = session.scalars(
            select(Consent).where(Consent.candidate_id == run.candidate_id)
        ).all()
        decisions = session.scalars(
            select(Decision).where(Decision.application_id == run.application_id)
        ).all()
        for row in (candidate, application, *events, *audit_events, *consents, *decisions):
            session.expunge(row)
    return ConversationAudit(
        candidate=candidate,
        application=application,
        events=list(events),
        audit_events=list(audit_events),
        consents=list(consents),
        decisions=list(decisions),
    )


def _transcript(audit: ConversationAudit) -> list[dict[str, str]]:
    """The message transcript of one conversation, in stream order."""
    turns: list[dict[str, str]] = []
    for event in audit.events:
        if event.type == "message.in":
            body = event.payload.get("text")
            if body:
                turns.append(
                    {"role": str(event.payload.get("role", "candidate")), "text": str(body)}
                )
        elif event.type == "message.out":
            body = event.payload.get("body")
            if body:
                turns.append({"role": "agent", "text": str(body)})
    return turns


# ------------------------------------------------------------ one conversation


def drive_conversation(
    engine: Engine, persona: Persona, *, max_turns: int = MAX_PERSONA_TURNS
) -> dict[str, Any]:
    """Run one persona through the system and return the conversation record."""
    scenario_id = SCENARIO_BY_BEHAVIOUR.get(persona.behaviour, DEFAULT_SCENARIO)
    run = _start_run(engine, persona)
    sim = CandidateSimulator(persona)
    sim.observe_channel(simulator_channel)  # the system's opening message
    last_sent: datetime | None = None

    for _ in range(max_turns):
        if _current_state(engine, run) in DONE_STATES:
            break
        turn = sim.next_turn()
        if turn is None:
            _handle_silence(engine, run, persona)
            break
        # The run clock follows the persona's own timing, so timers fire on
        # the real path (nudges while unanswered, bench at 48 h).
        anchor = last_sent or PERSONA_EPOCH
        run = _advance_to(engine, run, _sim_now(engine, run) + (turn.sent_at - anchor))
        last_sent = turn.sent_at
        send_person_turn(engine, run, turn)
        _record_protected_refusal(engine, run, turn.text)
        run = _refresh(engine, run)
        # A reply to an outstanding consent ask captures consent first, so the
        # reply composition below never asks again (iteration-3, G2).
        if (
            _current_state(engine, run) == "contacted"
            and not _consent_row_exists(engine, run)
        ):
            run = _capture_outstanding_consent(engine, run, persona)
        run_agent_turn(
            engine,
            _refresh(engine, run),
            agent="recruit",
            inbound_text=turn.text,
            reply=_scripted_reply(engine, run, persona),
        )
        run = _refresh(engine, run)
        sim.observe_channel(simulator_channel)
        _world_steps(engine, run, persona)
        run = _refresh(engine, run)

    audit = _collect_audit(engine, run)
    return {
        "persona": persona,
        "audit": audit,
        "scenario_id": scenario_id,
        "trace_id": run.trace_id,
        "final_state": _current_state(engine, run),
        "transcript": _transcript(audit),
    }


# ------------------------------------------------------------------ reporting


def _judge_mean(scores) -> float:
    values = [score.score for score in scores]
    return sum(values) / len(values)


def _previous_report(out_dir: Path, label: str) -> tuple[dict | None, str | None]:
    """The previous version's report JSON, when one exists.

    For numeric labels (vN) the v(N-1) file is used when present; otherwise
    the most recently written other report in the directory is the previous
    version, so any label sequence keeps its summary comparison.
    """
    match = re.fullmatch(r"v(\d+)", label)
    if match is not None and int(match.group(1)) > 1:
        previous_label = f"v{int(match.group(1)) - 1}"
        path = out_dir / f"eval-{previous_label}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")), previous_label
        return None, previous_label
    candidates = [
        path
        for path in out_dir.glob("eval-*.json")
        if path.name != f"eval-{label}.json"
    ]
    if not candidates:
        return None, None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return json.loads(latest.read_text(encoding="utf-8")), latest.stem.removeprefix("eval-")


def _what_changed(iteration_log: Path) -> str:
    """The most recent entry of docs/iteration-log.md, verbatim."""
    if not iteration_log.is_file():
        return (
            f"no iteration log found at {iteration_log}; fill it to record the "
            "hypothesis behind this version"
        )
    content = iteration_log.read_text(encoding="utf-8").strip()
    if not content:
        return f"iteration log at {iteration_log} is empty"
    entries = re.split(r"\n(?=## )", content)
    return entries[-1].strip()


SUMMARY_ROWS: tuple[tuple[str, Callable[[dict], Any]], ...] = (
    ("task_success_rate", lambda summary: summary["task_success_rate"]),
    ("deterministic_failures", lambda summary: summary["deterministic_failures"]),
    ("interview_show_rate", lambda summary: summary["interview_show_rate"]),
    ("day1_show_rate", lambda summary: summary["day1_show_rate"]),
    ("median_ttfps_hours", lambda summary: summary["median_ttfps_hours"]),
    ("total_cost_usd", lambda summary: summary["total_cost_usd"]),
    ("cost_per_hired_usd", lambda summary: summary["cost_per_hired_usd"]),
    ("mean_judge_score", lambda summary: summary["mean_judge_score"]),
)


def _markdown_report(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    lines: list[str] = [
        f"# Eval report eval-{meta['label']}",
        "",
        f"Suite `{meta['suite']}`, seed {meta['seed']}, {meta['persona_count']} personas, "
        f"judge `{meta['judge_model']}`, generated {meta['generated_at']}.",
        "",
        "## Summary",
        "",
    ]
    comparison = payload.get("comparison") or {}
    previous_label = comparison.get("previous_label")
    if previous_label:
        lines.append(f"Compared against the previous version `{previous_label}`.")
        lines += [
            "",
            "| metric | eval-" + meta["label"] + " | eval-" + previous_label + " | delta |",
            "| --- | --- | --- | --- |",
        ]
        for name, getter in SUMMARY_ROWS:
            current = getter(payload["summary"])
            previous = getter(comparison["summary"])
            if isinstance(current, (int, float)) and isinstance(previous, (int, float)):
                delta = f"{current - previous:+.4g}"
            else:
                delta = "n/a"
            lines.append(f"| {name} | {current} | {previous} | {delta} |")
    else:
        lines.append(
            "No previous version to compare against: this run is the baseline."
        )
        lines += ["", "| metric | value |", "| --- | --- |"]
        for name, getter in SUMMARY_ROWS:
            lines.append(f"| {name} | {getter(payload['summary'])} |")

    checks = payload["deterministic_checks"]
    lines += [
        "",
        "## Deterministic checks",
        "",
        f"**{checks['failing']} failing** across {checks['checked_conversations']} "
        "conversation(s). The suite is 100% only at zero failures.",
        "",
        "| check | passed | failed |",
        "| --- | --- | --- |",
    ]
    for name, counts in checks["per_check"].items():
        lines.append(f"| {name} | {counts['passed']} | {counts['failed']} |")

    lines += [
        "",
        "## Worst 5 conversations",
        "",
        "Lowest mean judge score first; every trace is replayable in the console.",
        "",
        "| # | persona | judge mean | trace | label |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, conversation in enumerate(payload["worst_5"], start=1):
        lines.append(
            f"| {index} | {conversation['persona_id']} | {conversation['judge_mean']:.2f} | "
            f"`{conversation['trace_id']}` | {conversation['label']} |"
        )

    lines += [
        "",
        "## Task success",
        "",
        f"{payload['summary']['task_success']} of {payload['meta']['persona_count']} personas "
        f"reached their ground-truth end state ({payload['summary']['task_success_rate']:.0%}).",
        "",
        "| persona | expected | achieved | detail |",
        "| --- | --- | --- | --- |",
    ]
    for conversation in payload["conversations"]:
        lines.append(
            f"| {conversation['persona_id']} | {conversation['expected_outcome']} | "
            f"{'yes' if conversation['task_success'] else 'NO'} | {conversation['task_detail']} |"
        )

    lines += [
        "",
        "## Funnel",
        "",
        f"- conversations: {payload['funnel']['conversations']}",
        f"- interviews booked / attended: {payload['funnel']['booked_interviews']} / "
        f"{payload['funnel']['attended_interviews']} (show rate "
        f"{payload['summary']['interview_show_rate']:.0%})",
        f"- offers sent / ready for rota: {payload['funnel']['offers_sent']} / "
        f"{payload['funnel']['ready_for_rota']}",
        f"- first shifts scheduled / worked: {payload['funnel']['scheduled_first_shifts']} / "
        f"{payload['funnel']['worked_first_shifts']} (day-1 show rate "
        f"{payload['summary']['day1_show_rate']:.0%})",
        f"- median time to first contact: "
        f"{_fmt(payload['funnel']['median_time_to_first_contact_min'])} min",
        f"- median offer-to-rota: {_fmt(payload['funnel']['median_offer_to_rota_hours'])} h",
        f"- median TTFPS proxy: {_fmt(payload['funnel']['median_ttfps_hours'])} h "
        "(simulated clock: comparable proxy, not wall-clock)",
        "",
        "## Fairness",
        "",
        "Selection = reaching the interview or any later stage. Groups are synthetic proxies "
        "(language, profile); ratio vs the highest group rate, four-fifths rule at 0.8.",
        "",
        "| dimension | group | n | selected | rate | ratio | flagged |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["fairness"]:
        lines.append(
            f"| {row['dimension']} | {row['group']} | {row['n']} | {row['selected']} | "
            f"{row['rate']:.2f} | {row['ratio']:.2f} | {'REVIEW' if row['flagged'] else ''} |"
        )

    cost = payload["cost"]
    lines += [
        "",
        "## Cost per hire",
        "",
        f"- agent turns: {cost['turns']} across {cost['conversations']} conversation(s)",
        f"- tokens: {cost['total_input_tokens']} in / {cost['total_output_tokens']} out",
        f"- total USD: {cost['total_usd']:.4f} (scripted model priced at the "
        "gpt-4.1-mini proxy rate)",
        f"- hires (offer accepted): {cost['hired']}",
        f"- cost per hired candidate: {_fmt(cost['cost_per_hired_usd'])} USD",
        f"- p95 agent latency: {_fmt(cost['p95_latency_ms'])} ms",
        "",
        "## What changed",
        "",
        payload["what_changed"],
        "",
    ]
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


# -------------------------------------------------------------------- the run


def run_suite(
    suite: str,
    seed: int,
    label: str,
    *,
    out_dir: Path = DEFAULT_REPORTS_DIR,
    personas: list[Persona] | None = None,
    judge: JudgePort | None = None,
    engine: Engine | None = None,
    iteration_log: Path = DEFAULT_ITERATION_LOG,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run one eval suite end to end and write the JSON and markdown reports.

    Deterministic checks gate the suite: any failing check stops the run with
    exit code 2 before any artifact is written (S2: must be 100%).
    """
    started = time.monotonic()
    all_personas = (
        personas if personas is not None else generate_personas(seed=seed, count=DEFAULT_COUNT)
    )
    selected = select_personas(suite, all_personas)
    judge = judge or ScriptedJudge()
    rubrics = load_all_rubrics()

    with (
        contextlib.nullcontext(engine) if engine is not None else eval_engine()
    ) as eng:
        _ensure_seed(eng, seed)
        conversations: list[dict[str, Any]] = []
        for persona in selected:
            record = drive_conversation(eng, persona)
            checks = run_deterministic_checks(record["audit"])
            conversations.append({**record, "checks": checks})
            log(f"  {persona.persona_id}: {record['final_state']}")

        failures = [
            (record["persona"].persona_id, check)
            for record in conversations
            for check in record["checks"]
            if not check.passed
        ]
        if failures:
            for persona_id, check in failures:
                log(f"DETERMINISTIC CHECK FAILED [{persona_id}] {check.name}: {check.evidence}")
            log(
                f"deterministic checks failed ({len(failures)} failure(s)): the suite "
                "requires 100%; no report was written"
            )
            raise SystemExit(2)

        conversation_payloads: list[dict[str, Any]] = []
        for record in conversations:
            persona, audit = record["persona"], record["audit"]
            success = task_success(persona, audit)
            judgement = judge.judge(
                ConversationTranscript(
                    conversation_id=record["trace_id"],
                    turns=tuple(
                        ConversationTurn(**turn) for turn in record["transcript"]
                    ),
                    language=audit.candidate.preferred_language,
                ),
                rubrics,
            )
            conversation_payloads.append(
                {
                    "persona_id": persona.persona_id,
                    "label": f"{persona.behaviour.value}/{persona.language.value}",
                    "conversation_id": record["trace_id"],
                    "trace_id": record["trace_id"],
                    "scenario": record["scenario_id"],
                    "final_state": record["final_state"],
                    "expected_outcome": success.expected,
                    "task_success": success.achieved,
                    "task_detail": success.detail,
                    "judge_mean": round(_judge_mean(judgement.scores), 3),
                    "judge_scores": {
                        score.criterion: score.score for score in judgement.scores
                    },
                    "transcript": record["transcript"],
                }
            )

        audits = [record["audit"] for record in conversations]
        funnel_metrics = funnel(audits)
        fairness_rows = fairness(selected, audits)
        cost = cost_latency(audits)
        check_names = [check.name for check in conversations[0]["checks"]]
        per_check = {
            name: {
                "passed": sum(
                    1
                    for record in conversations
                    for check in record["checks"]
                    if check.name == name and check.passed
                ),
                "failed": sum(
                    1
                    for record in conversations
                    for check in record["checks"]
                    if check.name == name and not check.passed
                ),
            }
            for name in check_names
        }
        mean_judge = (
            sum(c["judge_mean"] for c in conversation_payloads) / len(conversation_payloads)
            if conversation_payloads
            else 0.0
        )
        summary = {
            "task_success": sum(1 for c in conversation_payloads if c["task_success"]),
            "task_success_rate": (
                sum(1 for c in conversation_payloads if c["task_success"])
                / len(conversation_payloads)
                if conversation_payloads
                else 0.0
            ),
            "deterministic_failures": 0,
            "interview_show_rate": funnel_metrics.interview_show_rate,
            "day1_show_rate": funnel_metrics.day1_show_rate,
            "median_ttfps_hours": funnel_metrics.median_ttfps_hours,
            "total_cost_usd": round(cost.total_usd, 6),
            "cost_per_hired_usd": (
                round(cost.cost_per_hired_usd, 6)
                if cost.cost_per_hired_usd is not None
                else None
            ),
            "mean_judge_score": round(mean_judge, 3),
        }
        previous, previous_label = _previous_report(out_dir, label)
        comparison = None
        if previous is not None:
            comparison = {"previous_label": previous_label, "summary": previous["summary"]}
        elif previous_label is not None:
            comparison = {"previous_label": previous_label, "summary": None}

        elapsed = time.monotonic() - started
        payload: dict[str, Any] = {
            "meta": {
                "suite": suite,
                "seed": seed,
                "label": label,
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "persona_count": len(selected),
                "judge_model": judge.model,
                "elapsed_seconds": round(elapsed, 1),
            },
            "summary": summary,
            "deterministic_checks": {
                "failing": 0,
                "checked_conversations": len(conversations),
                "per_check": per_check,
            },
            "conversations": conversation_payloads,
            "worst_5": sorted(
                conversation_payloads,
                key=lambda c: (c["judge_mean"], c["persona_id"]),
            )[:5],
            "funnel": asdict(funnel_metrics),
            "fairness": [asdict(row) for row in fairness_rows],
            "cost": asdict(cost),
            "comparison": comparison,
            "what_changed": _what_changed(iteration_log),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"eval-{label}.json"
    md_path = out_dir / f"eval-{label}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(payload), encoding="utf-8")
    log(f"wrote {json_path} and {md_path} in {payload['meta']['elapsed_seconds']}s")
    if suite == "fast" and elapsed > 180:
        raise SystemExit(f"fast suite took {elapsed:.0f}s: the 3-minute budget was exceeded")
    return payload


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run",
        description=(
            "Run the FirstShift eval suite (specs/05-iteration-evals.md section 3) "
            "and write evals/reports/eval-<label>.{json,md}."
        ),
    )
    parser.add_argument("--suite", choices=sorted(SUITES), default="fast",
                        help="fast = 10 personas (every change), full = all (before closing)")
    parser.add_argument("--seed", type=int, default=42, help="persona bundle seed")
    parser.add_argument("--label", default="v1", help="report version label, e.g. v2")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    args = parser.parse_args(argv)
    run_suite(args.suite, args.seed, args.label, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
