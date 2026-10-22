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

import argparse
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from evals.judge.port import ConversationTranscript, ConversationTurn, JudgePort, ScriptedJudge
from evals.judge.rubrics import Rubric, load_all_rubrics


def build_judge(mode: str = "scripted", **kwargs: object) -> JudgePort:
    """Lazy shim over evals.judge.live.build_judge (keeps the CI import path
    offline) and the seam tests patch to avoid any model client."""
    from evals.judge.live import build_judge as _build_judge

    return _build_judge(mode, **kwargs)  # type: ignore[arg-type]

CALIBRATION_CONVERSATIONS = 15
DEFAULT_REPORTS_DIR = Path("evals/reports")

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


# ------------------------------------------------- live fill of unscored rows


def _fill_unscored_rows(
    rows: list[CalibrationRow], *, worksheet_path: Path, report_path: Path | None
) -> list[CalibrationRow]:
    """Fill the judge column of unscored rows with the live judge (S4).

    Rows already carrying a judge score keep it (the scripted pre-fill stays
    intact). Rows whose conversation is missing from the report are left
    unscored with a note. The worksheet is rewritten in place when anything
    was filled, so reruns do not repay live calls for already-filled rows.
    """
    pending: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        if row.judge_score is None:
            pending.setdefault(row.conversation_id, []).append(i)
    if not pending:
        return rows  # nothing to do: never construct the live judge

    judge = build_judge("live")
    rubrics = list(load_all_rubrics())
    report_path = report_path or _latest_report(DEFAULT_REPORTS_DIR)
    transcripts = {t.conversation_id: t for t in _transcripts_from_report(report_path)}

    filled = list(rows)
    filled_count = 0
    for conversation_id, indexes in pending.items():
        transcript = transcripts.get(conversation_id)
        if transcript is None:
            print(
                f"note: conversation {conversation_id} is not in {report_path}; "
                "its unscored rows are left as-is"
            )
            continue
        judgement = judge.judge(transcript, rubrics)
        for i in indexes:
            score = judgement.score_for(rows[i].criterion)
            if score is None:
                raise ValueError(
                    f"live judge for {conversation_id} returned no score for "
                    f"criterion '{rows[i].criterion}'"
                )
            filled[i] = replace(rows[i], judge_score=score.score)
            filled_count += 1

    if filled_count:
        _rewrite_judge_column(worksheet_path, filled)
        print(
            f"filled {filled_count} unscored judge cell(s) with the live judge "
            f"({getattr(judge, 'model', 'live-judge')}); updated {worksheet_path}"
        )
    return filled


def _rewrite_judge_column(path: Path, rows: list[CalibrationRow]) -> None:
    """Write newly filled judge scores back into the worksheet, preserving the
    human column exactly."""
    by_key = {(r.conversation_id, r.criterion): r.judge_score for r in rows}
    text = path.read_text(encoding="utf-8")
    trailing_newline = text.endswith("\n")
    current_conversation: str | None = None
    out: list[str] = []
    for line in text.splitlines():
        section = _CONVERSATION_RE.match(line)
        if section:
            current_conversation = section.group(1)
            out.append(line)
            continue
        row = _TABLE_ROW_RE.match(line)
        criterion = row.group(1).strip() if row else ""
        if row and criterion in _CRITERIA_ORDER and current_conversation:
            score = by_key.get((current_conversation, criterion))
            if score is not None:
                out.append(f"| {criterion} | {row.group(2).strip()} | {score} |")
                continue
        out.append(line)
    path.write_text("\n".join(out) + ("\n" if trailing_newline else ""), encoding="utf-8")


# --------------------------------------------------------------- the CLI


