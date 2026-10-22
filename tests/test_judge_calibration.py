"""T4 first half (S4): calibration worksheet and human-judge agreement.

Spec source: specs/05-iteration-evals.md section 2, row 3: "calibrate the
judge on 15 hand-labeled conversations first and report agreement". The
worksheet is emitted with 15 conversations, blank human score fields and a
deterministic judge column; the agreement math reports exact and within-1
rates once the worksheet is filled.
"""

import json

from evals.judge.calibration import (
    CALIBRATION_CONVERSATIONS,
    agreement,
    emit_worksheet,
    load_worksheet,
)
from evals.judge.port import ConversationTranscript, ConversationTurn
from evals.judge.rubrics import load_all_rubrics

CRITERIA = ("clarity", "warmth", "brevity", "language", "honesty")


def sample_transcripts(n: int = CALIBRATION_CONVERSATIONS):
    return [
        ConversationTranscript(
            conversation_id=f"cal-{i:02d}",
            language="es",
            turns=(
                ConversationTurn(role="agent", text="Hola: soy una IA de Lumbre Burger."),
                ConversationTurn(role="candidate", text="Si, quiero info."),
                ConversationTurn(role="agent", text="Te cuento los turnos de la semana."),
            ),
        )
        for i in range(1, n + 1)
    ]


# ------------------------------------------------------------- the worksheet


def test_worksheet_covers_15_conversations_with_blank_human_scores(tmp_path) -> None:
    rubrics = load_all_rubrics()
    path = emit_worksheet(sample_transcripts(), rubrics, path=tmp_path / "worksheet.md")
    rows = load_worksheet(path)
    conversation_ids = {row.conversation_id for row in rows}
    assert len(conversation_ids) == CALIBRATION_CONVERSATIONS
    assert {row.criterion for row in rows} == set(CRITERIA)
    assert len(rows) == CALIBRATION_CONVERSATIONS * len(CRITERIA)
    assert all(row.human_score is None for row in rows), "human fields must start blank"
    # The judge column is pre-filled so the runner can compute agreement later.
    assert all(row.judge_score is not None for row in rows)


def test_worksheet_includes_the_transcript_text(tmp_path) -> None:
    rubrics = load_all_rubrics()
    path = emit_worksheet(sample_transcripts(3), rubrics, path=tmp_path / "worksheet.md")
    text = path.read_text(encoding="utf-8")
    assert "soy una IA de Lumbre Burger" in text
    assert "cal-01" in text and "cal-03" in text


def test_filled_worksheet_roundtrips_human_scores(tmp_path) -> None:
    rubrics = load_all_rubrics()
    path = emit_worksheet(sample_transcripts(2), rubrics, path=tmp_path / "worksheet.md")
    rows = load_worksheet(path)
    filled = [row.human_score if row.criterion != "clarity" else 4 for row in rows]
    written = path.read_text(encoding="utf-8")
    # Simulate a human filling exactly the clarity cells, then reload.
    assert filled.count(4) == 2
    assert "| clarity |" in written
    for row in rows:
        if row.criterion == "clarity":
            written = written.replace(
                f"| clarity |  | {row.judge_score} |",
                f"| clarity | 4 | {row.judge_score} |",
            )
    path.write_text(written, encoding="utf-8")
    reloaded = load_worksheet(path)
    clarity = [r for r in reloaded if r.criterion == "clarity"]
    assert all(r.human_score == 4 for r in clarity)


# ----------------------------------------------------------- agreement math


def test_agreement_computes_exact_and_within_1_rates() -> None:
    from evals.judge.calibration import CalibrationRow

    rows = [
        CalibrationRow("c1", "clarity", 4, 4),  # exact
        CalibrationRow("c2", "clarity", 3, 4),  # within 1 only
        CalibrationRow("c3", "clarity", 1, 5),  # miss on both counts
    ]
    result = agreement(rows)
    assert result.n == 3
    assert result.exact_rate == 1 / 3
    assert result.within_1_rate == 2 / 3


def test_agreement_within_1_boundary_is_inclusive() -> None:
    from evals.judge.calibration import CalibrationRow

    rows = [
        CalibrationRow("c1", "clarity", 2, 3),
        CalibrationRow("c2", "clarity", 3, 2),
        CalibrationRow("c3", "clarity", 2, 4),
    ]
    result = agreement(rows)
    assert result.exact_rate == 0.0
    assert abs(result.within_1_rate - 2 / 3) < 1e-9


def test_agreement_excludes_unlabeled_rows_and_reports_per_criterion() -> None:
    from evals.judge.calibration import CalibrationRow

    rows = [
        CalibrationRow("c1", "clarity", 4, 4),
        CalibrationRow("c1", "warmth", None, 3),  # not yet labeled: excluded
        CalibrationRow("c2", "clarity", 4, 3),
        CalibrationRow("c2", "warmth", 5, 3),
    ]
    result = agreement(rows)
    assert result.n == 3
    per = {c.criterion: c for c in result.per_criterion}
    assert set(per) == {"clarity", "warmth"}
    assert per["clarity"].n == 2 and per["clarity"].exact_rate == 0.5
    assert per["warmth"].n == 1 and per["warmth"].exact_rate == 0.0


def test_agreement_of_a_fully_labeled_scripted_run_is_deterministic(tmp_path) -> None:
    rubrics = load_all_rubrics()
    transcripts = sample_transcripts(15)
    worksheet = emit_worksheet(transcripts, rubrics, path=tmp_path / "worksheet.md")
    rows = load_worksheet(worksheet)
    # Fill every human field with the scripted judge's own scores: agreement
    # must be exactly 1.0 on both rates.
    filled = []
    for row in rows:
        filled.append(
            type(row)(row.conversation_id, row.criterion, row.judge_score, row.judge_score)
        )
    result = agreement(filled)
    assert result.n == CALIBRATION_CONVERSATIONS * len(CRITERIA)
    assert result.exact_rate == 1.0
    assert result.within_1_rate == 1.0


def test_worksheet_roundtrip_is_json_stable_for_two_emits(tmp_path) -> None:
    rubrics = load_all_rubrics()
    transcripts = sample_transcripts(3)
    rows_a = load_worksheet(emit_worksheet(transcripts, rubrics, path=tmp_path / "a.md"))
    rows_b = load_worksheet(emit_worksheet(transcripts, rubrics, path=tmp_path / "b.md"))
    assert json.dumps([r.__dict__ for r in rows_a], sort_keys=True) == json.dumps(
        [r.__dict__ for r in rows_b], sort_keys=True
    )
