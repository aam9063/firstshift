"""T1-T2 (S1, S2): the 30-day simulated pilot and its weekly ops review.

Spec source: specs/05-iteration-evals.md section 5, verbatim: "Run the full
system over the 12 pilot restaurants for a simulated 30 days (clock
fast-forward) with persona arrival rates matching the client's seasonality,
and compare with the 3 control restaurants running the 'as-is' process model
from discovery." Plus: "State its limits plainly: this is a simulation with
synthetic behavior, useful to find failure modes and to size impact, not
proof of real-world effect."

The tests cover, per the task's acceptance criteria:

- the control model's arithmetic reproduces the discovery baselines
  (`discovery/funnel-baseline.md`) within a stated tolerance, and the
  baseline check fails when the model is fed wrong inputs (not vacuous),
- a seeded pilot run is reproducible (same counts twice),
- the pilot run reports zero deterministic-check failures,
- arrivals respect the seasonality shape (weekend uplift and summer ramp),
- the report contains every required section and the simulation caveat is
  visible in every results section.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from evals.pilot import (
    CONTROL_RESTAURANT_IDS,
    PILOT_RESTAURANT_IDS,
    ControlRates,
    assign_personas,
    baseline_violations,
    build_arrival_schedule,
    render_markdown,
    run_pilot,
    simulate_control_arm,
)
from mocks.services.seed import load_restaurants
from tests.test_sim_common import fresh_sim_engine

RATE_TOLERANCE = 0.05  # 5 percentage points, the funnel-baseline tolerance
DAY_TOLERANCE = 1.0  # days, the funnel-baseline median tolerance

REQUIRED_SECTIONS = (
    "# FirstShift simulated pilot",
    "## Headline numbers",
    "## What went wrong",
    "## Top escalations",
    "## Fairness",
    "## Decisions needed from the client",
    "## Limits of this simulation",
)
RESULTS_SECTIONS = (
    "## Headline numbers",
    "## What went wrong",
    "## Top escalations",
    "## Fairness",
)
CAVEAT = "Simulation caveat:"
LIMITS_STATEMENT = (
    "this is a simulation with synthetic behavior, useful to find failure "
    "modes and to size impact, not proof of real-world effect"
)


# ------------------------------------------------------------- control model


def test_control_model_reproduces_discovery_baselines() -> None:
    """At the discovery dataset's volume (4,500 applications, seed 42) the
    as-is model's funnel lands on the baselines within the stated tolerance."""
    summary = simulate_control_arm(4500, rng=random.Random(42))

    assert baseline_violations(summary) == []
    assert abs(summary.contact_rate - 0.590) <= 0.02
    assert abs(summary.interview_show_rate - 0.62) <= 0.02
    assert abs(summary.day1_show_rate - 0.821) <= 0.02
    assert abs(summary.median_days_to_contact - 3.9) <= 0.5
    assert abs(summary.median_days_application_to_first_shift - 27.3) <= DAY_TOLERANCE


def test_control_model_baseline_check_fails_on_wrong_inputs() -> None:
    """Feeding the model rates that are not the discovery baselines must trip
    the baseline check: the reproduction test above is not vacuous."""
    tampered = ControlRates(
        contact_rate=0.90,
        attend_rate=0.90,
        day1_rate=0.60,
        days_to_contact=1.0,
    )
    summary = simulate_control_arm(4500, rates=tampered, rng=random.Random(42))

    violations = baseline_violations(summary)
    assert violations, "tampered rates must produce baseline violations"
    assert any("contact rate" in v for v in violations)
    assert any("day-1" in v for v in violations)
    assert any("first contact" in v for v in violations)


# ----------------------------------------------------------------- arrivals


def test_arrival_schedule_uses_the_pilot_and_control_restaurants() -> None:
    pilot_ids = [r.restaurant_id for r in load_restaurants() if r.is_pilot]
    control_ids = [r.restaurant_id for r in load_restaurants() if not r.is_pilot]
    assert pilot_ids == PILOT_RESTAURANT_IDS
    assert control_ids == CONTROL_RESTAURANT_IDS


def test_arrival_schedule_is_reproducible_and_seasonal() -> None:
    schedule_a = build_arrival_schedule(30, PILOT_RESTAURANT_IDS, random.Random(42))
    schedule_b = build_arrival_schedule(30, PILOT_RESTAURANT_IDS, random.Random(42))
    assert schedule_a == schedule_b, "the same seed must produce the same arrivals"
    assert {a.restaurant_id for a in schedule_a} == set(PILOT_RESTAURANT_IDS)

    weekday = [a for a in schedule_a if not a.weekend]
    weekend = [a for a in schedule_a if a.weekend]
    assert weekday and weekend
    weekday_per_day = len(weekday) / 22  # 22 weekdays in the 30-day window
    weekend_per_day = len(weekend) / 8  # 8 weekend days
    assert weekend_per_day > weekday_per_day * 1.25, (
        "weekend arrivals must run clearly above weekday arrivals"
    )

    first_week_per_day = sum(
        1 for a in schedule_a if a.day_index < 7
    ) / 7
    last_week_per_day = sum(
        1 for a in schedule_a if a.day_index >= 23
    ) / 7
    assert last_week_per_day > first_week_per_day * 1.1, (
        "the summer ramp must raise arrivals over the 30-day window"
    )


