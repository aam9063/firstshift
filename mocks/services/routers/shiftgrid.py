"""ShiftGrid mock (workforce management): rotas and open shifts.

Mock API per design/integration-contracts.md section 3. The Thursday lock is
modeled in core policy, not here; the mock serves the seeded open shifts and
accepts assignments keyed by the Nómina360 employee ref.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mocks.services.seed import SeedData, build_seed

router = APIRouter(prefix="/shiftgrid", tags=["shiftgrid"])


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


@router.get("/restaurants/{restaurant_id}/open-shifts")
def list_open_shifts(restaurant_id: str) -> list[dict[str, Any]]:
    if restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    return [
        shift
        for shift in store.open_shifts
        if shift["restaurant_id"] == restaurant_id
    ]


@router.get("/rotas")
def get_rotas() -> list[dict[str, Any]]:
    return [
        {"shiftgrid_shift_id": shift_id, "nomina360_employee_ref": employee_ref}
        for shift_id, employee_ref in sorted(store.assignments.items())
    ]


@router.post("/shifts/{shift_id}/assign")
def assign_shift(shift_id: str, payload: ShiftAssign) -> dict[str, Any]:
    if not any(
        shift["shiftgrid_shift_id"] == shift_id for shift in store.open_shifts
    ):
        raise HTTPException(status_code=404, detail="unknown shift")

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


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
