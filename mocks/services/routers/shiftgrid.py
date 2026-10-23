"""ShiftGrid mock (workforce management): rotas and open shifts.

Mock API per design/integration-contracts.md section 3. The Thursday lock is
modeled in core policy, not here; the mock serves the seeded open shifts and
accepts assignments keyed by the Nómina360 employee ref.

Fault injection (mocks/faults.py, F12 T1): shift_filled answers the first
assignment with 409 as if the manager filled the shift manually, thursday_rota
pins a request date so the weekly publication cycle is testable, and
dst_boundary serves shift times as naive local ISO strings on the DST
boundary plus a local_timezone field.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mocks.faults import faults
from mocks.services.seed import SeedData, build_seed

router = APIRouter(prefix="/shiftgrid", tags=["shiftgrid"])

ROTA_PUBLISH_WEEKDAY = 3  # Thursday: the rota locks until it publishes


class ShiftAssign(BaseModel):
    nomina360_employee_ref: str
    or_people_ops_exception_id: str | None = None


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.restaurants: set[str] = set()
        self.open_shifts: list[dict[str, Any]] = []
        self.assignments: dict[str, str] = {}

    def reset(self, seed: SeedData) -> None:
        self.restaurants = {r.restaurant_id for r in seed.restaurants}
        self.open_shifts = [
            {
                "shiftgrid_shift_id": s.shiftgrid_shift_id,
                "restaurant_id": s.restaurant_id,
                "starts_at": s.starts_at.isoformat(),
                "ends_at": s.ends_at.isoformat(),
                "role": s.role,
            }
            for s in seed.open_shifts
        ]
        self.assignments = {}


store = Store()


def _rota_monday(week: str) -> date:
    """The Monday of the ISO week containing ``week``."""

    day = date.fromisoformat(week)
    return day - timedelta(days=day.weekday())


def _rota_published(week: str, today: str | None) -> bool:
    """The rota for ``week`` publishes on the Thursday before its Monday.

    Without a pinned date the mock is lenient (published), so ordinary tests
    are deterministic; the thursday_rota fault pins ``today`` to exercise
    the cycle.
    """

    if not faults.is_active("shiftgrid", "thursday_rota"):
        return True
    pinned = today or faults.params("shiftgrid", "thursday_rota").get("today")
    if not pinned:
        return True
    publish_day = _rota_monday(week) - timedelta(days=4)  # the previous Thursday
    return date.fromisoformat(pinned) >= publish_day


def _shift_payload(shift: dict[str, Any]) -> dict[str, Any]:
    dst = faults.params("shiftgrid", "dst_boundary")
    payload = dict(shift)
    payload["assigned_to"] = store.assignments.get(shift["shiftgrid_shift_id"])
    if dst:
        timezone_name = dst.get("timezone", "Europe/Madrid")
        payload["local_timezone"] = timezone_name
        if (
            dst.get("shift_id") is None
            or dst.get("shift_id") == shift["shiftgrid_shift_id"]
        ) and dst.get("force_local_starts_at"):
            starts_at = datetime.fromisoformat(str(dst["force_local_starts_at"]))
            hours = (
                datetime.fromisoformat(payload["ends_at"])
                - datetime.fromisoformat(payload["starts_at"])
            )
            payload["starts_at"] = starts_at.isoformat()
            payload["ends_at"] = (starts_at + hours).isoformat()
    return payload


def _find_shift(shift_id: str) -> dict[str, Any]:
    for shift in store.open_shifts:
        if shift["shiftgrid_shift_id"] == shift_id:
            return shift
    raise HTTPException(status_code=404, detail="unknown shift")


@router.get("/restaurants/{restaurant_id}/open-shifts")
def list_open_shifts(restaurant_id: str) -> list[dict[str, Any]]:
    if restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    return [
        _shift_payload(shift)
        for shift in store.open_shifts
        if shift["restaurant_id"] == restaurant_id
    ]


@router.get("/shifts/{shift_id}")
def get_shift(shift_id: str) -> dict[str, Any]:
    return _shift_payload(_find_shift(shift_id))


@router.get("/rotas")
def get_rotas(week: str | None = None, today: str | None = None) -> dict[str, Any]:
    """One weekly rota with its publication state (the Thursday cycle)."""

    week_label = week or date.today().isoformat()
    return {
        "week": _rota_monday(week_label).isoformat(),
        "published": _rota_published(week_label, today),
        "assignments": [
            {"shiftgrid_shift_id": shift_id, "nomina360_employee_ref": employee_ref}
            for shift_id, employee_ref in sorted(store.assignments.items())
        ],
    }


@router.post("/shifts/{shift_id}/assign")
def assign_shift(shift_id: str, payload: ShiftAssign) -> dict[str, Any]:
    _find_shift(shift_id)

    filled = faults.params("shiftgrid", "shift_filled")
    if filled.get("shift_id") == shift_id:
        # The manager assigned the shift manually while the agent was
        # offering it: the upstream state changes and the write conflicts.
        store.assignments[shift_id] = str(filled.get("filled_by", "manager"))
        raise HTTPException(
            status_code=409,
            detail={
                "code": "shift_filled",
                "assigned_to": store.assignments[shift_id],
            },
        )

    existing = store.assignments.get(shift_id)
    if existing == payload.nomina360_employee_ref:
        return {
            "status": "ok",
            "shiftgrid_shift_id": shift_id,
            "idempotent": True,
        }
    if existing is not None:
        raise HTTPException(status_code=409, detail="shift already assigned")

    store.assignments[shift_id] = payload.nomina360_employee_ref
    return {"status": "ok", "shiftgrid_shift_id": shift_id}


@router.post("/shifts/{shift_id}/release")
def release_shift(shift_id: str) -> dict[str, Any]:
    _find_shift(shift_id)
    store.assignments.pop(shift_id, None)
    return {"status": "ok", "shiftgrid_shift_id": shift_id}


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
