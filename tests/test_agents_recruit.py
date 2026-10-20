"""T1 (S1): scripted Recruit conversation against the persisted core.

The ScriptedModel satisfies the model-port interface so the conversation runs
fully offline (no OpenAI, no Twilio: the only network is the local Postgres
test schema every DB test in this repo already uses).

Journey: application in `contacted`, three agent turns drive
contacted -> consented -> screening -> matched purely through allowed tools
(capture_consent, save_screening_answers, get_open_shifts, propose_shifts),
with agent.turn, tool.call and state.transition events persisted.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.agents.base import AgentRunner
from app.agents.model_port import ScriptedModel
from app.agents.services import AgentService
from app.db.events import Event
from app.db.models import Application, Candidate, Consent, OpenShift, Restaurant
from tests.test_db_models import fresh_migrated_schema

NOW = datetime(2025, 6, 6, 21, 40, tzinfo=UTC)
TRACE_ID = "trc-test-recruit"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    with fresh_migrated_schema() as eng:
        yield eng


@pytest.fixture()
def ids(engine: Engine) -> Iterator[tuple[UUID, UUID]]:
    """One restaurant, one candidate, one application in `contacted`."""
    restaurant_id, candidate_id, application_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            Restaurant(
                id=restaurant_id,
                code=f"R{restaurant_id.hex[:3].upper()}",
                brand_id="lumbre",
                name="Lumbre Test",
                city="Madrid",
                timezone="Europe/Madrid",
                bench_enabled=True,
            )
        )
        session.flush()
        session.add(
            Candidate(
                id=candidate_id,
                brand_id="lumbre",
                first_name="Marta",
                phone="+34600000001",
                preferred_language="es",
                state="contacted",
                source="qr",
            )
        )
        session.flush()
        session.add(
            Application(
                id=application_id,
                candidate_id=candidate_id,
                restaurant_id=restaurant_id,
                state="contacted",
                entered_at=NOW,
                state_changed_at=NOW,
            )
        )
        session.add(
            OpenShift(
                id=uuid4(),
                restaurant_id=restaurant_id,
                shiftgrid_shift_id=f"sg-{restaurant_id.hex[:8]}",
                starts_at=datetime(2025, 6, 13, 18, 0, tzinfo=UTC),
                ends_at=datetime(2025, 6, 13, 23, 0, tzinfo=UTC),
                role="kitchen",
                requires_food_hygiene=True,
                status="open",
            )
        )
    yield application_id, candidate_id


def _scripted_replies(shift_id: UUID) -> list[dict[str, object]]:
    return [
        # Turn 1: consent (contacted -> consented)
        {
            "message": {
                "body": "Gracias, Marta. Tu consentimiento queda registrado.",
                "language": "es",
            },
            "tool_calls": [{"name": "capture_consent", "arguments": {"channel": "whatsapp"}}],
            "extracted_facts": {"consent_granted": True, "language": "es"},
        },
        # Turn 2: screening answers (consented -> screening)
        {
            "message": {
                "body": "Anotado: puedes trabajar los viernes y sabados.", "language": "es"
            },
            "tool_calls": [
                {
                    "name": "save_screening_answers",
                    "arguments": {
                        "right_to_work": True,
                        "minimum_age_confirmed": True,
                        "distance_ok": True,
                    },
                }
            ],
            "extracted_facts": {
                "right_to_work": True,
                "minimum_age_confirmed": True,
                "distance_ok": True,
            },
        },
        # Turn 3: shift match (screening -> matched)
        {
            "message": {
                "body": "Tengo un turno para ti el viernes 13 de 18 a 23.", "language": "es"
            },
            "tool_calls": [
                {"name": "get_open_shifts", "arguments": {}},
                {"name": "propose_shifts", "arguments": {"shift_ids": [str(shift_id)]}},
            ],
        },
    ]


def test_scripted_recruit_conversation_reaches_matched_via_tools(
    engine: Engine, ids: tuple[UUID, UUID]
) -> None:
    application_id, candidate_id = ids
    with Session(engine) as session:
        application = session.get(Application, application_id)
        assert application is not None
        shift_id = session.scalar(
            select(OpenShift.id).where(OpenShift.restaurant_id == application.restaurant_id)
        )
        assert shift_id is not None

    service = AgentService(
        engine,
        application_id=application_id,
        candidate_id=candidate_id,
        trace_id=TRACE_ID,
        agent="recruit",
        notice_version="v1",
        now=NOW,
    )
    model = ScriptedModel(_scripted_replies(shift_id))
    runner = AgentRunner(service, model, agent="recruit")

    runner.run_turn("Si, acepto el consentimiento")
    runner.run_turn("Tengo derecho a trabajar, soy mayor de edad, vivo cerca")
    result = runner.run_turn("Que turnos tienes?")

    # The record ended in `matched`, mirrored on candidate and application.
    assert result.state_after == "matched"
    with Session(engine) as session:
        application = session.get(Application, application_id)
        candidate = session.get(Candidate, candidate_id)
        assert application is not None and candidate is not None
        assert application.state == "matched"
        assert candidate.state == "matched"

        # Consent stored with timestamp and notice version (C-L1, G2).
        consent = session.scalar(select(Consent).where(Consent.candidate_id == candidate_id))
        assert consent is not None
        assert consent.channel == "whatsapp"
        assert consent.notice_version == "v1"
        assert consent.granted_at == NOW

        # Typed events: 3 agent.turn, 4 tool.call, 3 state.transition.
        types = [row.type for row in session.scalars(select(Event)).all()]
        assert types.count("agent.turn") == 3
        assert types.count("tool.call") == 4
        assert types.count("state.transition") == 3

        # S6 metadata on the agent turns: prompt version, model, latency, tokens.
        turns = [
            row.payload
            for row in session.scalars(
                select(Event).where(Event.type == "agent.turn")
            ).all()
        ]
        assert all(t["prompt_version"] == "v1" for t in turns)
        assert all(t["model"] == "scripted" for t in turns)
        assert all(t["latency_ms"] >= 0 for t in turns)
        assert all(t["tokens"]["output"] >= 0 for t in turns)

        # Rejections would have failed the journey loudly; every tool call is ok.
        calls = [
            row.payload
            for row in session.scalars(
                select(Event).where(Event.type == "tool.call")
            ).all()
        ]
        assert [c["tool"] for c in calls] == [
            "capture_consent",
            "save_screening_answers",
            "get_open_shifts",
            "propose_shifts",
        ]
        assert all(c["status"] == "ok" for c in calls)
