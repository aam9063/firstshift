"""The judge behind a port (S4, ports-and-adapters rule 2).

``JudgePort`` is the contract: ``judge(conversation, rubric) -> Judgement``
with one 1-5 score, rationale and rubric version per criterion, plus the model
name. Two implementations live behind it:

- ``ScriptedJudge``: fully deterministic. Tests and CI use it; reruns of the
  same conversation and rubrics always produce the identical Judgement.
- ``OpenAIStyleJudge``: a scaffold for the live model judge. It refuses to
  construct without an API key and its ``judge`` is not wired to any endpoint
  yet: live judging arrives with the runner (T5). Nothing in this module
  imports a model client, so no test or CI path can contact the network.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from evals.judge.rubrics import Rubric

MIN_SCORE = 1
MAX_SCORE = 5


class JudgeRuntimeError(RuntimeError):
    """The judge cannot run: configuration is missing (no API key)."""


@dataclass(frozen=True)
class ConversationTurn:
    """One message in the judged transcript."""

    role: str  # "agent" | "candidate" | "system"
    text: str


@dataclass(frozen=True)
class ConversationTranscript:
    """The conversation under judgment, as plain data the runner assembles."""

    conversation_id: str
    turns: tuple[ConversationTurn, ...]
    language: str | None = None  # stated preferred language, when known


@dataclass(frozen=True)
class CriterionScore:
    """One criterion's 1-5 score with its rubric version and rationale."""

    criterion: str
    rubric_version: str
    score: int
    rationale: str

    def __post_init__(self) -> None:
        if not MIN_SCORE <= self.score <= MAX_SCORE:
            raise ValueError(
                f"score for criterion '{self.criterion}' must be {MIN_SCORE}-{MAX_SCORE}, "
                f"got {self.score}"
            )


@dataclass(frozen=True)
class Judgement:
    """The judge's verdict over one conversation against one rubric set."""

    conversation_id: str
    scores: tuple[CriterionScore, ...]
    model: str
    rationale: str
    rubric_version: str  # the rubric versions behind this judgement, joined

    def score_for(self, criterion: str) -> CriterionScore | None:
        return next((s for s in self.scores if s.criterion == criterion), None)


@runtime_checkable
class JudgePort(Protocol):
    """The judge contract: conversation plus rubrics in, Judgement out."""

    def judge(
        self, conversation: ConversationTranscript, rubric: Sequence[Rubric]
    ) -> Judgement: ...


def _rubric_version_of(rubric: Sequence[Rubric]) -> str:
    versions = sorted({r.version for r in rubric})
    return "+".join(versions) if versions else "unversioned"


# ------------------------------------------------------------ ScriptedJudge


class ScriptedJudge:
    """Deterministic judge for tests and CI.

    Scores come from an optional scripted table keyed by conversation id and
    criterion. Conversations without a scripted entry get a stable fallback
    derived from a SHA-256 digest of (conversation id, criterion, rubric
    version): same input, same score, forever, with no randomness.
    """

    model = "scripted-judge/v0"

    def __init__(self, scripted: dict[str, dict[str, int]] | None = None) -> None:
        self._scripted: dict[str, dict[str, int]] = {}
        for conversation_id, table in (scripted or {}).items():
            for criterion, score in table.items():
                if not MIN_SCORE <= score <= MAX_SCORE:
                    raise ValueError(
                        f"scripted score for conversation '{conversation_id}', criterion "
                        f"'{criterion}' must be {MIN_SCORE}-{MAX_SCORE}, got {score}"
                    )
            self._scripted[conversation_id] = dict(table)

    def judge(
        self, conversation: ConversationTranscript, rubric: Sequence[Rubric]
    ) -> Judgement:
        if not rubric:
            raise ValueError("ScriptedJudge.judge needs at least one rubric")
        scores: list[CriterionScore] = []
        table = self._scripted.get(conversation.conversation_id, {})
        for entry in rubric:
            scripted_score = table.get(entry.criterion)
            if scripted_score is not None:
                score = scripted_score
                rationale = (
                    f"scripted label for '{entry.criterion}' per the {entry.name} table"
                )
            else:
                score = self._fallback(conversation.conversation_id, entry)
                rationale = (
                    f"scripted fallback for '{entry.criterion}' (deterministic digest of "
                    f"{conversation.conversation_id} against {entry.name})"
                )
            scores.append(
                CriterionScore(
                    criterion=entry.criterion,
                    rubric_version=entry.version,
                    score=score,
                    rationale=rationale,
                )
            )
        return Judgement(
            conversation_id=conversation.conversation_id,
            scores=tuple(scores),
            model=self.model,
            rationale="; ".join(s.rationale for s in scores),
            rubric_version=_rubric_version_of(rubric),
        )

    @staticmethod
    def _fallback(conversation_id: str, rubric: Rubric) -> int:
        digest = hashlib.sha256(
            f"{conversation_id}|{rubric.criterion}|{rubric.version}".encode()
        ).hexdigest()
        return MIN_SCORE + int(digest[:8], 16) % (MAX_SCORE - MIN_SCORE + 1)


# --------------------------------------------------------- OpenAIStyleJudge


class OpenAIStyleJudge:
    """Scaffold for the live model judge, behind the same port.

    Constructing without an API key raises instead of degrading silently.
    The judge method is intentionally not wired to any endpoint: live judging
    lands with the runner (T5) and is never exercised in tests or CI. When
    wired, it will prompt with the rubric's anchors and validate the reply
    against the rubric's JSON output shape, re-asking on malformed output.
    """

    model: str

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise JudgeRuntimeError(
                "OPENAI_API_KEY is not set: the live judge is unavailable. "
                "Tests and CI must use ScriptedJudge."
            )
        self._api_key = key
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

    def judge(
        self, conversation: ConversationTranscript, rubric: Sequence[Rubric]
    ) -> Judgement:
        raise NotImplementedError(
            "OpenAIStyleJudge is a scaffold: live judging arrives with the "
            "eval runner (T5) and is never contacted from tests or CI."
        )
