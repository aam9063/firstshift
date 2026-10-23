"""Deterministic fault injection for the mock client systems (F12 T1, S1).

The registry covers the failure modes listed in specs/06 section 1:

- HireDesk: duplicate webhook delivery, out-of-order stage event, candidate
  merged upstream, requisition closed mid-flow.
- Nomina360: 429 rate limiting (against the adapter's 60 req/min token
  bucket), HTTP 200 with an error body, partial employee creation, nightly
  CSV drift.
- ShiftGrid: open shift filled by the manager while being offered
  (optimistic check), Thursday rota publication, timezone/DST boundary.
- LearnBite: late completion webhook, re-enrollment, completion without
  webhook (poll fallback).
- M365: manager without calendar slots.

Determinism rules: no ambient state. Faults are only active when a test
injected them, they are cleared with ``faults.clear()`` (also on mock app
startup and by the DELETE /__faults admin endpoint), and every mode takes
explicit params so the same fault produces the same behavior on every run.
Routers consult the registry at request time, so a test can toggle a fault
per request: in-process through this module, or over HTTP through the
/__faults admin endpoints when driving a live mock server.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

# Every (system, mode) pair the registry knows about. Documented here so a
# typo in a test fails loudly instead of silently injecting nothing.
FAULT_MODES: dict[str, tuple[str, ...]] = {
    "hiredesk": (
        "duplicate_webhook_delivery",
        "out_of_order_stage_event",
        "candidate_merged",
        "requisition_closed",
    ),
    "nomina360": (
        "throttle_429",
        "error_body_200",
        "partial_creation",
        "csv_drift",
    ),
    "shiftgrid": (
        "shift_filled",
        "thursday_rota",
        "dst_boundary",
    ),
    "learnbite": (
        "late_completion_webhook",
        "re_enrollment",
        "completion_without_webhook",
    ),
    "m365": ("no_calendar_slots",),
}


class UnknownFaultMode(KeyError):
    """Raised when a test injects a (system, mode) pair nobody implements."""


class FaultRegistry:
    """Per-test fault state, keyed by (system, mode) with explicit params."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._active: dict[tuple[str, str], dict[str, Any]] = {}

    def inject(self, system: str, mode: str, **params: Any) -> None:
        """Activate one fault for the rest of the test (or until clear)."""

        if mode not in FAULT_MODES.get(system, ()):
            raise UnknownFaultMode(f"no fault mode {system}/{mode}")
        with self._lock:
            self._active[(system, mode)] = dict(params)

    def clear(self, system: str | None = None) -> None:
        """Deactivate every fault, or every fault of one system."""

        with self._lock:
            if system is None:
                self._active.clear()
            else:
                for key in [k for k in self._active if k[0] == system]:
                    del self._active[key]

    def consume(self, system: str, mode: str) -> dict[str, Any]:
        """Return the params and deactivate the fault: a one-shot mode."""

        with self._lock:
            return self._active.pop((system, mode), {})

    def is_active(self, system: str, mode: str) -> bool:
        with self._lock:
            return (system, mode) in self._active

    def params(self, system: str, mode: str) -> dict[str, Any]:
        """The params the test injected; empty dict when the fault is off."""

        with self._lock:
            return dict(self._active.get((system, mode), {}))

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Nested view for the admin endpoint and for test assertions."""

        with self._lock:
            view: dict[str, dict[str, dict[str, Any]]] = {}
            for (system, mode), params in self._active.items():
                view.setdefault(system, {})[mode] = dict(params)
            return view

    @contextmanager
    def injected(self, system: str, mode: str, **params: Any) -> Iterator[None]:
        """Scoped injection: the fault is active only inside the block."""

        self.inject(system, mode, **params)
        try:
            yield
        finally:
            with self._lock:
                self._active.pop((system, mode), None)


faults = FaultRegistry()


class FaultInjectionRequest(BaseModel):
    """Body of POST /__faults (toggle a fault on a live mock server)."""

    system: str
    mode: str
    params: dict[str, Any] = {}


router = APIRouter(tags=["faults"])


@router.post("/__faults")
def inject_fault(request: FaultInjectionRequest) -> dict[str, Any]:
    faults.inject(request.system, request.mode, **request.params)
    return {"active": faults.snapshot()}


@router.get("/__faults")
def list_faults() -> dict[str, Any]:
    return {"active": faults.snapshot()}


@router.delete("/__faults")
def clear_faults() -> dict[str, Any]:
    faults.clear()
    return {"active": faults.snapshot()}
