"""Hiring funnel baseline from the seeded mock dataset.

Re-runnable report for specs/01-discovery.md section 6:

    uv run python -m mocks.funnel

Prints per-stage counts, conversion per stage, median elapsed days between
consecutive stages, the brief's baseline metrics, and the largest absolute
loss of candidates and the largest time sink.
"""

from __future__ import annotations

import csv
import statistics
from datetime import datetime
from pathlib import Path

from mocks.seed.generate import STAGES

SEED_DIR = Path(__file__).resolve().parent / "seed"

STAGE_LABELS: dict[str, str] = {
    "applied": "Applied",
    "contacted": "Contacted",
    "screened": "Screened",
    "interview_scheduled": "Interview scheduled",
    "interview_attended": "Interview attended",
    "offer": "Offer",
    "documents_complete": "Documents complete",
    "on_rota": "On rota",
    "day1_worked": "Day 1 worked",
    "day30_active": "Day 30 active",
    "day90_active": "Day 90 active",
}


def load_applications(seed_dir: Path = SEED_DIR) -> list[dict]:
    """Load applications.csv into rows with datetime or None per stage."""

    path = seed_dir / "applications.csv"
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row: dict = {
                "application_id": raw["application_id"],
                "restaurant_id": raw["restaurant_id"],
                "is_pilot": raw["is_pilot"] == "true",
            }
            for stage in STAGES:
                value = raw[f"{stage}_at"]
                row[f"{stage}_at"] = (
                    datetime.fromisoformat(value) if value else None
                )
            rows.append(row)
    return rows


def funnel_counts(rows: list[dict]) -> dict[str, int]:
    """Count of applications that reached each stage."""

    return {
        stage: sum(1 for row in rows if row[f"{stage}_at"] is not None)
        for stage in STAGES
    }


def stage_conversions(counts: dict[str, int]) -> list[tuple[str, float]]:
    """Conversion rate into each stage relative to the previous stage."""

    conversions: list[tuple[str, float]] = []
    previous = STAGES[0]
    for stage in STAGES[1:]:
        base = counts[previous]
        rate = counts[stage] / base if base else 0.0
        conversions.append((stage, rate))
        previous = stage
    return conversions


def median_elapsed_days(rows: list[dict], from_stage: str, to_stage: str) -> float:
    """Median elapsed days between two stages, over rows that have both."""

    deltas = [
        (row[f"{to_stage}_at"] - row[f"{from_stage}_at"]).total_seconds() / 86400.0
        for row in rows
        if row[f"{from_stage}_at"] is not None and row[f"{to_stage}_at"] is not None
    ]
    return statistics.median(deltas)


def baseline_metrics(rows: list[dict]) -> dict[str, float]:
    """The brief's baseline metrics computed from the dataset."""

    counts = funnel_counts(rows)
    applied = counts["applied"]
    scheduled = counts["interview_scheduled"]
    on_rota = counts["on_rota"]
    day1 = counts["day1_worked"]
    day90 = counts["day90_active"]

    return {
        "never_contacted_pct": 100.0 * (applied - counts["contacted"]) / applied,
        "median_days_to_first_contact": median_elapsed_days(
            rows, "applied", "contacted"
        ),
        "interview_no_show_pct": 100.0 * (scheduled - counts["interview_attended"])
        / scheduled,
        "median_days_offer_to_first_shift": median_elapsed_days(
            rows, "offer", "day1_worked"
        ),
        "day1_no_show_pct": 100.0 * (on_rota - day1) / on_rota,
        "attrition_90d_pct": 100.0 * (day1 - day90) / day1,
    }


def main() -> None:
    rows = load_applications()
    counts = funnel_counts(rows)
    conversions = dict(stage_conversions(counts))
    metrics = baseline_metrics(rows)

    print("Hiring funnel baseline (mock dataset, seeded, last 6 months)")
    print(f"Applications: {len(rows)} across {len({r['restaurant_id'] for r in rows})} restaurants")
    print()
    header = (
        f"{'Stage':<22}{'Count':>7}{'Conversion':>12}{'Median days':>13}"
    )
    print(header)
    print("-" * len(header))
    print(f"{STAGES[0]:<22}{counts['applied']:>7}{'-':>12}{'-':>13}")
    for stage in STAGES[1:]:
        if stage in ("day30_active", "day90_active"):
            median_display = "n/a"
        else:
            previous_stage = STAGES[STAGES.index(stage) - 1]
            median_days = median_elapsed_days(rows, previous_stage, stage)
            median_display = f"{median_days:.1f}"
        print(
            f"{stage:<22}{counts[stage]:>7}"
            f"{conversions[stage] * 100:>11.1f}%{median_display:>13}"
        )

    print()
    print("Baseline metrics (specs/00-client-brief.md section 4)")
    print(f"  Never contacted: {metrics['never_contacted_pct']:.1f}% (baseline 41%)")
    print(
        f"  Median days to first contact: "
        f"{metrics['median_days_to_first_contact']:.1f} (baseline 3.8)"
    )
    print(
        f"  Interview no-show: {metrics['interview_no_show_pct']:.1f}% (baseline 38%)"
    )
    print(
        f"  Median days offer to first worked shift: "
        f"{metrics['median_days_offer_to_first_shift']:.1f} (baseline 9)"
    )
    print(f"  Day-1 no-show: {metrics['day1_no_show_pct']:.1f}% (baseline 18%)")
    print(f"  90-day attrition: {metrics['attrition_90d_pct']:.1f}% (baseline 52%)")

    losses = [
        (STAGE_LABELS[stage], counts[STAGES[i]] - counts[stage])
        for i, stage in enumerate(STAGES[1:])
    ]
    largest_loss_stage, largest_loss = max(losses, key=lambda pair: pair[1])
    print()
    print(f"Largest absolute loss of candidates: {largest_loss_stage} (-{largest_loss})")

    sinks = [
        (STAGE_LABELS[stage], median_elapsed_days(rows, STAGES[i], stage))
        for i, stage in enumerate(STAGES[1:8])
    ]
    largest_sink_stage, largest_sink = max(sinks, key=lambda pair: pair[1])
    print(
        f"Largest time sink: {largest_sink_stage} "
        f"(median {largest_sink:.1f} days between stages)"
    )


if __name__ == "__main__":
    main()
