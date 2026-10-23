"""ShiftGrid adapter: workforce management writes with optimistic checks.

Contract: app/ports/shiftgrid.py ShiftGridPort; design/integration-contracts
section 3. Hardened failure modes (specs/06 §1):

- Open shift filled by the manager while the agent is offering it: the
  adapter checks the shift before assigning and re-checks after a 409,
  raising ShiftGridShiftFilledError with who took it (a lost race is never
  retried; the agent offers another shift).
- Rota published on Thursdays: ``get_rota`` reports the publication state of
  the weekly cycle so callers respect the lock instead of discovering it at
  write time.
- Timezone and DST: shift times arrive as naive local ISO strings plus a
  ``local_timezone`` field; the adapter converts with the zone's rules
  (fold=0 for the spring-forward gap) and always returns aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.ports.errors import PortRateLimitedError, PortTransientError, PortValidationError
from app.ports.shiftgrid import (
    OpenShiftRead,
    RotaAssignment,
    RotaView,
    ShiftAssign,
    ShiftGridShift,
    ShiftGridShiftFilledError,
    ShiftRelease,
)


def _to_utc(raw: dict[str, Any], field: str) -> datetime:
    """Convert one mock timestamp to aware UTC.

    Without a ``local_timezone`` the mock's timestamps are treated as UTC;
    with one, naive local times are localized with fold=0 (the deterministic
    PEP 495 choice for the spring-forward gap) and converted to UTC.
    """

    value = raw[field]
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    timezone_name = raw.get("local_timezone")
    if parsed.tzinfo is None:
        zone = ZoneInfo(timezone_name) if timezone_name else UTC
        parsed = parsed.replace(tzinfo=zone, fold=0)
    return parsed.astimezone(UTC)


def _shift_from(raw: dict[str, Any]) -> ShiftGridShift:
    return ShiftGridShift(
        shiftgrid_shift_id=raw["shiftgrid_shift_id"],
        restaurant_id=raw["restaurant_id"],
        starts_at=_to_utc(raw, "starts_at"),
        ends_at=_to_utc(raw, "ends_at"),
        role=raw["role"],
        assigned_to=raw.get("assigned_to"),
    )


class ShiftGridAdapter:
    """HTTP adapter against the ShiftGrid (mock) REST surface."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=10.0, trust_env=False
        )

    def _raise(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise PortRateLimitedError("shiftgrid throttled the request")
        if response.status_code >= 500:
            raise PortTransientError(f"shiftgrid transient failure: {response.status_code}")
        if response.status_code >= 400:
            raise PortValidationError(
                f"shiftgrid rejected the request: {response.status_code} {response.text[:200]}"
            )

    def list_open_shifts(self, restaurant_id: str) -> list[OpenShiftRead]:
        try:
            response = self._client.get(f"/shiftgrid/restaurants/{restaurant_id}/open-shifts")
        except httpx.TransportError as exc:
            raise PortTransientError(f"shiftgrid unreachable: {exc}") from exc
        self._raise(response)
        return [_shift_from(raw) for raw in response.json()]

    def get_shift(self, shiftgrid_shift_id: str) -> ShiftGridShift:
        """One shift with its assignment; the optimistic re-check reads this."""

        try:
            response = self._client.get(f"/shiftgrid/shifts/{shiftgrid_shift_id}")
        except httpx.TransportError as exc:
            raise PortTransientError(f"shiftgrid unreachable: {exc}") from exc
        self._raise(response)
        return _shift_from(response.json())

    def get_rota(self, *, week: str, today: str | None = None) -> RotaView:
        """The weekly rota with its Thursday publication state.

        ``today`` pins the request date so the cycle is testable; the mock
        applies the same rule.
        """

        try:
            response = self._client.get(
                "/shiftgrid/rotas", params={"week": week, "today": today}
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"shiftgrid unreachable: {exc}") from exc
        self._raise(response)
        body = response.json()
        return RotaView(
            week=body["week"],
            published=body["published"],
            published_at=body.get("published_at"),
            assignments=[
                RotaAssignment.model_validate(a) for a in body.get("assignments", [])
            ],
        )

    def assign_shift(
        self, payload: ShiftAssign, *, idempotency_key: str
    ) -> dict[str, Any]:
        """Optimistic assignment: check, assign, re-check on conflict.

        A 409 means someone else took the shift (usually the manager filling
        it manually); the re-check confirms the upstream state and the typed
        error carries who took it, so the agent never retries a lost race.
        """

        current = self.get_shift(payload.shiftgrid_shift_id)
        if current.assigned_to and current.assigned_to != payload.nomina360_employee_ref:
            raise ShiftGridShiftFilledError(payload.shiftgrid_shift_id, current.assigned_to)

        try:
            response = self._client.post(
                f"/shiftgrid/shifts/{payload.shiftgrid_shift_id}/assign",
                json=payload.model_dump(exclude={"shiftgrid_shift_id"}),
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"shiftgrid unreachable: {exc}") from exc
        if response.status_code == 409:
            filled = self.get_shift(payload.shiftgrid_shift_id)  # optimistic re-check
            raise ShiftGridShiftFilledError(
                payload.shiftgrid_shift_id, filled.assigned_to
            )
        self._raise(response)
        result: dict[str, Any] = response.json()
        return result

    def release_shift(self, payload: ShiftRelease) -> None:
        try:
            response = self._client.post(
                f"/shiftgrid/shifts/{payload.shiftgrid_shift_id}/release"
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"shiftgrid unreachable: {exc}") from exc
        self._raise(response)
