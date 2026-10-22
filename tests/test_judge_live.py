"""T4 second half (S4): the live LLM judge behind the existing JudgePort.

Spec source: specs/05-iteration-evals.md section 2, row 3: "LLM-as-judge with
a written rubric (1 to 5 per criterion), judge prompt versioned; calibrate the
judge on 15 hand-labeled conversations first and report agreement".

Every test here is offline via an injected client double: the OpenAI SDK
(3.x) vendors its own ``httpx2`` transport, which respx cannot intercept, so
each test injects an ``OpenAI`` client whose httpx transport is a
``MockTransport`` that records requests and replays scripted responses. No
test ever touches the network. ``ScriptedJudge`` stays the CI judge
untouched.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import OpenAI

from evals.judge import calibration
from evals.judge.live import (
    JUDGE_MODEL_DEFAULT,
    JudgeInvalidOutputError,
    JudgeRateLimitedError,
    JudgeUnavailableError,
    LiveJudge,
    build_judge,
)
from evals.judge.port import (
    ConversationTranscript,
    ConversationTurn,
    CriterionScore,
    Judgement,
    JudgePort,
    JudgeRuntimeError,
    ScriptedJudge,
)
from evals.judge.rubrics import Rubric, load_all_rubrics

RUBRICS: list[Rubric] = list(load_all_rubrics())
CRITERIA = [r.criterion for r in RUBRICS]
JOINED_VERSIONS = "+".join(sorted({r.version for r in RUBRICS}))


class MockOpenAI:
    """Offline chat completions double: records requests, replays responses.

    Responses are consumed in order; one more call than scripted responses is
    a hard failure, so every call-count assertion is implicit and exact.
    """

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.client = OpenAI(
            api_key="test-key",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(self._handle)),  # type: ignore[arg-type]
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(
                f"unexpected judge API call #{len(self.requests)}: no scripted response left"
            )
        return self._responses.pop(0)

    def enqueue(self, response: httpx.Response) -> None:
        self._responses.append(response)

    def last_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self.requests[-1].content)
        return payload

    def last_body(self) -> str:
        """The raw message contents of the last request, as plain text."""
        return "\n".join(m["content"] for m in self.last_payload()["messages"])


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


def model_payload(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "judge-test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def valid_content(score: int = 4) -> str:
    return json.dumps(
        {
            "scores": {
                criterion: {"score": score, "rationale": f"evidence for {criterion}"}
                for criterion in CRITERIA
            },
            "overall_rationale": "solid conversation overall",
        }
    )


def single_content(criterion: str, score: int = 4) -> str:
    """A valid reply for a single-criterion rubric set."""
    return json.dumps(
        {
            "scores": {
                criterion: {"score": score, "rationale": f"evidence for {criterion}"}
            },
            "overall_rationale": "ok",
        }
    )


def make_judge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, api: MockOpenAI, **kwargs: Any
) -> LiveJudge:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JUDGE_MODEL", "judge-test-model")
    kwargs.setdefault("cache_dir", tmp_path / "judge-cache")
    kwargs.setdefault("client", api.client)
    return LiveJudge(**kwargs)


# ------------------------------------------------------------- construction


def test_live_judge_refuses_construction_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(JudgeRuntimeError, match="OPENAI_API_KEY"):
        LiveJudge()


def test_model_from_judge_model_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = MockOpenAI(httpx.Response(200, json=model_payload(valid_content())))
    judge = make_judge(monkeypatch, tmp_path, api)
    assert judge.model == "judge-test-model"


def test_documented_default_model_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    judge = LiveJudge(cache_dir=tmp_path / "cache")
    assert judge.model == JUDGE_MODEL_DEFAULT == "gpt-5-mini"


def test_invalid_judge_model_env_falls_back_to_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.settings import settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JUDGE_MODEL", "not a model id!")
    judge = LiveJudge(cache_dir=tmp_path / "cache")
    assert judge.model == settings.openai_model


# ------------------------------------------------------------ request shape


def test_request_payload_carries_rubric_transcript_model_and_temperature(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(httpx.Response(200, json=model_payload(valid_content())))
    judge = make_judge(monkeypatch, tmp_path, api)
    judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 1
    assert str(api.requests[0].url).startswith("https://api.openai.com/v1/")
    payload = api.last_payload()
    assert payload["model"] == "judge-test-model"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    body = api.last_body()
    # every rubric file is in the prompt: description, all five anchors and
    # the exact output shape block
    for rubric in RUBRICS:
        assert rubric.name in body
        assert rubric.description.splitlines()[0] in body
        for anchor in rubric.anchors.values():
            assert anchor.splitlines()[0] in body
        assert rubric.output_shape in body
    # the transcript is in the prompt, with roles
    assert "Hola: soy una IA de Lumbre Burger." in body
    assert "Si, doy mi consentimiento." in body
    assert "agent:" in body and "candidate:" in body
    assert "preferred language: es" in body


# --------------------------------------------------------- response parsing


def test_valid_response_parses_into_judgement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(httpx.Response(200, json=model_payload(valid_content(score=4))))
    judge = make_judge(monkeypatch, tmp_path, api)
    judgement = judge.judge(transcript(), RUBRICS)

    assert isinstance(judge, JudgePort)
    assert judgement.conversation_id == "conv-001"
    assert judgement.model == "judge-test-model"
    assert judgement.rubric_version == JOINED_VERSIONS
    assert judgement.rationale == "solid conversation overall"
    assert [s.criterion for s in judgement.scores] == CRITERIA
    for score in judgement.scores:
        assert score.score == 4
        assert score.rubric_version == "v1"
        assert score.rationale.startswith("evidence for")


def test_invalid_output_repaired_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(
        httpx.Response(200, json=model_payload("this is not JSON at all")),
        httpx.Response(200, json=model_payload(valid_content())),
    )
    judge = make_judge(monkeypatch, tmp_path, api)
    judgement = judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 2
    assert judgement.score_for("clarity") is not None
    # the repair call repeats the rubric prompt and adds the repair instruction
    repair_body = api.last_body()
    assert "not valid" in repair_body
    assert api.last_payload()["temperature"] == 0


def test_invalid_output_twice_raises_after_one_repair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(
        httpx.Response(200, json=model_payload(valid_content(score=9))),
        httpx.Response(
            200,
            json=model_payload(
                json.dumps({"scores": {"clarity": {"score": 3, "rationale": "x"}}})
            ),
        ),
    )
    judge = make_judge(monkeypatch, tmp_path, api)
    with pytest.raises(JudgeInvalidOutputError, match="warmth"):
        judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 2  # exactly one repair attempt


def test_out_of_scale_score_is_invalid_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(
        httpx.Response(200, json=model_payload(valid_content(score=0))),
        httpx.Response(200, json=model_payload(valid_content(score=6))),
    )
    judge = make_judge(monkeypatch, tmp_path, api)
    with pytest.raises(JudgeInvalidOutputError, match="1-5"):
        judge.judge(transcript(), RUBRICS)


# ------------------------------------------------------------ model errors


def test_rate_limited_response_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(httpx.Response(429, json={"error": {"message": "slow down"}}))
    judge = make_judge(monkeypatch, tmp_path, api)
    with pytest.raises(JudgeRateLimitedError):
        judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 1  # no retry on rate limits


def test_server_error_raises_unavailable_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(httpx.Response(500, json={"error": {"message": "boom"}}))
    judge = make_judge(monkeypatch, tmp_path, api)
    with pytest.raises(JudgeUnavailableError):
        judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 1


# ------------------------------------------------------------------- cache


def test_cache_hit_avoids_second_http_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(httpx.Response(200, json=model_payload(valid_content())))
    judge = make_judge(monkeypatch, tmp_path, api)
    first = judge.judge(transcript(), RUBRICS)
    second = judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 1  # deterministic reuse: no second repayment
    assert first == second
    cache_dir = tmp_path / "judge-cache"
    assert any(cache_dir.glob("*.json"))
    assert (cache_dir / ".gitignore").is_file()  # cache stays out of git


def test_cache_key_separates_conversation_rubric_and_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(
        httpx.Response(200, json=model_payload(valid_content())),
        httpx.Response(200, json=model_payload(valid_content())),
    )
    judge = make_judge(monkeypatch, tmp_path, api)
    judge.judge(transcript("conv-001"), RUBRICS)
    judge.judge(transcript("conv-002"), RUBRICS)
    assert len(api.requests) == 2
    # a different rubric version must be a different cache key: every shipped
    # rubric is v1, so the version is what separates the sets
    v2_rubric = replace(RUBRICS[0], version="v2")
    api.enqueue(
        httpx.Response(200, json=model_payload(single_content(v2_rubric.criterion)))
    )
    judgement_v2 = judge.judge(transcript("conv-001"), [v2_rubric])
    assert len(api.requests) == 3
    assert judgement_v2.rubric_version == "v2"


def test_cache_disabled_contacts_the_model_every_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = MockOpenAI(
        httpx.Response(200, json=model_payload(valid_content())),
        httpx.Response(200, json=model_payload(valid_content())),
    )
    judge = make_judge(monkeypatch, tmp_path, api, use_cache=False)
    judge.judge(transcript(), RUBRICS)
    judge.judge(transcript(), RUBRICS)

    assert len(api.requests) == 2


# ----------------------------------------------------------------- factory


def test_build_judge_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert isinstance(build_judge("scripted"), ScriptedJudge)
    assert isinstance(build_judge(), ScriptedJudge)  # default: CI stays scripted
    with pytest.raises(ValueError, match="mode"):
        build_judge("yolo")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(JudgeRuntimeError):
        build_judge("live")

    judge = build_judge("live", api_key="test-key", cache_dir=tmp_path / "cache")
    assert isinstance(judge, LiveJudge)


# ------------------------------------------------- calibration CLI (live)


class FakeLiveJudge:
    """Offline stand-in for LiveJudge: scores every criterion 5."""

    model = "fake-live-judge/v1"

    def judge(self, conversation: ConversationTranscript, rubric: Any) -> Judgement:
        return Judgement(
            conversation_id=conversation.conversation_id,
            scores=tuple(
                CriterionScore(
                    criterion=r.criterion,
                    rubric_version=r.version,
                    score=5,
                    rationale="fake live label",
                )
                for r in rubric
            ),
            model=self.model,
            rationale="fake live label",
            rubric_version="+".join(sorted({r.version for r in rubric})),
        )


def _emit_worksheet(tmp_path: Path) -> Path:
    out = tmp_path / "worksheet.md"
    calibration.emit_worksheet([transcript()], RUBRICS, path=out)
    return out


def _report(tmp_path: Path) -> Path:
    report = tmp_path / "eval-test.json"
    report.write_text(
        json.dumps(
            {
                "conversations": [
                    {
                        "conversation_id": "conv-001",
                        "language": "es",
                        "transcript": [
                            {"role": "agent", "text": "Hola: soy una IA de Lumbre Burger."},
                            {"role": "candidate", "text": "Si, doy mi consentimiento."},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return report


def _scripted_score(criterion: str) -> int:
    score = ScriptedJudge().judge(transcript(), RUBRICS).score_for(criterion)
    assert score is not None
    return score.score


def _blank_judge_cell(worksheet: Path, criterion: str) -> None:
    """Blank the judge cell for one criterion, keeping the human column."""
    text = worksheet.read_text(encoding="utf-8")
    new_text, count = re.subn(
        rf"^\| {criterion} \| (\d*) \| \d+ \|$",
        rf"| {criterion} | \1 |  |",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, f"no judge cell found for {criterion}"
    worksheet.write_text(new_text, encoding="utf-8")


def _fill_human_column(worksheet: Path) -> None:
    """Label every human cell with the scripted score, like a filled worksheet."""
    text = worksheet.read_text(encoding="utf-8")
    for criterion in CRITERIA:
        score = _scripted_score(criterion)
        text = text.replace(
            f"| {criterion} |  | {score} |", f"| {criterion} | {score} | {score} |"
        )
    worksheet.write_text(text, encoding="utf-8")


def test_calibration_score_default_keeps_scripted_column(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worksheet = _emit_worksheet(tmp_path)
    _fill_human_column(worksheet)

    def _no_judge(mode: str, **kwargs: Any) -> None:
        raise AssertionError("default score must not build any live judge")

    monkeypatch.setattr(calibration, "build_judge", _no_judge)
    code = calibration.main(["score", "--worksheet", str(worksheet)])
    assert code == 0
    out = capsys.readouterr().out
    assert "exact agreement 100%" in out


def test_calibration_score_with_live_judge_fills_unscored_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worksheet = _emit_worksheet(tmp_path)
    _fill_human_column(worksheet)
    _blank_judge_cell(worksheet, "clarity")  # one unscored judge cell
    report = _report(tmp_path)
    monkeypatch.setattr(calibration, "build_judge", lambda mode, **kwargs: FakeLiveJudge())

    code = calibration.main(
        ["score", "--worksheet", str(worksheet), "--judge", "live", "--report", str(report)]
    )
    assert code == 0
    text = worksheet.read_text(encoding="utf-8")
    # filled by the fake live judge; the human column is untouched
    assert f"| clarity | {_scripted_score('clarity')} | 5 |" in text
    assert "| clarity |  |  |" not in text
    # the untouched scripted cells stay exactly as emitted
    for criterion in ("warmth", "brevity", "language", "honesty"):
        score = _scripted_score(criterion)
        assert f"| {criterion} | {score} | {score} |" in text
    out = capsys.readouterr().out
    assert "| clarity | 1 |" in out  # the agreement table counts the filled row
    assert "fake-live-judge/v1" in out


def test_calibration_score_live_mode_without_unscored_rows_never_builds_judge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worksheet = _emit_worksheet(tmp_path)
    _fill_human_column(worksheet)
    report = _report(tmp_path)

    def _no_judge(mode: str, **kwargs: Any) -> None:
        raise AssertionError("no unscored rows: no judge call needed")

    monkeypatch.setattr(calibration, "build_judge", _no_judge)
    code = calibration.main(
        ["score", "--worksheet", str(worksheet), "--judge", "live", "--report", str(report)]
    )
    assert code == 0
    assert "exact agreement 100%" in capsys.readouterr().out
