"""F03 T1: seeded funnel dataset and re-runnable funnel script.

Covers specs/01-discovery.md section 6 and the baseline table in
specs/00-client-brief.md section 4, with the tolerances stated in
odd/tasks/discovery-process-funnel.md T1: rates within 5 percentage points,
median elapsed days within 1.0 day.
"""

import random
import statistics
from datetime import timedelta
from pathlib import Path

from mocks.funnel import (
    baseline_metrics,
    funnel_counts,
    median_elapsed_days,
    stage_conversions,
)
from mocks.seed.generate import (
    DATA_CUT,
    RESTAURANT_COUNT,
    SEED,
    SEED_DIR,
    STAGES,
    build_applications,
    build_restaurants,
    write_seed_files,
)

SEED_FILES = ("restaurants.csv", "applications.csv")
WINDOW_DAYS = 180

RATE_TOLERANCE_PCT = 5.0
MEDIAN_TOLERANCE_DAYS = 1.0


def make_rows() -> list[dict]:
    restaurants = build_restaurants()
    return build_applications(random.Random(SEED), restaurants)


def elapsed_days(row: dict, from_stage: str, to_stage: str) -> float | None:
    start = row[f"{from_stage}_at"]
    end = row[f"{to_stage}_at"]
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Dataset shape
# ---------------------------------------------------------------------------


def test_dataset_has_15_restaurants_with_pilot_control_split() -> None:
    restaurants = build_restaurants()

    assert len(restaurants) == RESTAURANT_COUNT == 15
    pilots = [r for r in restaurants if r["is_pilot"]]
    controls = [r for r in restaurants if not r["is_pilot"]]
    assert len(pilots) == 12
    assert len(controls) == 3
    ids = {r["restaurant_id"] for r in restaurants}
    assert len(ids) == 15


def test_applications_cover_six_months_across_all_restaurants() -> None:
    rows = make_rows()

    assert len(rows) >= 3000
    restaurants = {r["restaurant_id"] for r in build_restaurants()}
    assert {row["restaurant_id"] for row in rows} == restaurants
    applied = [row["applied_at"] for row in rows]
    assert min(applied) >= DATA_CUT - timedelta(days=WINDOW_DAYS)
    assert max(applied) < DATA_CUT
    assert (max(applied) - min(applied)).days >= WINDOW_DAYS - 10


def test_committed_seed_files_match_fixed_seed(tmp_path: Path) -> None:
    regen = tmp_path / "regen"
    write_seed_files(regen)

    for name in SEED_FILES:
        assert (SEED_DIR / name).exists(), f"missing committed seed file {name}"
        assert (SEED_DIR / name).read_bytes() == (regen / name).read_bytes(), (
            f"committed {name} does not match regeneration with seed {SEED}"
        )


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_seed_files(first)
    write_seed_files(second)

    for name in SEED_FILES:
        assert (first / name).read_bytes() == (second / name).read_bytes()


# ---------------------------------------------------------------------------
# Funnel structure
# ---------------------------------------------------------------------------


def test_funnel_counts_are_non_increasing_across_all_stages() -> None:
    rows = make_rows()
    counts = funnel_counts(rows)

    assert list(counts) == list(STAGES)
    values = [counts[stage] for stage in STAGES]
    assert all(a >= b for a, b in zip(values, values[1:], strict=False)), counts
    assert counts["applied"] == len(rows)
    assert counts["day90_active"] > 0


def test_stage_timestamps_never_go_backwards() -> None:
    rows = make_rows()

    for row in rows:
        for before, after in zip(STAGES, STAGES[1:], strict=False):
            start = row[f"{before}_at"]
            end = row[f"{after}_at"]
            if start is not None and end is not None:
                assert end >= start, (row["application_id"], before, after)


def test_every_stage_conversion_is_a_fraction() -> None:
    rows = make_rows()
    counts = funnel_counts(rows)
    conversions = stage_conversions(counts)

    assert [stage for stage, _ in conversions] == list(STAGES[1:])
    for _, rate in conversions:
        assert 0.0 < rate <= 1.0


# ---------------------------------------------------------------------------
# Baseline metrics vs specs/00-client-brief.md section 4 (within T1 tolerance)
# ---------------------------------------------------------------------------


def test_baseline_metrics_reproduce_the_brief_within_tolerance() -> None:
    rows = make_rows()
    metrics = baseline_metrics(rows)

    assert abs(metrics["never_contacted_pct"] - 41.0) <= RATE_TOLERANCE_PCT
    assert (
        abs(metrics["median_days_to_first_contact"] - 3.8) <= MEDIAN_TOLERANCE_DAYS
    )
    assert abs(metrics["interview_no_show_pct"] - 38.0) <= RATE_TOLERANCE_PCT
    assert (
        abs(metrics["median_days_offer_to_first_shift"] - 9.0) <= MEDIAN_TOLERANCE_DAYS
    )
    assert abs(metrics["day1_no_show_pct"] - 18.0) <= RATE_TOLERANCE_PCT
    assert abs(metrics["attrition_90d_pct"] - 52.0) <= RATE_TOLERANCE_PCT


def test_median_elapsed_days_matches_direct_computation() -> None:
    rows = make_rows()

    expected = statistics.median(
        d
        for row in rows
        if (d := elapsed_days(row, "applied", "contacted")) is not None
    )
    assert median_elapsed_days(rows, "applied", "contacted") == expected


# ---------------------------------------------------------------------------
# CLI contract: uv run python -m mocks.funnel
# ---------------------------------------------------------------------------


def test_funnel_main_prints_counts_conversions_medians_and_baseline(
    capsys, monkeypatch
) -> None:
    from mocks import funnel

    monkeypatch.setattr(funnel, "SEED_DIR", SEED_DIR)
    funnel.main()
    out = capsys.readouterr().out

    for stage in STAGES:
        assert stage in out, f"stage {stage} missing from funnel output"
    assert "conversion" in out.lower()
    assert "median" in out.lower()
    assert "Never contacted" in out
    assert "Interview no-show" in out
    assert "Day-1 no-show" in out
    assert "90-day attrition" in out
    assert "Largest absolute loss" in out
    assert "Largest time sink" in out
