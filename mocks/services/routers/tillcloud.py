"""TillCloud mock (POS): read-only sales and the derived labor forecast.

Mock API per design/integration-contracts.md section 4. Read-only by design,
like the real system: no write endpoints exist. Sales are synthetic but
deterministic per restaurant, date and 15-minute interval, with Friday and
Saturday peaks.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from mocks.services.seed import SeedData, build_seed

router = APIRouter(prefix="/tillcloud", tags=["tillcloud"])


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.restaurants: dict[str, bool] = {}

    def reset(self, seed: SeedData) -> None:
        self.restaurants = {r.restaurant_id: r.is_pilot for r in seed.restaurants}


store = Store()

OPENING = time(10, 0)
CLOSING = time(23, 45)
INTERVAL_MINUTES = 15


def _slice_sales(restaurant_id: str, interval_start: datetime, is_pilot: bool) -> float:
    rng = random.Random(f"tillcloud:{restaurant_id}:{interval_start.isoformat()}")
    weekday = interval_start.weekday()
    hour = interval_start.hour

    base = 45.0 if is_pilot else 32.0
    if weekday in (4, 5):  # Friday and Saturday peaks
        base *= 1.5
    if 12 <= hour < 15 or 19 <= hour < 22:  # lunch and dinner peaks
        base *= 1.8
    return round(base * (0.6 + 0.8 * rng.random()), 2)


@router.get("/restaurants/{restaurant_id}/sales")
def get_sales(restaurant_id: str, day: str | None = None) -> dict[str, Any]:
    if restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")

    sales_day = date.fromisoformat(day) if day else datetime.now(UTC).date()
    is_pilot = store.restaurants[restaurant_id]
    cursor = datetime.combine(sales_day, OPENING)
    end = datetime.combine(sales_day, CLOSING)

    slices = []
    while cursor <= end:
        slices.append(
            {
                "interval_start": cursor.isoformat(),
                "sales_eur": _slice_sales(restaurant_id, cursor, is_pilot),
            }
        )
        cursor += timedelta(minutes=INTERVAL_MINUTES)
    return {"restaurant_id": restaurant_id, "granularity": "15m", "slices": slices}


@router.get("/restaurants/{restaurant_id}/forecast")
def get_forecast(restaurant_id: str) -> dict[str, Any]:
    if restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")

    # Derived weekly forecast: average demand per weekday role bucket,
    # consistent with the sales pattern above.
    weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    forecast = [
        {
            "weekday": label,
            "kitchen": 3 if label in ("fri", "sat") else 2,
            "till": 2,
            "foh": 2 if label in ("fri", "sat") else 1,
            "drive_thru": 2 if label in ("fri", "sat") else 1,
        }
        for label in weekdays
    ]
    return {"restaurant_id": restaurant_id, "week": forecast}


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
