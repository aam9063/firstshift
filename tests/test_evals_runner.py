"""T5 (S6): the eval runner CLI, artifacts and suite selection.

Spec source: specs/05-iteration-evals.md section 3, verbatim: "uv run python
-m evals.run --suite full --seed 42 --label vN produces evals/reports/eval-vN.md
with: summary table vs previous version, failing deterministic checks (must be
zero), worst 5 conversations by judge score with links, fairness table, cost
per hire, and a 'what changed' section filled from the iteration log." Plus a
fast suite (10 personas, under 3 minutes).

The DB-backed tests run a two-persona suite through the real sim runner with
the scripted model over a throwaway Postgres schema; the pure selection and
failure tests need no database.
"""

import json
from pathlib import Path

import pytest

from evals.personas.generate import generate_personas
from evals.run import run_suite, select_personas

REQUIRED_SECTIONS = (
    "# Eval report eval-",
    "## Summary",
    "## Deterministic checks",
    "0 failing",
    "## Worst 5 conversations",
    "## Task success",
    "## Fairness",
    "## Funnel",
    "## Cost per hire",
    "## What changed",
)


# ------------------------------------------------------------ suite selection


def test_fast_suite_selects_ten_personas_and_full_selects_all() -> None:
    personas = generate_personas(seed=42, count=44)
    assert len(select_personas("fast", personas)) == 10
    assert len(select_personas("full", personas)) == 44


def test_fast_suite_selection_is_a_stable_prefix_of_the_seeded_bundle() -> None:
    personas = generate_personas(seed=42, count=44)
    fast = select_personas("fast", personas)
    assert [p.persona_id for p in fast] == [p.persona_id for p in personas[:10]]


def test_unknown_suite_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="suite"):
        select_personas("smoke", generate_personas(seed=42, count=12))


# ------------------------------------------------- artifacts over the real runner


@pytest.fixture()
def sim_engine():
    from tests.test_sim_common import fresh_sim_engine

    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        yield engine
    finally:
        generator.close()


TWO_PERSONAS = generate_personas(seed=42, count=44)[:2]


def test_run_suite_writes_json_and_markdown_with_all_required_sections(
    sim_engine, tmp_path: Path
) -> None:
    run_suite(
        suite="fast",
        seed=42,
        label="t1",
        out_dir=tmp_path,
        personas=TWO_PERSONAS,
        engine=sim_engine,
    )
    json_path = tmp_path / "eval-t1.json"
    md_path = tmp_path / "eval-t1.md"
    assert json_path.is_file() and md_path.is_file(), sorted(p.name for p in tmp_path.iterdir())

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["meta"]["suite"] == "fast"
    assert payload["meta"]["seed"] == 42
    assert payload["meta"]["label"] == "t1"
    assert payload["meta"]["persona_count"] == 2
    assert len(payload["conversations"]) == 2
    assert payload["deterministic_checks"]["failing"] == 0
    assert payload["fairness"], "fairness rows must be in the JSON"
    assert "cost_per_hired_usd" in payload["cost"]
    # Transcripts are stored so the calibration worksheet can be emitted.
    assert all(c["transcript"] for c in payload["conversations"])

    markdown = md_path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in markdown, f"missing report section: {section}"


def test_run_suite_summary_compares_against_the_previous_version(
    sim_engine, tmp_path: Path
) -> None:
    run_suite(
        suite="fast", seed=42, label="t1", out_dir=tmp_path,
        personas=TWO_PERSONAS, engine=sim_engine,
    )
    result = run_suite(
        suite="fast", seed=42, label="t2", out_dir=tmp_path,
        personas=TWO_PERSONAS, engine=sim_engine,
    )
    markdown = (tmp_path / "eval-t2.md").read_text(encoding="utf-8")
    assert "eval-t1" in markdown, "previous version must be referenced in the summary"
    assert result["comparison"]["previous_label"] == "t1"


def test_run_suite_what_changed_reads_the_iteration_log(
    sim_engine, tmp_path: Path
) -> None:
    log = tmp_path / "iteration-log.md"
    log.write_text(
        "# Iteration log\n\n## v1: shorter first message\n\nWe believe changing "
        "the first message will improve reply rate from 0.5 to 0.8.\n",
        encoding="utf-8",
    )
    result = run_suite(
        suite="fast", seed=42, label="t1", out_dir=tmp_path,
        personas=TWO_PERSONAS, engine=sim_engine, iteration_log=log,
    )
    assert "shorter first message" in result["what_changed"]
    assert "0.8" in result["what_changed"]


