"""The live LLM judge (S4): the real model behind the existing JudgePort.

Spec source: specs/05-iteration-evals.md section 2, row 3: "LLM-as-judge with
a written rubric (1 to 5 per criterion), judge prompt versioned; calibrate the
judge on 15 hand-labeled conversations first and report agreement".

``LiveJudge`` prompts a chat completions model with the versioned rubric files
(description, all five score anchors and the exact output shape per criterion)
plus the conversation transcript, and replies are parsed against a strict
Pydantic schema: one 1-5 score and a rationale per rubric criterion, plus an
overall rationale. temperature is 0. A malformed reply is retried exactly once
with a repair instruction; a second malformed reply raises.

Configuration (12-factor):
- ``JUDGE_MODEL``: model id for judging. Default ``gpt-5-mini`` when the
  resolved value looks like a valid model id; otherwise the judge falls back
  to ``settings.openai_model``.
- ``OPENAI_API_KEY``: required. Construction without a key raises
  ``JudgeRuntimeError`` instead of degrading silently; tests and CI use
  ``ScriptedJudge`` via ``build_judge("scripted")``.

Caching: successful judgements are cached per (conversation id, rubric
version, model) under ``evals/.cache/`` (kept out of git by a ``.gitignore``
dropped inside the directory) so reruns do not repay identical calls and stay
deterministic.

No test or CI path contacts the network: ``tests/test_judge_live.py`` mocks
the endpoint with respx, and the default ``build_judge`` mode is "scripted".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.settings import settings
from evals.judge.port import (
    ConversationTranscript,
    CriterionScore,
    Judgement,
    JudgePort,
    JudgeRuntimeError,
    ScriptedJudge,
    _rubric_version_of,
)
from evals.judge.rubrics import Rubric

JUDGE_MODEL_DEFAULT = "gpt-5-mini"
DEFAULT_CACHE_DIR = Path("evals/.cache")

# A model id "looks valid": one token of letters, digits and . _ / - separators,
# at least two characters. Anything else falls back to settings.openai_model.
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,80}$")

_REPAIR_INSTRUCTION = (
    "Your previous reply was not valid: {detail}. Reply again with exactly one "
    "JSON object matching the required shape (one score and rationale per "
    "criterion, plus overall_rationale), with no markdown, no prose and no "
    "extra keys."
)


# ------------------------------------------------------------------- errors


class JudgeUnavailableError(JudgeRuntimeError):
    """The judge endpoint is unreachable, misconfigured or failing."""


class JudgeRateLimitedError(JudgeRuntimeError):
    """The judge endpoint answered 429: rate limited, no retry."""


class JudgeInvalidOutputError(JudgeRuntimeError):
    """The model reply did not match the schema, even after one repair ask."""


# ------------------------------------------------------- strict output schema


class LiveCriterionOutput(BaseModel):
    """One criterion's model reply: a 1-5 score and a grounded rationale."""

    score: int
    rationale: str = Field(min_length=1)

    @field_validator("score")
    @classmethod
    def _on_scale(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError(f"score must be 1-5, got {value}")
        return value


class LiveJudgeOutput(BaseModel):
    """The strict schema every model reply must satisfy."""

    scores: dict[str, LiveCriterionOutput]
    overall_rationale: str = Field(min_length=1)


# ----------------------------------------------------------------- LiveJudge


@dataclass(frozen=True)
class _PromptBundle:
    """The static rubric text and the per-conversation transcript text."""

    system: str
    user: str

    def messages(self, conversation: ConversationTranscript) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": f"{self.user}\n\n{self._transcript_text(conversation)}"},
        ]

    @staticmethod
    def _transcript_text(conversation: ConversationTranscript) -> str:
        lines = [f"preferred language: {conversation.language or 'unknown'}", ""]
        for turn in conversation.turns:
            body = turn.text.replace("\n", " ")
            lines.append(f"{turn.role}: {body}")
        return "\n".join(lines)


def _build_prompt(rubric: Sequence[Rubric]) -> _PromptBundle:
    sections: list[str] = []
    for entry in rubric:
        anchors = "\n\n".join(
            f"### {score}\n{entry.anchors[score]}" for score in sorted(entry.anchors)
        )
        sections.append(
            f"# Rubric: {entry.name} (criterion: {entry.criterion}, "
            f"version: {entry.version})\n\n"
            f"## What it measures\n\n{entry.description}\n\n"
            f"## Score anchors\n\n{anchors}\n\n"
            f"## Per-criterion output shape\n\n```json\n{entry.output_shape}\n```"
        )
    criteria = ", ".join(r.criterion for r in rubric)
    system = (
        "You are the quality judge for a recruiting assistant's conversations on "
        "WhatsApp. Score the conversation strictly against each written rubric "
        "below, using only the transcript as evidence. Cite specific turns in "
        "every rationale."
    )
    user = (
        f"Rubrics to apply ({criteria}):\n\n" + "\n\n".join(sections) + "\n\n"
        "Reply with exactly one JSON object and nothing else:\n"
        '{"scores": {"<criterion>": {"score": <integer 1-5>, "rationale": "<one or '
        'two sentences citing specific turns>"}}, "overall_rationale": "<one '
        'sentence>"}\n'
        "Include every criterion listed above and no others."
    )
    return _PromptBundle(system=system, user=user)


