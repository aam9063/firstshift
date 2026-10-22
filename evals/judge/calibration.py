"""Judge calibration (S4): a labeling worksheet plus the agreement math.

Spec source: specs/05-iteration-evals.md section 2, row 3: "calibrate the
judge on 15 hand-labeled conversations first and report agreement".

- ``emit_worksheet`` writes a markdown worksheet with the calibration
  conversations, their transcripts and one blank human score cell per
  criterion; the judge column is pre-filled by the deterministic judge so the
  runner can compute agreement as soon as the human column is filled.
- ``load_worksheet`` reads the worksheet back, filled or blank.
- ``agreement`` computes exact and within-1 agreement (|human - judge| <= 1)
  overall and per criterion, over the rows both parties scored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from evals.judge.port import ConversationTranscript, JudgePort, ScriptedJudge
from evals.judge.rubrics import Rubric

CALIBRATION_CONVERSATIONS = 15

_CRITERIA_ORDER = ("clarity", "warmth", "brevity", "language", "honesty")
_CONVERSATION_RE = re.compile(r"^##\s+Conversation\s+(\S+)\s*$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|([^|]+)\|([^|]*)\|([^|]*)\|\s*$", re.MULTILINE)


def _score_cell(cell: str) -> int | None:
    text = cell.strip()
    if not text:
        return None
    value = int(text)
    if not 1 <= value <= 5:
        raise ValueError(f"worksheet score must be 1-5, got {value}")
    return value


@dataclass(frozen=True)
class CalibrationRow:
    """One conversation x criterion with its human and judge scores."""

    conversation_id: str
    criterion: str
    human_score: int | None
    judge_score: int | None

    def __post_init__(self) -> None:
        for name in ("human_score", "judge_score"):
            value = getattr(self, name)
            if value is not None and not 1 <= value <= 5:
                raise ValueError(f"{name} for '{self.criterion}' must be 1-5, got {value}")


@dataclass(frozen=True)
class CriterionAgreement:
    criterion: str
    n: int
    exact_rate: float
    within_1_rate: float


@dataclass(frozen=True)
class AgreementResult:
    n: int
    exact_rate: float
    within_1_rate: float
    per_criterion: tuple[CriterionAgreement, ...]


# -------------------------------------------------------------- the worksheet


def emit_worksheet(
    transcripts: list[ConversationTranscript],
    rubrics: list[Rubric],
    *,
    path: Path,
    judge: JudgePort | None = None,
) -> Path:
    """Write the labeling worksheet and return its path.

    One section per conversation: the transcript, then a score table with one
    blank human cell per criterion and the scripted judge's score pre-filled.
    """
    if not transcripts:
        raise ValueError("emit_worksheet needs at least one conversation")
    if not rubrics:
        raise ValueError("emit_worksheet needs at least one rubric")
    judge = judge or ScriptedJudge()

    criteria = [r.criterion for r in rubrics]
    lines: list[str] = [
        "# Judge calibration worksheet",
        "",
        f"Label each conversation on every criterion ({', '.join(criteria)}) with a 1-5 "
        "score using the anchors in evals/judge/rubrics/<criterion>-v1.md. Fill the human "
        "score column only: the judge column is pre-filled and stays as-is.",
        "",
    ]
    for transcript in transcripts:
        judgement = judge.judge(transcript, rubrics)
        lines.extend(
            [
                f"## Conversation {transcript.conversation_id}",
                "",
                f"preferred language: {transcript.language or 'unknown'}",
                "",
            ]
        )
        for turn in transcript.turns:
            body = turn.text.replace("\n", " ")
            lines.append(f"> {turn.role}: {body}")
        lines.extend(
            [
                "",
                "| criterion | human score (1-5) | judge score (1-5) |",
                "| --- | --- | --- |",
            ]
        )
        for criterion in criteria:
            score = judgement.score_for(criterion)
            judge_value = str(score.score) if score is not None else ""
            lines.append(f"| {criterion} |  | {judge_value} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_worksheet(path: Path) -> list[CalibrationRow]:
    """Read a worksheet (blank or filled) back into calibration rows."""
    text = path.read_text(encoding="utf-8")
    conversation_ids = [m.group(1) for m in _CONVERSATION_RE.finditer(text)]
    if not conversation_ids:
        raise ValueError(f"no '## Conversation <id>' sections in {path}")

    rows: list[CalibrationRow] = []
    boundaries = [
        (m.start(), m.end(), m.group(1)) for m in _CONVERSATION_RE.finditer(text)
    ]
    for i, (_, end, conversation_id) in enumerate(boundaries):
        section_end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        section = text[end:section_end]
        for match in _TABLE_ROW_RE.finditer(section):
            criterion = match.group(1).strip()
            if criterion not in _CRITERIA_ORDER:
                continue  # header and separator rows
            rows.append(
                CalibrationRow(
                    conversation_id=conversation_id,
                    criterion=criterion,
                    human_score=_score_cell(match.group(2)),
                    judge_score=_score_cell(match.group(3)),
                )
            )
    return rows


# ------------------------------------------------------------ agreement math


def agreement(rows: list[CalibrationRow]) -> AgreementResult:
    """Exact and within-1 agreement over the rows both parties scored.

    Exact: human score == judge score. Within 1: |human - judge| <= 1.
    Rows missing either score are excluded from both rates.
    """
    counted = [r for r in rows if r.human_score is not None and r.judge_score is not None]
    if not counted:
        return AgreementResult(n=0, exact_rate=0.0, within_1_rate=0.0, per_criterion=())

    per_criterion: list[CriterionAgreement] = []
    for criterion in _CRITERIA_ORDER:
        subset = [r for r in counted if r.criterion == criterion]
        if not subset:
            continue
        exact = sum(1 for r in subset if r.human_score == r.judge_score)
        within = sum(1 for r in subset if abs((r.human_score or 0) - (r.judge_score or 0)) <= 1)
        per_criterion.append(
            CriterionAgreement(
                criterion=criterion,
                n=len(subset),
                exact_rate=exact / len(subset),
                within_1_rate=within / len(subset),
            )
        )

    exact = sum(1 for r in counted if r.human_score == r.judge_score)
    within = sum(1 for r in counted if abs((r.human_score or 0) - (r.judge_score or 0)) <= 1)
    return AgreementResult(
        n=len(counted),
        exact_rate=exact / len(counted),
        within_1_rate=within / len(counted),
        per_criterion=tuple(per_criterion),
    )
