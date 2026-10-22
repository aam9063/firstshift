"""T4 first half (S4): judge behind a port, versioned rubrics, scripted judge.

Spec source: specs/05-iteration-evals.md section 2, row 3: "LLM-as-judge with
a written rubric (1 to 5 per criterion), judge prompt versioned; calibrate the
judge on 15 hand-labeled conversations first and report agreement". The judge
sits behind a port: tests and CI use the deterministic ScriptedJudge and never
contact a model.
"""

from evals.judge.port import (
    ConversationTranscript,
    ConversationTurn,
    JudgePort,
    JudgeRuntimeError,
    OpenAIStyleJudge,
    ScriptedJudge,
)
from evals.judge.rubrics import (
    EXPECTED_RUBRICS,
    RUBRIC_DIR,
    load_all_rubrics,
    load_rubric,
)


def transcript(conversation_id: str = "conv-001") -> ConversationTranscript:
    return ConversationTranscript(
        conversation_id=conversation_id,
        language="es",
        turns=(
            ConversationTurn(role="agent", text="Hola: soy una IA de Lumbre Burger."),
            ConversationTurn(role="candidate", text="Si, doy mi consentimiento."),
            ConversationTurn(role="agent", text="Gracias. Trabajamos en Sol."),
        ),
    )


# ------------------------------------------------------------------ rubrics


def test_all_five_versioned_rubrics_exist_and_parse() -> None:
    assert {f"{name}-v1" for name in EXPECTED_RUBRICS} == {
        "clarity-v1",
        "warmth-v1",
        "brevity-v1",
        "language-v1",
        "honesty-v1",
    }
    for name in EXPECTED_RUBRICS:
        path = RUBRIC_DIR / f"{name}-v1.md"
        assert path.is_file(), f"missing rubric file: {path}"


def test_every_rubric_has_one_criterion_full_anchors_and_a_json_output_shape() -> None:
    rubrics = load_all_rubrics()
    assert [r.name for r in rubrics] == [f"{name}-v1" for name in EXPECTED_RUBRICS]
    for rubric in rubrics:
        assert rubric.criterion in EXPECTED_RUBRICS
        assert rubric.version == "v1"
        assert sorted(rubric.anchors) == [1, 2, 3, 4, 5]
        assert all(text.strip() for text in rubric.anchors.values())
        assert rubric.description.strip()
        assert rubric.output_shape.strip()
        assert rubric.output_shape.lstrip().startswith("{")


def test_rubric_output_shape_substitutes_to_valid_json() -> None:
    import json

    rubric = load_rubric("clarity-v1")
    concrete = rubric.concrete_output_shape()
    parsed = json.loads(concrete)
    assert parsed["criterion"] == "clarity"
    assert parsed["score"] == 3
    assert parsed["rationale"]


def test_load_rubric_rejects_unknown_names() -> None:
    try:
        load_rubric("charisma-v1")
    except KeyError as error:
        assert "charisma-v1" in str(error)
    else:
        raise AssertionError("unknown rubric must raise KeyError")


# ------------------------------------------------------------- the judge port


def test_scripted_judge_satisfies_the_judge_port_protocol() -> None:
    judge = ScriptedJudge()
    assert isinstance(judge, JudgePort)


def test_scripted_judge_returns_scripted_scores_with_model_and_rubric_version() -> None:
    rubrics = load_all_rubrics()
    judge = ScriptedJudge(scripted={"conv-001": {"clarity": 4, "honesty": 5}})
    judgement = judge.judge(transcript(), rubrics)
    assert judgement.conversation_id == "conv-001"
    assert {s.criterion for s in judgement.scores} == set(EXPECTED_RUBRICS)
    scores = {s.criterion: s.score for s in judgement.scores}
    assert scores["clarity"] == 4
    assert scores["honesty"] == 5
    for score in judgement.scores:
        assert 1 <= score.score <= 5
        assert score.rubric_version == "v1"
        assert score.rationale.strip()
    assert judgement.model  # the judge names its model
    assert judgement.rationale.strip()


def test_scripted_judge_is_deterministic_including_its_fallback() -> None:
    rubrics = load_all_rubrics()
    unscripted = ScriptedJudge()
    first = unscripted.judge(transcript(), rubrics)
    second = unscripted.judge(transcript(), rubrics)
    assert first == second, "same conversation and rubrics must give the same judgement"
    # A scripted table and the fallback never drift between runs either.
    assert ScriptedJudge().judge(transcript("conv-002"), rubrics) == ScriptedJudge().judge(
        transcript("conv-002"), rubrics
    )


def test_scripted_judge_scores_stay_within_the_1_to_5_range() -> None:
    rubrics = load_all_rubrics()
    judge = ScriptedJudge()
    for conversation_id in ("conv-003", "conv-004", "conv-005", "conv-006"):
        judgement = judge.judge(transcript(conversation_id), rubrics)
        for score in judgement.scores:
            assert 1 <= score.score <= 5


def test_scripted_judge_rejects_scores_outside_the_scale() -> None:
    try:
        ScriptedJudge(scripted={"conv-001": {"clarity": 9}})
    except ValueError as error:
        assert "clarity" in str(error)
    else:
        raise AssertionError("out-of-scale scripted score must be rejected")


def test_openai_style_judge_requires_a_key_and_never_runs_in_tests() -> None:
    import os

    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        try:
            OpenAIStyleJudge()
        except JudgeRuntimeError as error:
            assert "OPENAI_API_KEY" in str(error)
        else:
            raise AssertionError("construction without a key must fail")
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved

    # With a key present the judge constructs, but live judging is scaffold
    # only: calling it raises instead of contacting any endpoint.
    judge = OpenAIStyleJudge(api_key="test-only-key")
    assert isinstance(judge, JudgePort)
    assert judge.model
    try:
        judge.judge(transcript(), load_all_rubrics())
    except NotImplementedError:
        pass
    else:
        raise AssertionError("the live judge scaffold must not execute in tests")


def test_judgement_rubric_version_tracks_the_loaded_rubrics() -> None:
    rubrics = load_all_rubrics()
    judgement = ScriptedJudge().judge(transcript(), rubrics)
    for score in judgement.scores:
        rubric = load_rubric(f"{score.criterion}-v1")
        assert score.rubric_version == rubric.version