def _resolve_model(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("JUDGE_MODEL") or JUDGE_MODEL_DEFAULT
    if _MODEL_ID_RE.match(candidate):
        return candidate
    return settings.openai_model


class LiveJudge:
    """The real model judge, behind the same ``JudgePort`` as ScriptedJudge."""

    model: str

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        use_cache: bool = True,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise JudgeRuntimeError(
                "OPENAI_API_KEY is not set: the live judge is unavailable. "
                "Tests and CI must use ScriptedJudge."
            )
        self._api_key = key
        self.model = _resolve_model(model)
        self._injected_client = client
        self._client: Any | None = client
        self._cache_dir = Path(cache_dir)
        self._use_cache = use_cache

    # ------------------------------------------------------------ the port

    def judge(
        self, conversation: ConversationTranscript, rubric: Sequence[Rubric]
    ) -> Judgement:
        if not rubric:
            raise ValueError("LiveJudge.judge needs at least one rubric")
        rubric_version = _rubric_version_of(rubric)

        cached = self._cache_read(conversation.conversation_id, rubric_version)
        if cached is not None:
            return cached

        prompt = _build_prompt(rubric)
        messages = prompt.messages(conversation)
        criteria = [r.criterion for r in rubric]
        detail = ""
        for _attempt in range(2):  # initial ask + exactly one repair ask
            content = self._complete(messages)
            output, detail = self._parse(content, criteria)
            if output is not None:
                break
            messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": _REPAIR_INSTRUCTION.format(detail=detail)},
            ]
        else:
            raise JudgeInvalidOutputError(
                f"model reply for '{conversation.conversation_id}' did not match the "
                f"judge schema after one repair attempt: {detail}"
            )

        scores = tuple(
            CriterionScore(
                criterion=entry.criterion,
                rubric_version=entry.version,
                score=output.scores[entry.criterion].score,
                rationale=output.scores[entry.criterion].rationale,
            )
            for entry in rubric
        )
        judgement = Judgement(
            conversation_id=conversation.conversation_id,
            scores=scores,
            model=self.model,
            rationale=output.overall_rationale,
            rubric_version=rubric_version,
        )
        self._cache_write(conversation.conversation_id, rubric_version, judgement)
        return judgement

    # ------------------------------------------------------------- the model

    def _complete(self, messages: list[dict[str, str]]) -> str:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, max_retries=0)
        client: Any = self._client
        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except _rate_limit_errors() as error:
            raise JudgeRateLimitedError(
                f"judge model '{self.model}' is rate limited: {error}"
            ) from error
        except _unavailable_errors() as error:
            raise JudgeUnavailableError(
                f"judge model '{self.model}' is unavailable: {error}"
            ) from error
        return response.choices[0].message.content or ""

    @staticmethod
    def _parse(content: str, criteria: Sequence[str]) -> tuple[LiveJudgeOutput | None, str]:
        """Strict parse; returns (output, None-detail) or (None, failure detail)."""
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            return None, f"reply is not valid JSON ({error.msg})"
        # the criteria set is checked first: pydantic's dict type would happily
        # accept a reply that omits or invents criteria
        if isinstance(payload, dict) and isinstance(payload.get("scores"), dict):
            expected = set(criteria)
            present = set(payload["scores"])
            if present != expected:
                problems: list[str] = []
                missing = sorted(expected - present)
                extra = sorted(present - expected)
                if missing:
                    problems.append(f"missing criteria {missing}")
                if extra:
                    problems.append(f"unexpected criteria {extra}")
                return None, "; ".join(problems)
        try:
            output = LiveJudgeOutput.model_validate(payload)
        except ValidationError as error:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}"
                for e in error.errors(include_url=False)
            )
            return None, detail
        return output, ""

    # --------------------------------------------------------------- cache

    def _cache_path(self, conversation_id: str, rubric_version: str) -> Path:
        digest = hashlib.sha256(
            f"{conversation_id}|{rubric_version}|{self.model}".encode()
        ).hexdigest()[:16]
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", conversation_id)[:60]
        return self._cache_dir / f"{safe_id}-{digest}.json"

    def _cache_read(self, conversation_id: str, rubric_version: str) -> Judgement | None:
        if not self._use_cache:
            return None
        path = self._cache_path(conversation_id, rubric_version)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            scores = tuple(
                CriterionScore(**score) for score in payload["scores"]
            )
            return Judgement(
                conversation_id=payload["conversation_id"],
                scores=scores,
                model=payload["model"],
                rationale=payload["rationale"],
                rubric_version=payload["rubric_version"],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None  # a corrupt cache entry is a miss, never a wrong answer

    def _cache_write(
        self, conversation_id: str, rubric_version: str, judgement: Judgement
    ) -> None:
        if not self._use_cache:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self._cache_dir / ".gitignore"
        if not gitignore.is_file():
            gitignore.write_text("*\n", encoding="utf-8")
        payload: dict[str, Any] = asdict(judgement)
        self._cache_path(conversation_id, rubric_version).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ------------------------------------------------------------------ factory


def _rate_limit_errors() -> tuple[type[Exception], ...]:
    from openai import RateLimitError

    return (RateLimitError,)


def _unavailable_errors() -> tuple[type[Exception], ...]:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        InternalServerError,
    )

    return (AuthenticationError, APIConnectionError, InternalServerError, APIStatusError)


def build_judge(
    mode: str = "scripted",
    *,
    api_key: str | None = None,
    model: str | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> JudgePort:
    """Build the judge for a mode: "scripted" (default, CI) or "live".

    "live" requires an API key and refuses construction without one; pass
    ``model``/``cache_dir`` through to ``LiveJudge``.
    """
    if mode == "scripted":
        return ScriptedJudge()
    if mode == "live":
        return LiveJudge(api_key=api_key, model=model, cache_dir=cache_dir)
    raise ValueError(f"unknown judge mode '{mode}': expected 'scripted' or 'live'")
