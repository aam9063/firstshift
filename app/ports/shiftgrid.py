"""ShiftGridPort: workforce management (integration-contracts section 3).

REST for rotas and open shifts. The rota locks Thursdays (modeled in core
policy); a person cannot be assigned until they exist in Nómina360, which the
core guards, not the adapter. Assignments are idempotent on the C-T5 key so
a retry never double books.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.ports.errors import PortValidationError


class ShiftGridShiftFilledError(PortValidationError):
    """The open shift was filled while the agent was offering it.

    Raised after the optimistic re-check confirms the upstream state change;
    the agent picks another shift instead of retrying a lost race.
    """

    def __init__(self, shiftgrid_shift_id: str, assigned_to: str | None) -> None:
        self.shiftgrid_shift_id = shiftgrid_shift_id
        self.assigned_to = assigned_to
        super().__init__(
            f"shift {shiftgrid_shift_id} was filled by {assigned_to or 'someone else'}"
        )


class OpenShiftRead(BaseModel):
    """One open shift as read from ShiftGrid; datetimes are aware UTC."""

    shiftgrid_shift_id: str
    restaurant_id: str
    starts_at: datetime  # aware UTC once through the adapter
    ends_at: datetime
    role: Literal["kitchen", "till", "foh", "drive_thru"]


class ShiftGridShift(OpenShiftRead):
    """An open shift plus its current assignment (for optimistic checks)."""

    assigned_to: str | None = None


class ShiftAssign(BaseModel):
    shiftgrid_shift_id: str
    nomina360_employee_ref: str  # guard: assignment only after csv_confirmed alta (O12)
    or_people_ops_exception_id: str | None = None


class ShiftRelease(BaseModel):
    shiftgrid_shift_id: str


class RotaAssignment(BaseModel):
    shiftgrid_shift_id: str
    nomina360_employee_ref: str


class RotaView(BaseModel):
    """One weekly rota and its publication state (the Thursday cycle)."""

    week: str  # ISO date of the rota's Monday
    published: bool
    published_at: str | None = None
    assignments: list[RotaAssignment] = []


class ShiftGridPort(Protocol):
    """Contract for the workforce management adapter."""

    def list_open_shifts(self, restaurant_id: str) -> list[OpenShiftRead]:
        """Open shifts for a restaurant, aware UTC datetimes."""
        ...

    def get_shift(self, shiftgrid_shift_id: str) -> ShiftGridShift:
        """One shift with its current assignment (optimistic re-check)."""
        ...

    def get_rota(self, *, week: str, today: str | None = None) -> RotaView:
        """The rota for the week of ``week``'s Monday, with publication state."""
        ...

    def assign_shift(
        self, payload: ShiftAssign, *, idempotency_key: str
    ) -> dict[str, Any]:
        """Idempotent assignment; raises ShiftGridShiftFilledError when the
        manager filled the shift meanwhile (optimistic check)."""
        ...

    def release_shift(self, payload: ShiftRelease) -> None:
        """Release a shift the FirstShift-assigned person cannot work."""
        ...


__all__ = [
    "OpenShiftRead",
    "PortValidationError",
    "RotaAssignment",
    "RotaView",
    "ShiftAssign",
    "ShiftGridPort",
    "ShiftGridShift",
    "ShiftGridShiftFilledError",
    "ShiftRelease",
]
