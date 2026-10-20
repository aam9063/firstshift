"""Seed the skeleton entities (T1): restaurants from mocks/seed/restaurants.csv
and open shifts for the next three weeks (S2 window).

Run with: uv run python -m app.db.seed

Derivations from the CSV (documented, deterministic):
- brand_id: every seeded site is a Lumbre Burger location -> "lumbre".
- timezone: all seeded cities are in Spain -> "Europe/Madrid".
- bench_enabled: the bench operates in the 12 pilot sites, not the 3 controls
  (is_pilot column).
"""

import csv
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.db.models import OpenShift, Restaurant

RESTAURANTS_CSV = Path("mocks/seed/restaurants.csv")
MADRID = ZoneInfo("Europe/Madrid")
# Two concrete shifts per day and site: a kitchen shift (food contact, C-L8
# hygiene gate) and a till shift. Deterministic, reproducible ids via the
# ShiftGrid link, so seeding is idempotent.
DAILY_SHIFTS: tuple[tuple[str, time, time, bool], ...] = (
    ("kitchen", time(10, 0), time(18, 0), True),
    ("till", time(16, 0), time(23, 0), False),
)
SEED_DAYS = 21  # open shifts for the next 3 weeks


def seed_restaurants(conn: Connection, csv_path: Path = RESTAURANTS_CSV) -> None:
    """Upsert every row of the seed CSV; idempotent on the site code."""
    existing = set(conn.execute(select(Restaurant.code)).scalars())
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["restaurant_id"] in existing:
                continue
            conn.execute(
                insert(Restaurant).values(
                    id=uuid4(),
                    code=row["restaurant_id"],
                    brand_id="lumbre",
                    name=row["name"],
                    city=row["city"],
                    timezone="Europe/Madrid",
                    bench_enabled=row["is_pilot"] == "true",
                )
            )


def seed_open_shifts(conn: Connection, *, now: datetime | None = None) -> None:
    """Upsert open shifts for the next three weeks per restaurant; idempotent
    on the shiftgrid_shift_id link."""
    moment = now or datetime.now(MADRID)
    first_day = (moment + timedelta(days=1)).date()
    existing = set(conn.execute(select(OpenShift.shiftgrid_shift_id)).scalars())
    restaurants = conn.execute(select(Restaurant.id, Restaurant.code)).all()
    for restaurant_id, code in restaurants:
        for day_offset in range(SEED_DAYS):
            day = first_day + timedelta(days=day_offset)
            for role, start, end, requires_hygiene in DAILY_SHIFTS:
                shiftgrid_shift_id = f"{code}-{day:%Y%m%d}-{role}"
                if shiftgrid_shift_id in existing:
                    continue
                starts_at = datetime.combine(day, start, tzinfo=MADRID)
                ends_at = datetime.combine(day, end, tzinfo=MADRID)
                if ends_at <= starts_at:  # a shift crossing midnight
                    ends_at += timedelta(days=1)
                conn.execute(
                    insert(OpenShift).values(
                        id=uuid4(),
                        restaurant_id=restaurant_id,
                        shiftgrid_shift_id=shiftgrid_shift_id,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        role=role,
                        requires_food_hygiene=requires_hygiene,
                        status="open",
                    )
                )


def main() -> None:
    from app.db.base import make_engine
    from app.settings import settings

    engine = make_engine(settings.database_url)
    with engine.begin() as conn:
        seed_restaurants(conn)
        seed_open_shifts(conn)
    engine.dispose()
    print("seeded restaurants and open shifts")  # noqa: T201 (operator feedback)


if __name__ == "__main__":
    main()
