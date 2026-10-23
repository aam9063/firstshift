"""Iteration-4 (T1, specs/05-iteration-evals.md section 4, clarity-v1 anchor 2
and brevity-v1 anchor 2): the screening questions are asked one per turn.

The scripted journey runs through the real eval path (evals.run.drive_
conversation, scripted model) for one persona per language (es, pt, en):

(a) no single outbound message contains more than one screening question,
(b) the three screening questions appear as three separate consecutive agent
    turns, in the expected order (right to work, minimum age, distance),
(c) the conversation reaches the same end state with the same screening facts
    captured (one save_screening_answers effect, eligibility ok, availability),
(d) exactly one save_screening_answers effect happens, strictly after the
    third question turn.

Before the fix the whole screening was one message asking three questions at
once, so (a), (b) and (d) fail against the pre-fix code.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.engine import Engine

from evals.checks.deterministic import ConversationAudit
from evals.personas.generate import generate_personas
from evals.personas.schema import Behaviour, Language, Persona
from evals.run import _ensure_seed, drive_conversation

# The three screening questions per language, in the designed order: right to
# work, minimum age, distance to the site.
SCREENING_QUESTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "es": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (r"trabajar en España", r"18 o más", r"Llegas bien al local")
    ),
    "pt": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (r"trabalhar em Portugal", r"18 ou mais", r"Chegas bem ao local")
    ),
    "en": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (r"can you work here", r"18 or older", r"get to the site")
    ),
}

LANGUAGE_TAG: dict[Language, str] = {
    Language.es: "es",
    Language.pt: "pt",
    Language.en: "en",
    Language.mixed: "es",
}


@pytest.fixture()
def sim_engine():
    from tests.test_sim_common import fresh_sim_engine

    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        yield engine
    finally:
        generator.close()


def _persona(language: Language, behaviour: Behaviour) -> Persona:
    personas = generate_personas(seed=42, count=44)
    return next(
        p
        for p in personas
        if p.language is language and p.behaviour is behaviour
    )


def _agent_turns(transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    return [turn for turn in transcript if turn["role"] == "agent"]


def _question_hits(text: str, tag: str) -> int:
    return sum(
        1 for pattern in SCREENING_QUESTION_PATTERNS[tag] if pattern.search(text)
    )


def _expected_final_state(persona: Persona) -> str:
    """The end state the pre-change journey reached (unchanged by the split):
    reliable personas work their first shift, the rest no-show on day 0."""
    return "first_shift_worked" if persona.reliability >= 0.5 else "no_show"


def _save_calls(events: list) -> list:
    return [
        event
        for event in events
        if event.type == "tool.call"
        and event.payload.get("tool") == "save_screening_answers"
        and event.payload.get("status") == "ok"
    ]


def _third_question_event(record: dict):
    """The message.out event carrying the third screening question."""
    tag = LANGUAGE_TAG[record["persona"].language]
    third = SCREENING_QUESTION_PATTERNS[tag][2]
    matches = [
        event
        for event in record["audit"].events
        if event.type == "message.out" and third.search(str(event.payload.get("body", "")))
    ]
    assert len(matches) == 1, (
        f"expected exactly one third-question message, found {len(matches)}"
    )
    return matches[0]


@pytest.mark.parametrize(
    "language", [Language.es, Language.pt, Language.en], ids=["es", "pt", "en"]
)
def test_no_outbound_message_asks_more_than_one_screening_question(
    sim_engine: Engine, language: Language
) -> None:
    persona = _persona(language, Behaviour.instant)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    tag = LANGUAGE_TAG[language]
    multi = [
        turn["text"]
        for turn in _agent_turns(record["transcript"])
        if _question_hits(turn["text"], tag) > 1
    ]
    assert not multi, (
        f"{len(multi)} outbound message(s) ask more than one screening "
        f"question: {multi}"
    )


@pytest.mark.parametrize(
    "language", [Language.es, Language.pt, Language.en], ids=["es", "pt", "en"]
)
def test_three_questions_in_three_consecutive_turns_in_order(
    sim_engine: Engine, language: Language
) -> None:
    persona = _persona(language, Behaviour.instant)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    tag = LANGUAGE_TAG[language]
    agent_turns = _agent_turns(record["transcript"])

    indices: list[int] = []
    for pattern in SCREENING_QUESTION_PATTERNS[tag]:
        matching = [i for i, turn in enumerate(agent_turns) if pattern.search(turn["text"])]
        assert len(matching) == 1, (
            f"expected exactly one turn for pattern {pattern.pattern}, found "
            f"{len(matching)}: {[agent_turns[i]['text'][:60] for i in matching]}"
        )
        indices.append(matching[0])

    assert indices == sorted(indices), (
        f"screening questions out of order: {indices} "
        f"({[agent_turns[i]['text'][:40] for i in indices]})"
    )
    assert indices == list(range(indices[0], indices[0] + 3)), (
        "the three screening questions must be three consecutive agent turns, "
        f"got indices {indices}"
    )


@pytest.mark.parametrize(
    "language", [Language.es, Language.pt, Language.en], ids=["es", "pt", "en"]
)
def test_same_end_state_and_screening_facts(
    sim_engine: Engine, language: Language
) -> None:
    persona = _persona(language, Behaviour.instant)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    audit: ConversationAudit = record["audit"]

    # Same end state as the single-message journey (the split changes how the
    # questions are asked, not where the conversation ends).
    assert record["final_state"] == _expected_final_state(persona), (
        f"final state {record['final_state']} != expected "
        f"{_expected_final_state(persona)}"
    )

    # The same screening facts, captured exactly once: one ok
    # save_screening_answers call with eligibility ok and the availability.
    saves = _save_calls(audit.events)
    assert len(saves) == 1, f"expected exactly one save, found {len(saves)}"
    result = saves[0].payload["result"]
    assert result["eligibility_ok"] is True
    assert result["availability"] == [persona.availability.value]

    # The core moved from consented to screening on the captured answers.
    screening_starts = [
        row
        for row in audit.audit_events
        if row.event_type == "screening_starts"
        and row.state_from == "consented"
        and row.state_to == "screening"
    ]
    assert len(screening_starts) == 1, (
        f"expected one consented->screening transition, found {len(screening_starts)}"
    )


@pytest.mark.parametrize(
    "language", [Language.es, Language.pt, Language.en], ids=["es", "pt", "en"]
)
def test_save_screening_answers_runs_once_after_the_third_question(
    sim_engine: Engine, language: Language
) -> None:
    persona = _persona(language, Behaviour.instant)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    saves = _save_calls(record["audit"].events)
    assert len(saves) == 1, f"expected exactly one save, found {len(saves)}"

    # The third question's turn and the save's turn are different message
    # steps, so their simulated timestamps order them reliably (within one
    # turn events share a timestamp and only the UUID orders them).
    third_question_at = _third_question_event(record).occurred_at
    save_at = saves[0].occurred_at
    assert save_at > third_question_at, (
        f"save_screening_answers at {save_at} must happen strictly after "
        f"the third question turn at {third_question_at}"
    )


def test_silent_mid_screening_candidate_still_ends_gracefully(
    sim_engine: Engine,
) -> None:
    """Preserve: a persona who goes silent mid-process must never be left
    stuck in an open state (graceful_dropout ground truth); with screening
    spanning several turns inside `consented`, the no-reply policy still
    benches with consent instead of stalling."""
    persona = _persona(Language.es, Behaviour.stops_replying)
    _ensure_seed(sim_engine, 42)

    record = drive_conversation(sim_engine, persona)
    assert record["final_state"] in ("benched", "withdrawn") or record[
        "final_state"
    ] in (
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
        "first_shift_worked",
    ), f"silent persona ended stuck in {record['final_state']}"
    assert record["final_state"] != "consented"
