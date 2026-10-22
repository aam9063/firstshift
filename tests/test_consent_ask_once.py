"""Iteration-3 (T1, specs/05-iteration-evals.md section 4, guardrail G2): the
consent ask is emitted exactly once per conversation, as the first outbound
message, never repeated after the candidate answers it.

The scripted journey runs through the real eval path (evals.run.drive_
conversation, scripted model) for a persona that answers immediately and for
one that answers 20 hours late: between the first contact and the screening
message exactly one consent ask may appear, and it must be the very first
outbound message of the conversation.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.engine import Engine

from evals.personas.generate import generate_personas
from evals.personas.schema import Behaviour, Persona
from evals.run import _ensure_seed, drive_conversation

# The consent ask wording of both scripted sources (webhook first message and
# the agent's consent body), across es/pt/en.
CONSENT_ASK = re.compile(
    r"consentimiento para|Autoriza continuar|consent to continue", re.IGNORECASE
)
SCREENING_MESSAGE = re.compile(r"Tres preguntas|Três perguntas|Three questions")


@pytest.fixture()
def sim_engine():
    from tests.test_sim_common import fresh_sim_engine

    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        yield engine
    finally:
        generator.close()


def _persona(behaviour: Behaviour) -> Persona:
    personas = generate_personas(seed=42, count=44)
    return next(p for p in personas if p.behaviour is behaviour)


@pytest.mark.parametrize("behaviour", [Behaviour.instant, Behaviour.late_20h])
def test_consent_ask_appears_once_as_the_first_outbound_message(
    sim_engine: Engine, behaviour: Behaviour
) -> None:
    persona = _persona(behaviour)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    transcript = record["transcript"]

    agent_turns = [turn for turn in transcript if turn["role"] == "agent"]
    assert agent_turns, "the conversation must have outbound messages"

    asks = [turn for turn in agent_turns if CONSENT_ASK.search(turn["text"])]
    assert len(asks) == 1, (
        f"expected exactly one consent ask, found {len(asks)}: "
        f"{[turn['text'][:60] for turn in asks]}"
    )
    # The single ask is the very first outbound message (first contact, G1/G2).
    assert asks[0] is agent_turns[0]

    screening = [
        index
        for index, turn in enumerate(agent_turns)
        if SCREENING_MESSAGE.search(turn["text"])
    ]
    assert screening, "the scripted journey must reach the screening message"
    assert agent_turns.index(asks[0]) < screening[0], (
        "the consent ask must precede the screening message"
    )

    # The ask is gated on stored consent: exactly one consent row exists, with
    # the notice version shown (G2).
    consents = record["audit"].consents
    assert len(consents) == 1
    assert consents[0].notice_version == "v1"
    assert consents[0].channel == "whatsapp"