def _latest_report(reports_dir: Path) -> Path:
    """The most recently written eval report JSON in the reports directory."""
    candidates = sorted(reports_dir.glob("eval-*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(
            f"no eval-*.json report in {reports_dir}: run `python -m evals.run` first"
        )
    return candidates[-1]


def _transcripts_from_report(report_path: Path) -> list[ConversationTranscript]:
    """The judged conversations of an eval report, as plain transcripts."""
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    transcripts: list[ConversationTranscript] = []
    for conversation in payload.get("conversations", []):
        transcripts.append(
            ConversationTranscript(
                conversation_id=str(conversation["conversation_id"]),
                turns=tuple(
                    ConversationTurn(role=str(turn["role"]), text=str(turn["text"]))
                    for turn in conversation.get("transcript", [])
                ),
                language=conversation.get("language"),
            )
        )
    if not transcripts:
        raise ValueError(f"report {report_path} carries no conversations with transcripts")
    return transcripts


def _agreement_markdown(result: AgreementResult) -> str:
    """The agreement report: exact and within-1 rates, overall and per criterion."""
    lines = [
        "# Judge calibration agreement",
        "",
        f"{result.n} scored cell(s); exact agreement {result.exact_rate:.0%}, "
        f"within-1 agreement {result.within_1_rate:.0%}.",
        "",
        "| criterion | n | exact | within 1 |",
        "| --- | --- | --- | --- |",
    ]
    for entry in result.per_criterion:
        lines.append(
            f"| {entry.criterion} | {entry.n} | {entry.exact_rate:.0%} | "
            f"{entry.within_1_rate:.0%} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """`python -m evals.judge.calibration emit|score` (S4).

    emit: write the 15-conversation labeling worksheet from the latest (or
    named) eval report; the judge column is pre-filled with the deterministic
    judge so agreement is computable the moment the human column is filled.
    score: read the filled worksheet back and report human-judge agreement.
    """
    parser = argparse.ArgumentParser(
        prog="python -m evals.judge.calibration",
        description="Judge calibration worksheet and agreement (S4).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit = subparsers.add_parser("emit", help="write the labeling worksheet")
    emit.add_argument("--report", type=Path, default=None,
                      help="eval report JSON (default: newest in evals/reports)")
    emit.add_argument("--out", type=Path, default=DEFAULT_REPORTS_DIR / "calibration-v1.md")
    emit.add_argument("--count", type=int, default=CALIBRATION_CONVERSATIONS,
                      help="conversations to include (spec: 15)")

    score = subparsers.add_parser("score", help="compute human-judge agreement")
    score.add_argument("--worksheet", type=Path, required=True)
    score.add_argument(
        "--judge",
        choices=("scripted", "live"),
        default="scripted",
        help="fill unscored judge cells with the live model judge before "
        "computing agreement (default: scripted pre-fill stays as-is)",
    )
    score.add_argument(
        "--report",
        type=Path,
        default=None,
        help="eval report JSON holding the transcripts (default: newest in "
        "evals/reports; only used when --judge live)",
    )
    score.add_argument("--out", type=Path, default=None,
                      help="write the agreement markdown here (default: stdout)")

    args = parser.parse_args(argv)
    if args.command == "emit":
        report_path = args.report or _latest_report(DEFAULT_REPORTS_DIR)
        transcripts = _transcripts_from_report(report_path)[: args.count]
        worksheet = emit_worksheet(
            transcripts, list(load_all_rubrics()), path=args.out
        )
        print(f"wrote worksheet for {len(transcripts)} conversation(s) to {worksheet}")
        if len(transcripts) < CALIBRATION_CONVERSATIONS:
            print(
                f"note: {len(transcripts)} of {CALIBRATION_CONVERSATIONS} calibration "
                "conversations available; run a bigger suite for the full worksheet"
            )
        return 0

    rows = load_worksheet(args.worksheet)
    if args.judge == "live":
        rows = _fill_unscored_rows(
            rows, worksheet_path=args.worksheet, report_path=args.report
        )
    result = agreement(rows)
    report_md = _agreement_markdown(result)
    if args.out is None:
        print(report_md, end="")
    else:
        args.out.write_text(report_md, encoding="utf-8")
        print(f"wrote agreement report to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
