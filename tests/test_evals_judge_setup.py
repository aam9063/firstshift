"""T2/T4 setup surfaces: the evals packages import cleanly and stay offline.

The judge must never contact a model from tests or CI (specs/05 section 2 and
the eval-harness constraint "No network in tests except the judge behind a
port with a scripted/cached implementation"): this file pins that guarantee
structurally.
"""

import ast
from pathlib import Path

import evals.checks.deterministic  # noqa: F401
import evals.judge.calibration  # noqa: F401
import evals.judge.port  # noqa: F401
import evals.judge.rubrics  # noqa: F401

JUDGE_DIR = Path(evals.judge.port.__file__).parent


def test_judge_modules_never_import_a_model_client() -> None:
    forbidden = {"openai", "strands", "strands_agents", "httpx", "requests"}
    for module_file in JUDGE_DIR.glob("*.py"):
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert node.names[0].name.split(".")[0] not in forbidden, module_file.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".")[0] not in forbidden, module_file.name


def test_checks_module_has_no_i_o_dependencies() -> None:
    """The deterministic checks are pure assertions over passed-in rows: they
    import the persisted shapes and the allow-list table, nothing else."""
    source = Path(evals.checks.deterministic.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            assert (node.module or "").split(".")[0] in {
                "app", "evals", "dataclasses", "typing", "re", "__future__",
                "collections",
            }, node.module


def test_calibration_and_checks_define_their_public_surface() -> None:
    from evals.checks.deterministic import CHECK_NAMES, CheckResult, run_deterministic_checks
    from evals.judge.calibration import CalibrationRow, agreement, emit_worksheet, load_worksheet
    from evals.judge.port import Judgement, JudgePort, ScriptedJudge

    result = CheckResult(name="probe", passed=True, evidence="ok")
    assert (result.name, result.passed, result.evidence) == ("probe", True, "ok")
    assert callable(run_deterministic_checks)
    assert callable(emit_worksheet)
    assert callable(load_worksheet)
    assert callable(agreement)
    assert callable(ScriptedJudge().judge)
    assert len(CHECK_NAMES) == 6
    assert Judgement is not None and JudgePort is not None and CalibrationRow is not None
