"""T2 (S2) seed rules for the mock services: specs/04 section 1.2.

Covers the seed loader in mocks/services/seed.py: restaurants from
mocks/seed/restaurants.csv, one named manager per restaurant, open shifts for
the next 3 weeks following the Lumbre Burger pattern (weekday lunches, evening
closes on Friday and Saturday, drive-thru peaks), and 200 historical
candidates.

Stated choice (task T2): the 200 historical candidates are generated with a
seeded RNG, distinct from mocks/seed/applications.csv. That CSV is the closed
6-month funnel history behind mocks/funnel.py, with every row already in its
final funnel state; the HireDesk mock needs live in-flight candidate records
to serve and to receive stage updates, and reusing closed historical rows
would clash with their final outcomes.
"""

from datetime import date, datetime, timedelta

from mocks.services.seed import (
    HISTORICAL_CANDIDATES,
    SHIFTS_DAYS,
    build_seed,
    generate_historical_candidates,
    generate_managers,
    generate_open_shifts,
    load_restaurants,
)

TODAY = date(2025, 7, 1)  # a Tuesday, so the 3-week window contains Fri/Sat


def test_restaurants_match_csv_pilot_control_split() -> None:
    restaurants = load_restaurants()

    assert len(restaurants) == 15
    assert sum(1 for r in restaurants if r.is_pilot) == 12
    assert sum(1 for r in restaurants if not r.is_pilot) == 3
    assert [r.restaurant_id for r in restaurants] == [
        f"R{n:03d}" for n in range(1, 16)
    ]
    assert restaurants[0].name == "Lumbre Burger Sol"


def test_managers_one_named_per_restaurant() -> None:
    restaurants = load_restaurants()

    managers = generate_managers(restaurants)

    assert len(managers) == len(restaurants) == 15
    assert {m.restaurant_id for m in managers} == {
        r.restaurant_id for r in restaurants
    }
    assert all(len(m.name.split()) >= 2 for m in managers), "managers are named"
    assert len({m.manager_id for m in managers}) == 15


def test_open_shifts_deterministic_for_same_seed_and_date() -> None:
    restaurants = load_restaurants()

    first = generate_open_shifts(restaurants, TODAY)
    second = generate_open_shifts(restaurants, TODAY)

    assert first == second


def test_open_shifts_inside_next_three_weeks_with_known_roles() -> None:
    restaurants = load_restaurants()

    shifts = generate_open_shifts(restaurants, TODAY)

    assert shifts, "seeded rota is empty"
    allowed_roles = {"kitchen", "till", "foh", "drive_thru"}
    for shift in shifts:
        assert TODAY < shift.starts_at.date() <= TODAY + timedelta(
            days=SHIFTS_DAYS
        )
        assert shift.role in allowed_roles
        assert shift.ends_at > shift.starts_at


def test_open_shifts_pattern_lunch_evening_close_drive_thru() -> None:
    restaurants = load_restaurants()

    shifts = generate_open_shifts(restaurants, TODAY)

    friday_dates = [
        TODAY + timedelta(days=n)
        for n in range(1, SHIFTS_DAYS + 1)
        if (TODAY + timedelta(days=n)).weekday() == 4
    ]
    saturday_dates = [
        TODAY + timedelta(days=n)
        for n in range(1, SHIFTS_DAYS + 1)
        if (TODAY + timedelta(days=n)).weekday() == 5
    ]

    # Evening closes: Friday and Saturday shifts that end after midnight.
    closes = {
        s.starts_at.date()
        for s in shifts
        if s.ends_at.date() > s.starts_at.date()
    }
    assert friday_dates[0] in closes
    assert saturday_dates[0] in closes

    # Weekday lunches: kitchen shifts starting at 11:00 on a midweek day.
    lunches = [
        s
        for s in shifts
        if s.role == "kitchen"
        and s.starts_at.weekday() < 4
        and s.starts_at.hour == 11
    ]
    assert lunches

    # Drive-thru peaks exist somewhere in the window.
    assert any(s.role == "drive_thru" for s in shifts)

    # Volume: enough open shifts per restaurant for matching later. Only
    # the three complete weeks of the window are counted.
    per_restaurant_week: dict[tuple[str, int], int] = {}
    for shift in shifts:
        week = (shift.starts_at.date() - TODAY).days // 7
        per_restaurant_week[(shift.restaurant_id, week)] = (
            per_restaurant_week.get((shift.restaurant_id, week), 0) + 1
        )
    complete_week_counts = [
        count
        for (restaurant_id, week), count in per_restaurant_week.items()
        if week < 3
    ]
    assert len(complete_week_counts) == 45
    assert min(complete_week_counts) >= 5


def test_historical_candidates_deterministic_and_distinct() -> None:
    restaurants = load_restaurants()

    first = generate_historical_candidates(restaurants, TODAY)
    second = generate_historical_candidates(restaurants, TODAY)

    assert len(first) == HISTORICAL_CANDIDATES == 200
    assert first == second
    assert len({c.candidate_id for c in first}) == 200


def test_historical_candidates_distinct_from_funnel_history() -> None:
    import csv
    from pathlib import Path

    restaurants = load_restaurants()
    candidates = generate_historical_candidates(restaurants, TODAY)

    applications_csv = (
        Path(__file__).resolve().parents[1] / "mocks" / "seed" / "applications.csv"
    )
    with applications_csv.open(newline="", encoding="utf-8") as handle:
        funnel_ids = {row["application_id"] for row in csv.DictReader(handle)}

    candidate_ids = {c.candidate_id for c in candidates}
    assert candidate_ids.isdisjoint(funnel_ids)


def test_build_seed_assembles_everything() -> None:
    seed = build_seed(today=TODAY)

    assert len(seed.restaurants) == 15
    assert len(seed.managers) == 15
    assert len(seed.open_shifts) > 0
    assert len(seed.candidates) == 200
    assert isinstance(seed.candidates[0].created_at, datetime)
