"""Seed loader and generators for the mock client services (task T2, S2).

Seeds mocks/ from mocks/seed/ per specs/04 section 1.2: the 15 restaurants
from restaurants.csv (12 pilot + 3 control), one named manager per
restaurant, open shifts for the next 3 weeks following the Lumbre Burger
pattern (weekday lunches, evening closes on Friday and Saturday, drive-thru
peaks), and 200 historical candidates for the HireDesk mock.

Determinism: every generator is seeded and takes an explicit ``today`` date,
so the same seed and date produce identical output (see
tests/test_mocks_seed.py). The modules default to ``date.today()`` only at
service startup.

Stated choice: the 200 historical candidates are generated with a seeded RNG,
distinct from mocks/seed/applications.csv. That CSV is the closed 6-month
funnel history behind mocks/funnel.py, with every row already in its final
funnel state; the HireDesk mock needs live in-flight candidate records to
serve and to receive stage updates, and reusing closed historical rows would
clash with their final outcomes.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

SEED = 42
SHIFTS_DAYS = 21
HISTORICAL_CANDIDATES = 200

RESTAURANTS_CSV = Path(__file__).resolve().parents[1] / "seed" / "restaurants.csv"

ROLES = ("kitchen", "till", "foh", "drive_thru")

FIRST_NAMES = (
    "Marta", "Javier", "Lucia", "Pablo", "Nerea", "Adrian", "Carla", "Diego",
    "Sofia", "Marcos", "Irene", "Alvaro", "Beatriz", "Ruben", "Carmen",
    "Sergio", "Elena", "Hugo", "Noelia", "Iker", "Ainhoa", "Guillem",
    "Paula", "Raul", "Judith", "Oriol", "Vera", "Unai", "Rocio", "Bruno",
)
LAST_NAMES = (
    "Garcia", "Martinez", "Lopez", "Sanchez", "Perez", "Gomez", "Fernandez",
    "Ruiz", "Diaz", "Moreno", "Alvarez", "Romero", "Navarro", "Torres",
    "Dominguez", "Vazquez", "Castro", "Ortega", "Rios", "Marin", "Ibanez",
    "Serrano", "Molina", "Delgado", "Pascual", "Ferran",
)

CANDIDATE_STAGES = (
    "new", "new", "screening", "screening", "interview", "offer",
    "hired", "rejected",
)
CANDIDATE_SOURCES = ("qr_poster", "walk_in", "whatsapp_referral", "job_board")


@dataclass(frozen=True)
class Restaurant:
    restaurant_id: str
    name: str
    city: str
    is_pilot: bool


@dataclass(frozen=True)
class Manager:
    manager_id: str
    restaurant_id: str
    name: str


@dataclass(frozen=True)
class OpenShift:
    shiftgrid_shift_id: str
    restaurant_id: str
    starts_at: datetime
    ends_at: datetime
    role: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    first_name: str
    last_name: str
    phone: str
    restaurant_id: str
    stage: str
    source: str
    created_at: datetime


@dataclass(frozen=True)
class SeedData:
    restaurants: list[Restaurant]
    managers: list[Manager]
    open_shifts: list[OpenShift]
    candidates: list[Candidate]


def load_restaurants(csv_path: Path = RESTAURANTS_CSV) -> list[Restaurant]:
    """Load the 15 restaurants from mocks/seed/restaurants.csv."""

    restaurants: list[Restaurant] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            restaurants.append(
                Restaurant(
                    restaurant_id=row["restaurant_id"],
                    name=row["name"],
                    city=row["city"],
                    is_pilot=row["is_pilot"] == "true",
                )
            )
    return restaurants


def generate_managers(
    restaurants: list[Restaurant], seed: int = SEED
) -> list[Manager]:
    """One named manager per restaurant, drawn from a seeded name pool."""

    rng = random.Random(seed * 10 + 1)
    combos = [
        (first, last)
        for first in FIRST_NAMES
        for last in LAST_NAMES
    ]
    rng.shuffle(combos)
    managers: list[Manager] = []
    for index, restaurant in enumerate(sorted(restaurants, key=lambda r: r.restaurant_id)):
        first, last = combos[index]
        managers.append(
            Manager(
                manager_id=f"mgr-{restaurant.restaurant_id.lower()}",
                restaurant_id=restaurant.restaurant_id,
                name=f"{first} {last}",
            )
        )
    return managers


def _shift(
    restaurant_id: str, day: date, start: time, hours: float, role: str, slot: str
) -> OpenShift:
    starts_at = datetime.combine(day, start)
    return OpenShift(
        shiftgrid_shift_id=f"sg-{restaurant_id.lower()}-{day.isoformat()}-{slot}-{role}",
        restaurant_id=restaurant_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=hours),
        role=role,
    )


def generate_open_shifts(
    restaurants: list[Restaurant], today: date, seed: int = SEED
) -> list[OpenShift]:
    """Open shifts for the next 3 weeks per restaurant.

    Pattern: weekday lunches (11:00-16:00 kitchen and till/FOH), evening
    closes on Friday and Saturday (17:00-00:30 across roles), and drive-thru
    peaks. A per-restaurant seeded RNG drops some weekday shifts for volume
    variation, but Friday and Saturday closes are always generated.
    """

    shifts: list[OpenShift] = []
    for restaurant in sorted(restaurants, key=lambda r: r.restaurant_id):
        rng = random.Random(f"{seed}:{restaurant.restaurant_id}")
        rid = restaurant.restaurant_id
        for day_offset in range(1, SHIFTS_DAYS + 1):
            day = today + timedelta(days=day_offset)
            weekday = day.weekday()  # Monday is 0

            if weekday <= 3:  # Tuesday to Friday: lunch pattern
                if rng.random() < 0.9:
                    shifts.append(_shift(rid, day, time(11, 0), 5.0, "kitchen", "lunch"))
                if rng.random() < 0.8:
                    shifts.append(_shift(rid, day, time(11, 0), 5.0, "till", "lunch"))
                if rng.random() < 0.8:
                    shifts.append(_shift(rid, day, time(11, 0), 5.0, "foh", "lunch"))
                if rng.random() < 0.6:
                    shifts.append(
                        _shift(rid, day, time(11, 30), 4.0, "drive_thru", "lunch")
                    )
            elif weekday == 4:  # Friday: lunch plus evening close
                shifts.append(_shift(rid, day, time(11, 0), 5.0, "kitchen", "lunch"))
                shifts.append(_shift(rid, day, time(11, 0), 5.0, "till", "lunch"))
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "kitchen", "close"))
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "till", "close"))
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "foh", "close"))
                shifts.append(_shift(rid, day, time(18, 0), 5.0, "drive_thru", "peak"))
            elif weekday == 5:  # Saturday: evening close plus peaks
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "kitchen", "close"))
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "till", "close"))
                shifts.append(_shift(rid, day, time(17, 0), 7.5, "foh", "close"))
                shifts.append(_shift(rid, day, time(12, 0), 4.0, "drive_thru", "peak"))
                shifts.append(_shift(rid, day, time(18, 0), 5.0, "drive_thru", "peak"))
            else:  # Sunday: light service
                if rng.random() < 0.7:
                    shifts.append(_shift(rid, day, time(12, 0), 6.0, "till", "lunch"))

    return shifts


def generate_historical_candidates(
    restaurants: list[Restaurant],
    today: date,
    count: int = HISTORICAL_CANDIDATES,
    seed: int = SEED,
) -> list[Candidate]:
    """200 historical HireDesk candidates from a seeded RNG.

    Distinct from mocks/seed/applications.csv by design (see module
    docstring): funnel history is closed, these are live in-flight records.
    """

    rng = random.Random(seed * 10 + 2)
    pilot_ids = [r.restaurant_id for r in restaurants if r.is_pilot]
    control_ids = [r.restaurant_id for r in restaurants if not r.is_pilot]

    candidates: list[Candidate] = []
    for index in range(count):
        # Roughly 5 of every 6 candidates land in pilot restaurants, so the
        # pilot cohort has realistic volume for matching later.
        restaurant_id = (
            rng.choice(pilot_ids) if rng.random() < 5 / 6 else rng.choice(control_ids)
        )
        applied_at = datetime.combine(
            today - timedelta(days=rng.randint(0, 90)),
            time(rng.randint(9, 22), rng.randint(0, 59)),
        )
        candidates.append(
            Candidate(
                candidate_id=f"hdc-{index + 1:04d}",
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
                phone=f"+34 6{rng.randint(100, 999)} {rng.randint(100, 999)}"
                f" {rng.randint(100, 999)}",
                restaurant_id=restaurant_id,
                stage=rng.choice(CANDIDATE_STAGES),
                source=rng.choice(CANDIDATE_SOURCES),
                created_at=applied_at,
            )
        )
    return candidates


def build_seed(today: date | None = None) -> SeedData:
    """Load and generate the full seed dataset for the mock services."""

    effective_today = today if today is not None else date.today()
    restaurants = load_restaurants()
    return SeedData(
        restaurants=restaurants,
        managers=generate_managers(restaurants),
        open_shifts=generate_open_shifts(restaurants, effective_today),
        candidates=generate_historical_candidates(restaurants, effective_today),
    )