def test_run_suite_what_changed_notes_a_missing_log(
    sim_engine, tmp_path: Path
) -> None:
    result = run_suite(
        suite="fast", seed=42, label="t1", out_dir=tmp_path,
        personas=TWO_PERSONAS, engine=sim_engine,
        iteration_log=tmp_path / "missing.md",
    )
    assert "no iteration log" in result["what_changed"]


# --------------------------------------- deterministic checks gate the suite


def test_deterministic_check_failure_stops_the_suite(
    sim_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evals.checks.deterministic import CheckResult

    def failing_checks(record):
        return [CheckResult("state_machine_invariants", False, "boom: illegal transition")]

    monkeypatch.setattr("evals.run.run_deterministic_checks", failing_checks)
    with pytest.raises(SystemExit) as excinfo:
        run_suite(
            suite="fast", seed=42, label="tfail", out_dir=tmp_path,
            personas=TWO_PERSONAS, engine=sim_engine,
        )
    assert excinfo.value.code == 2
    assert not (tmp_path / "eval-tfail.json").exists()
    assert not (tmp_path / "eval-tfail.md").exists()


# ------------------------------------------------- judge scores in the report


def test_run_suite_judges_conversations_and_reports_the_worst_five(
    sim_engine, tmp_path: Path
) -> None:
    result = run_suite(
        suite="fast", seed=42, label="t1", out_dir=tmp_path,
        personas=TWO_PERSONAS, engine=sim_engine,
    )
    judged = [c for c in result["conversations"] if c["judge_mean"] is not None]
    assert len(judged) == 2
    for conversation in judged:
        assert 1.0 <= conversation["judge_mean"] <= 5.0
    markdown = (tmp_path / "eval-t1.md").read_text(encoding="utf-8")
    for conversation in judged:
        assert conversation["trace_id"] in markdown, (
            "worst-5 table must carry the trace link"
        )


# ------------------------------------------------------- calibration CLI (T4)


def _fake_report(tmp_path: Path) -> Path:
    report = {
        "meta": {"label": "t1"},
        "conversations": [
            {
                "conversation_id": f"trc-{i}",
                "language": "es",
                "transcript": [
                    {"role": "agent", "text": "Hola, soy la asistente de Lumbre Burger."},
                    {"role": "candidate", "text": "Hola, quiero info del turno."},
                ],
            }
            for i in range(3)
        ],
    }
    path = tmp_path / "eval-t1.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_calibration_cli_emits_a_worksheet_from_an_eval_report(tmp_path: Path) -> None:
    from evals.judge.calibration import load_worksheet, main

    report = _fake_report(tmp_path)
    out = tmp_path / "calibration-v1.md"
    code = main(["emit", "--report", str(report), "--out", str(out)])
    assert code == 0
    rows = load_worksheet(out)
    assert {row.conversation_id for row in rows} == {"trc-0", "trc-1", "trc-2"}
    assert all(row.judge_score is not None for row in rows)
    assert all(row.human_score is None for row in rows)


def test_calibration_cli_scores_agreement_on_a_filled_worksheet(tmp_path: Path) -> None:
    from evals.judge.calibration import main

    report = _fake_report(tmp_path)
    out = tmp_path / "calibration-v1.md"
    assert main(["emit", "--report", str(report), "--out", str(out)]) == 0

    text = out.read_text(encoding="utf-8")
    # Fill every human cell with the pre-filled judge score: agreement 1.0.
    # Emitted rows look like "| clarity |  | 3 |"; only the human cell is blank.
    assert " |  | " in text
    out.write_text(text.replace(" |  | ", " | 3 | "), encoding="utf-8")

    score_out = tmp_path / "agreement.md"
    code = main(["score", "--worksheet", str(out), "--out", str(score_out)])
    assert code == 0
    agreement_md = score_out.read_text(encoding="utf-8")
    assert "100" in agreement_md, f"perfect agreement expected: {agreement_md}"
