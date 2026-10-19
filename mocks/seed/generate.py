"""Seeded dataset for the hiring funnel baseline (specs/01-discovery.md section 6).

Generates the mock application history for the 15 pilot and control restaurants
over the last 6 months, consistent with the baseline table in
specs/00-client-brief.md section 4. Re-run with:

    uv run python -m mocks.seed.generate

Determinism: the same SEED produces byte-identical CSVs. Stage passage is
assigned with exact counts (shuffle-and-select, not per-record coin flips) so
the realized conversion rates match the target rates up to integer rounding;
the random generator only breaks ties (which records pass) and draws elapsed
times. Elapsed times are lognormal with the target median, so each stage
median lands on its baseline value.

Stated decision: the dataset models full maturation (every application runs
the whole funnel) so the baseline rates stay stable across the window. For the
most recent applications the later stage timestamps can therefore extend past
the 6-month application window; a real extract would censor those.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
RESTAURANT_COUNT = 15
PILOT_COUNT = 12
DATA_CUT = datetime(2025, 6, 30)
WINDOW_DAYS = 180
APPLICATIONS_PER_RESTAURANT = 300

SEED_DIR = Path(__file__).resolve().parent

STAGES = (
    "applied",
    "contacted",
    "screened",
    "interview_scheduled",
    "interview_attended",
    "offer",
    "documents_complete",
    "on_rota",
    "day1_worked",
    "day30_active",
    "day90_active",
)

# Conditional pass rate per stage and median elapsed days from the previous
# stage. Targets come from specs/00-client-brief.md section 4: never contacted
# 41% (contact rate 0.59), interview no-show 38% (attendance 0.62), day-1
# no-show 18% (day-1 work rate 0.82), 90-day attrition 52% (0.72 * 0.6667 of
# day-1 workers are active at day 90), median offer to first worked shift 9
# days (2.5 + 5.0 + 1.5), median application to first contact 3.8 days.
STAGE_RATES: dict[str, float] = {
    "contacted": 0.59,
    "screened": 0.75,
    "interview_scheduled": 0.70,
    "interview_attended": 0.62,
    "offer": 0.60,
    "documents_complete": 0.85,
    "on_rota": 0.90,
    "day1_worked": 0.82,
    "day30_active": 0.72,
    "day90_active": 2.0 / 3.0,
}

STAGE_MEDIAN_DAYS: dict[str, float] = {
    "contacted": 3.8,
    "screened": 2.0,
    "interview_scheduled": 4.0,
    "interview_attended": 5.0,
    "offer": 3.0,
    "documents_complete": 2.5,
    "on_rota": 5.0,
    "day1_worked": 1.5,
}

# Fixed offsets in days from the first worked shift.
DAY30_OFFSET_DAYS = 29.0
DAY90_OFFSET_DAYS = 89.0

RESTAURANTS: tuple[tuple[str, str, bool], ...] = (
    ("R001", "Lumbre Burger Sol", "Madrid", True),
    ("R002", "Lumbre Burger Malasana", "Madrid", True),
    ("R003", "Lumbre Burger Gran Via", "Madrid", True),
    ("R004", "Lumbre Burger La Latina", "Madrid", True),
    ("R005", "Lumbre Burger Chamberi", "Madrid", True),
    ("R006", "Lumbre Burger Gotico", "Barcelona", True),
    ("R007", "Lumbre Burger Gracia", "Barcelona", True),
    ("R008", "Lumbre Burger Eixample", "Barcelona", True),
    ("R009", "Lumbre Burger Barceloneta", "Barcelona", True),
    ("R010", "Lumbre Burger Ruzafa", "Valencia", True),
    ("R011", "Lumbre Burger Ciutat Vella", "Valencia", True),
    ("R012", "Lumbre Burger Triana", "Seville", True),
    ("R013", "Lumbre Burger Alameda", "Seville", False),
    ("R014", "Lumbre Burger Centro", "Malaga", False),
    ("R015", "Lumbre Burger Soho", "Malaga", False),
)


def build_restaurants() -> list[dict]:
    """Return the 15 restaurants as dicts (12 pilot, 3 control)."""

    return [
        {
            "restaurant_id": restaurant_id,
            "name": name,
            "city": city,
            "is_pilot": is_pilot,
        }
        for restaurant_id, name, city, is_pilot in RESTAURANTS
    ]


def _select(rng: random.Random, candidates: list[int], rate: float) -> set[int]:
    """Pick exactly round(len(candidates) * rate) members, reproducibly."""

    count = round(len(candidates) * rate)
    pool = list(candidates)
    rng.shuffle(pool)
    return set(pool[:count])


def build_applications(rng: random.Random, restaurants: list[dict]) -> list[dict]:
    """Build the application rows: one dict per application, one datetime (or
    None) per funnel stage."""

    rows: list[dict] = []
    per_restaurant = APPLICATIONS_PER_RESTAURANT
    application_seq = 0

    for restaurant in restaurants:
        for _ in range(per_restaurant):
            application_seq += 1
            day_offset = rng.uniform(0, WINDOW_DAYS - 1)
            second_offset = rng.randrange(24 * 3600)
            applied_at = DATA_CUT - timedelta(
                days=day_offset, seconds=second_offset
            )
            row: dict = {
                "application_id": f"A{application_seq:06d}",
                "restaurant_id": restaurant["restaurant_id"],
                "is_pilot": restaurant["is_pilot"],
                "applied_at": applied_at,
                **{f"{stage}_at": None for stage in STAGES[1:]},
            }
            rows.append(row)

    order = list(range(len(rows)))
    reached = order
    for stage in STAGES[1:]:
        if stage == "day30_active":
            selected = _select(rng, reached, STAGE_RATES[stage])
            for idx in selected:
                rows[idx][f"{stage}_at"] = rows[idx]["day1_worked_at"] + timedelta(
                    days=DAY30_OFFSET_DAYS
                )
            reached = sorted(selected)
            continue
        if stage == "day90_active":
            selected = _select(rng, reached, STAGE_RATES[stage])
            for idx in selected:
                rows[idx][f"{stage}_at"] = rows[idx]["day1_worked_at"] + timedelta(
                    days=DAY90_OFFSET_DAYS
                )
            reached = sorted(selected)
            continue

        median_days = STAGE_MEDIAN_DAYS[stage]
        sigma = 0.5
        selected = _select(rng, reached, STAGE_RATES[stage])
        for idx in selected:
            elapsed_days = rng.lognormvariate(math.log(median_days), sigma)
            previous_stage = STAGES[STAGES.index(stage) - 1]
            previous_at = rows[idx][f"{previous_stage}_at"]
            minutes = round(elapsed_days * 24 * 60)
            rows[idx][f"{stage}_at"] = previous_at + timedelta(minutes=minutes)
        reached = sorted(selected)

    return rows


def _format_timestamp(value: datetime | None) -> str:
    return "" if value is None else value.replace(microsecond=0).isoformat()


def _application_fieldnames() -> list[str]:
    fields = ["application_id", "restaurant_id", "is_pilot"]
    fields.extend(f"{stage}_at" for stage in STAGES)
    return fields


def write_seed_files(output_dir: Path = SEED_DIR) -> None:
    """Write restaurants.csv and applications.csv into output_dir."""

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    restaurants = build_restaurants()
    applications = build_applications(rng, restaurants)

    restaurants_path = output_dir / "restaurants.csv"
    with restaurants_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["restaurant_id", "name", "city", "is_pilot"])
        for restaurant in restaurants:
            writer.writerow(
                [
                    restaurant["restaurant_id"],
                    restaurant["name"],
                    restaurant["city"],
                    "true" if restaurant["is_pilot"] else "false",
                ]
            )

    applications_path = output_dir / "applications.csv"
    with applications_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(_application_fieldnames())
        for row in applications:
            writer.writerow(
                [
                    row["application_id"],
                    row["restaurant_id"],
                    "true" if row["is_pilot"] else "false",
                    *(
                        _format_timestamp(row[f"{stage}_at"])
                        for stage in STAGES
                    ),
                ]
            )


if __name__ == "__main__":
    write_seed_files()
    print(f"wrote restaurants.csv and applications.csv to {SEED_DIR}")