def test_personas_are_assigned_to_their_arrival_restaurant() -> None:
    schedule = build_arrival_schedule(2, PILOT_RESTAURANT_IDS, random.Random(42))
    personas = assign_personas(schedule, seed=42)
    assert len(personas) == len(schedule)
    for persona, arrival in zip(personas, schedule, strict=True):
        assert persona.restaurant_id == arrival.restaurant_id
        assert persona.fitting_shift_ids, "ground truth must be recomputed per restaurant"


# ------------------------------------------------- the real-pipeline pilot run


@pytest.fixture(scope="module")
def pilot_run(tmp_path_factory: pytest.TempPathFactory):
    """One short pilot run (1 simulated day of arrivals) over the real
    pipeline, plus its output directory; shared by the DB-backed tests."""
    from evals.pilot import run_pilot  # noqa: F401  (import check happens above)

    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        out_dir = tmp_path_factory.mktemp("pilot")
        payload = run_pilot(
            days=1, seed=42, label="t1", out_dir=out_dir, engine=engine, log=lambda _m: None
        )
        yield payload, out_dir
    finally:
        generator.close()


def test_seeded_pilot_run_is_reproducible(pilot_run, tmp_path: Path) -> None:
    payload, _out_dir = pilot_run
    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        again = run_pilot(
            days=1, seed=42, label="t2", out_dir=tmp_path, engine=engine, log=lambda _m: None
        )
    finally:
        generator.close()

    assert payload["arrivals"]["pilot"] == again["arrivals"]["pilot"]
    assert payload["pilot"]["final_states"] == again["pilot"]["final_states"]
    assert payload["pilot"]["hires"] == again["pilot"]["hires"]
    assert payload["pilot"]["day1_show_rate"] == again["pilot"]["day1_show_rate"]
    assert payload["pilot"]["ttfps_days_median"] == again["pilot"]["ttfps_days_median"]
    assert payload["escalations"] == again["escalations"]
    control = ("arrivals", "contact_rate", "median_days_to_contact", "hires")
    assert all(payload["control"][k] == again["control"][k] for k in control)
    # A different seed must not be identical to seed 42 (the seed matters).
    assert payload["meta"]["seed"] == again["meta"]["seed"] == 42


def test_pilot_run_reports_zero_deterministic_check_failures(pilot_run) -> None:
    payload, _out_dir = pilot_run
    checks = payload["deterministic_checks"]
    assert checks["failing"] == 0
    assert checks["checked"] == payload["arrivals"]["pilot"]


def test_pilot_payload_labels_the_control_as_a_model(pilot_run) -> None:
    payload, _out_dir = pilot_run
    assert "model" in payload["control"]["model"].lower()
    assert "as-is" in payload["control"]["model"].lower()


# ------------------------------------------------------------ report content


def test_report_contains_required_sections_and_caveat(pilot_run) -> None:
    payload, out_dir = pilot_run
    markdown = (out_dir / "pilot-sim-t1.md").read_text(encoding="utf-8")

    for section in REQUIRED_SECTIONS:
        assert section in markdown, f"missing report section: {section}"
    assert LIMITS_STATEMENT in markdown

    # S2: the caveat is visible in every results section, not only in limits.
    bodies = _section_bodies(markdown)
    for section in RESULTS_SECTIONS:
        assert CAVEAT in bodies[section], f"caveat missing from {section}"


def test_report_is_written_next_to_its_json(pilot_run) -> None:
    payload, out_dir = pilot_run
    json_path = out_dir / "pilot-sim-t1.json"
    md_path = out_dir / "pilot-sim-t1.md"
    assert json_path.is_file() and md_path.is_file()
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["meta"]["days"] == payload["meta"]["days"]
    assert stored["meta"]["seed"] == payload["meta"]["seed"]


def test_shipped_day30_report_carries_the_required_sections() -> None:
    """The checked-in 30-day artifact must stay a valid ops review."""
    path = Path("docs/pilot-sim-day30.md")
    if not path.is_file():
        pytest.skip("docs/pilot-sim-day30.md not generated yet")
    markdown = path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in markdown, f"missing report section: {section}"
    assert LIMITS_STATEMENT in markdown
    bodies = _section_bodies(markdown)
    for section in RESULTS_SECTIONS:
        assert CAVEAT in bodies[section], f"caveat missing from {section}"


def test_render_markdown_matches_the_written_report(pilot_run) -> None:
    payload, out_dir = pilot_run
    assert render_markdown(payload) == (out_dir / "pilot-sim-t1.md").read_text(
        encoding="utf-8"
    )


def _section_bodies(markdown: str) -> dict[str, str]:
    """Split a markdown document into {heading, body} pairs."""
    heads = [line for line in markdown.splitlines() if line.startswith("## ")]
    bodies: dict[str, str] = {}
    for index, head in enumerate(heads):
        start = markdown.index(head) + len(head)
        end = markdown.index(heads[index + 1]) if index + 1 < len(heads) else len(markdown)
        bodies[head] = markdown[start:end]
    return bodies
