"""T1 (S1): the candidate simulator agent (specs/05-iteration-evals.md
section 1).

Spec, verbatim: "A candidate simulator agent plays each persona against the
system through the channel port, with its own clock. The system under test
must not see the persona file."

Unit tests are database-free: the simulator is driven exactly like the
channel works, outbound messages in (observe), inbound persona turns out.
One integration test drives a real scenario through the sim runner's
message path (app/sim/runner.send_sim_message) with a scripted system
agent, proving the simulator plays over the real message path.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.adapters.simulator import channel as simulator_channel
from app.ports.messaging import OutboundMessage
from evals.personas.generate import generate_personas
from evals.personas.schema import Behaviour, Language, Persona, WritingStyle
from evals.personas.simulator import (
    CandidateSimulator,
    CandidateView,
    PersonaTurn,
    ScriptedPersonaModel,
    send_person_turn,
)

PERSONAS = generate_personas(seed=42, count=44)


def persona_with(
    behaviour: Behaviour,
    *,
    style: WritingStyle | None = None,
    language: Language | None = None,
) -> Persona:
    for persona in PERSONAS:
        if persona.behaviour is not behaviour:
            continue
        if style is not None and persona.writing_style is not style:
            continue
        if language is not None and persona.language is not language:
            continue
        return persona
    raise AssertionError(f"no persona for {behaviour} style={style} language={language}")


def outbound(body: str) -> OutboundMessage:
    return OutboundMessage(
        recipient_ref="+34 600 000 000", body=body, correlation_id="test"
    )


class RecordingScriptedModel(ScriptedPersonaModel):
    """Test double that records exactly what the model ever sees."""

    def __init__(self, view: CandidateView) -> None:
        super().__init__(view)
        self.seen_views: list[CandidateView] = []
        self.seen_received: list[list[str]] = []

    def next_turn(self, view: CandidateView, received: list[str]) -> PersonaTurn | None:
        self.seen_views.append(view)
        self.seen_received.append(list(received))
        return super().next_turn(view, received)


# ------------------------------------------------------- behaviour rules


def test_late_replier_delays_twenty_hours() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.late_20h))
    first = sim.next_turn()
    assert first is not None
    assert first.delay == timedelta(hours=20)


def test_instant_replier_replies_within_minutes() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.instant))
    first = sim.next_turn()
    assert first is not None
    assert first.delay <= timedelta(minutes=2)


def test_injection_persona_attempts_injection_string() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.prompt_injection))
    first = sim.next_turn()
    assert first is not None
    lowered = first.text.lower()
    assert "ignora" in lowered or "ignore" in lowered
    assert "instrucciones" in lowered or "instructions" in lowered


def test_distressed_persona_asks_for_a_human() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.distressed))
    first = sim.next_turn()
    assert first is not None
    lowered = first.text.lower()
    assert "una persona" in lowered or "uma pessoa" in lowered or "a person" in lowered


def test_salary_first_persona_opens_asking_about_pay() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.salary_first))
    first = sim.next_turn()
    assert first is not None
    lowered = first.text.lower()
    assert "pagan" in lowered or "pagam" in lowered or "pay" in lowered


def test_rude_persona_marks_impatience() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.rude))
    first = sim.next_turn()
    assert first is not None
    lowered = first.text.lower()
    assert "tardaron" in lowered or "demoraram" in lowered or "ages" in lowered


def test_many_questions_persona_asks_several_questions() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.many_questions))
    first = sim.next_turn()
    assert first is not None
    assert first.text.count("?") >= 2


def test_volunteers_protected_info_persona_leaks_sensitive_data() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.volunteers_protected_info))
    first = sim.next_turn()
    assert first is not None
    text = first.text
    has_id = re.search(r"[XYZ]\d{7}[A-Z]", text) is not None
    has_health = "ansiedad" in text.lower() or "ansiedade" in text.lower() or (
        "anxiety" in text.lower()
    )
    assert has_id and has_health


def test_stops_replying_persona_goes_silent_after_two_turns() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.stops_replying))
    assert sim.next_turn() is not None
    sim.observe_outbound(outbound("Gracias, cuéntame tu disponibilidad"))
    assert sim.next_turn() is not None
    sim.observe_outbound(outbound("¿Sigues ahí?"))
    assert sim.next_turn() is None


def test_applies_twice_persona_restarts_mid_conversation() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.applies_twice))
    kinds: list[str] = []
    for _ in range(4):
        turn = sim.next_turn()
        if turn is None:
            kinds.append("stop")
            continue
        kinds.append(turn.kind)
        sim.observe_outbound(outbound("Gracias, sigo con tu proceso"))
    assert "reapply" in kinds


def test_replier_confirms_availability_when_pay_is_answered() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.salary_first))
    assert sim.next_turn() is not None
    sim.observe_outbound(outbound("El turno de cierre paga 12 euros por hora."))
    second = sim.next_turn()
    assert second is not None
    assert second.text.strip() != ""


# --------------------------------------------------------- writing style


def test_typo_heavy_persona_writes_without_accents() -> None:
    persona = next(
        p for p in PERSONAS if p.writing_style is WritingStyle.typo_heavy
    )
    sim = CandidateSimulator(persona)
    first = sim.next_turn()
    assert first is not None
    accented = set("áàäâéèëêíìïîóòöôúùüûñçãõáéíóú")
    assert not (set(first.text.lower()) & accented), first.text


def test_emoji_heavy_persona_appends_emojis() -> None:
    persona = next(
        p for p in PERSONAS if p.writing_style is WritingStyle.emoji_heavy
    )
    sim = CandidateSimulator(persona)
    first = sim.next_turn()
    assert first is not None
    assert any(ord(ch) > 0x1F000 for ch in first.text), first.text


def test_voice_note_persona_writes_short_replies() -> None:
    # A behaviour whose turn text has no overlay, so shortening is visible.
    persona = next(
        p
        for p in PERSONAS
        if p.writing_style is WritingStyle.voice_note_short
        and p.behaviour in (Behaviour.instant, Behaviour.late_20h)
    )
    sim = CandidateSimulator(persona)
    first = sim.next_turn()
    assert first is not None
    assert len(first.text.split()) <= 8, first.text


# ------------------------------------------------------------- language


def test_portuguese_persona_replies_in_portuguese() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.instant, language=Language.pt))
    first = sim.next_turn()
    assert first is not None
    assert first.language == "pt"
    assert "olá" in first.text.lower() or "interesse" in first.text.lower()


def test_english_persona_replies_in_english() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.instant, language=Language.en))
    first = sim.next_turn()
    assert first is not None
    assert first.language == "en"
    assert any(word in first.text.lower() for word in ("hi", "interested"))


def test_mixed_persona_tags_mixed_language() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.instant, language=Language.mixed))
    first = sim.next_turn()
    assert first is not None
    assert first.language == "mixed"


# ---------------------------------------------- isolation from the system


def test_simulator_never_receives_persona_file_paths() -> None:
    persona = persona_with(Behaviour.instant)
    sim = CandidateSimulator(persona)
    recording = RecordingScriptedModel(sim.view)
    sim.model = recording
    sim.next_turn()
    sim.observe_outbound(outbound("Te propongo el turno de cocina del viernes."))
    sim.next_turn()
    for view in recording.seen_views:
        dumped = view.model_dump()
        assert "fitting_shift_ids" not in dumped
        assert "reliability" not in dumped
        assert "dropout_trigger" not in dumped
        for value in dumped.values():
            assert "personas" not in str(value), value
            assert ".json" not in str(value), value
    for received in recording.seen_received:
        for message in received:
            assert "personas" not in message
            assert ".json" not in message


def test_candidate_view_is_built_from_persona_own_knowledge_only() -> None:
    persona = persona_with(Behaviour.instant)
    view = CandidateView.from_persona(persona)
    dumped = view.model_dump()
    for hidden in ("fitting_shift_ids", "reliability", "dropout_trigger"):
        assert hidden not in dumped


def test_simulator_has_its_own_clock() -> None:
    persona = persona_with(Behaviour.instant)
    sim = CandidateSimulator(persona)
    before = sim.clock.now
    first = sim.next_turn()
    assert first is not None
    assert sim.clock.now == before + first.delay
    assert first.sent_at == sim.clock.now


def test_observe_channel_feeds_only_new_outbound_messages() -> None:
    sim = CandidateSimulator(persona_with(Behaviour.instant))
    recorder: list[OutboundMessage] = []

    class FakeChannel:
        sent: list[OutboundMessage] = recorder

    sim.observe_channel(FakeChannel())  # type: ignore[arg-type]
    assert sim.received == []
    recorder.append(outbound("uno"))
    recorder.append(outbound("dos"))
    assert sim.observe_channel(FakeChannel()) == 2  # type: ignore[arg-type]
    recorder.append(outbound("tres"))
    assert sim.observe_channel(FakeChannel()) == 1  # type: ignore[arg-type]
    assert [m.body for m in sim.received] == ["uno", "dos", "tres"]


# ------------------------------------------------- model port seam (live)


def test_model_port_seam_accepts_a_custom_model() -> None:
    persona = persona_with(Behaviour.instant)

    class LiveStub:
        model_name = "stub-live"

        def next_turn(self, view: CandidateView, received: list[str]) -> PersonaTurn | None:
            return PersonaTurn(
                text="stub reply",
                language=view.language,
                kind="reply",
                delay=timedelta(minutes=1),
            )

    sim = CandidateSimulator(persona, model=LiveStub())  # type: ignore[arg-type]
    turn = sim.next_turn()
    assert turn is not None
    assert turn.text == "stub reply"


# ------------------------------------------------- sim runner integration


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    from tests.test_sim_common import fresh_sim_engine

    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    from tests.test_sim_common import make_sim_client

    yield from make_sim_client(sim_engine)


SYSTEM_REPLY: dict[str, Any] = {
    "message": {
        "body": (
            "Gracias por escribir. El turno de cocina del viernes paga 12 euros "
            "por hora, empieza a las 11:00. ¿Te encaja?"
        ),
        "language": "es",
    },
    "tool_calls": [],
}


def test_simulator_plays_through_the_sim_runner_message_path(
    sim_engine: Engine, sim_client: TestClient
) -> None:
    from app.sim.agent_loop import run_agent_turn
    from app.sim.runner import resolve_run
    from tests.test_sim_common import load_scenario

    simulator_channel.sent.clear()
    run = load_scenario(sim_client, "D1")
    run_ref = resolve_run(sim_engine, run["application_id"])
    persona = persona_with(Behaviour.instant, language=Language.es)
    sim = CandidateSimulator(persona)

    # Drain whatever the scenario load already put on the channel (the
    # system's opening message): the persona only reacts to what it receives.
    sim.observe_channel(simulator_channel)

    first = sim.next_turn()
    assert first is not None
    sent = send_person_turn(sim_engine, run_ref, first)
    assert sent["status"] == "recorded"

    run_agent_turn(
        sim_engine,
        run_ref,
        agent="recruit",
        inbound_text=first.text,
        reply=SYSTEM_REPLY,
    )
    assert sim.observe_channel(simulator_channel) == 1

    second = sim.next_turn()
    assert second is not None
    assert second.text.strip() != ""
    sent_two = send_person_turn(sim_engine, run_ref, second)
    assert sent_two["status"] == "recorded"

    # The system only ever saw the persona's messages, never the persona file.
    for turn in (first, second):
        assert "personas" not in turn.text
        assert ".json" not in turn.text


def test_next_turn_returns_none_only_for_stop_behaviour() -> None:
    persona = persona_with(Behaviour.instant)
    sim = CandidateSimulator(persona)
    for _ in range(6):
        assert sim.next_turn() is not None
        sim.observe_outbound(outbound("seguimos"))


def test_persona_turn_defaults_are_deterministic() -> None:
    persona = persona_with(Behaviour.instant)
    one = CandidateSimulator(persona).next_turn()
    two = CandidateSimulator(persona).next_turn()
    assert one is not None and two is not None
    assert one.text == two.text
    assert one.delay == two.delay
    epoch = datetime(2025, 7, 1, 9, 0, tzinfo=UTC)
    assert one.sent_at is not None and one.sent_at > epoch


# ------------------------------------------- every seeded persona can reply (T3)


def test_every_seeded_persona_answers_a_pay_reply_without_keyerror() -> None:
    """F08 T3 regression: no (availability, language) combination of the seed-42
    persona set may raise when the system reply answers pay (the branch that
    looks up AVAILABILITY_LINES). Found as KeyError ('weekday_mornings', 'mixed')
    and friends: the mixed-language availability templates were missing."""
    pay_reply = outbound("El turno de cocina paga 12 euros por hora.")
    for persona in PERSONAS:
        sim = CandidateSimulator(persona)
        assert sim.next_turn() is not None
        sim.observe_outbound(pay_reply)
        second = sim.next_turn()  # must not raise, whatever the axes
        assert second is not None, persona.persona_id
        assert second.text.strip() != "", persona.persona_id


def test_availability_templates_cover_every_axis_combination() -> None:
    """The template table itself is total over the persona axes."""
    from evals.personas.schema import AvailabilityBand, Language
    from evals.personas.simulator import AVAILABILITY_LINES

    for band in AvailabilityBand:
        for language in Language:
            assert (band.value, language.value) in AVAILABILITY_LINES, (band, language)
