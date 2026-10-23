"""Per-adapter health checks (F12 T2, S4).

specs/06-integration-rollout.md section 2: "Health checks per adapter; a
degraded adapter pauses only the flows that need it".

GET /health/adapters returns one entry per registered client system with:

- ``status``: ``ok`` (probe succeeded), ``degraded`` (probe failed or timed
  out) or ``unknown`` (adapter missing, not constructible, or without a
  health probe),
- ``last_checked_at``: the time of this check,
- ``failure_reason``: why the probe failed, or None when ok.

The registry discovers adapters defensively: each system maps to an adapter
module and candidate class names resolved with importlib at check time. A
missing adapter reports ``unknown``; discovery and probing can never crash
the endpoint. Adapters opt into probing by implementing the health-probe
protocol: an instance method ``health_check()`` that returns normally when
the client system is reachable and raises (or times out) when it is not.
Adapters built today without the method simply report unknown until the
method lands, so the registry works with hiredesk/twilio/simulator now and
extends to nomina360/shiftgrid/learnbite/m365 by dropping files in
app/adapters/ (owned by the adapters workstream).

Probes run with a short timeout (PROBE_TIMEOUT_SECONDS) in a worker thread,
so one hung client system cannot hang the health endpoint. GET /health stays
the process liveness check (F01); this endpoint is the per-system view.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.degraded import STATUS_DEGRADED, STATUS_OK, STATUS_UNKNOWN

router = APIRouter(tags=["health"])

PROBE_TIMEOUT_SECONDS = 2.0

# One registered client system per port in OUTBOX_PORTS (app/db/models.py).
# ``attributes`` lists the adapter class names to try, in order: the adapters
# workstream owns app/adapters/ and may rename classes as real adapters land.
@dataclass(frozen=True)
class AdapterSpec:
    system: str
    module: str
    attributes: tuple[str, ...]


ADAPTER_SPECS: tuple[AdapterSpec, ...] = (
    AdapterSpec("hiredesk", "app.adapters.hiredesk", ("HireDeskAdapter",)),
    AdapterSpec("nomina360", "app.adapters.nomina360", ("Nomina360Adapter",)),
    AdapterSpec("shiftgrid", "app.adapters.shiftgrid", ("ShiftGridAdapter",)),
    AdapterSpec("learnbite", "app.adapters.learnbite", ("LearnBiteAdapter",)),
    AdapterSpec("m365", "app.adapters.m365", ("M365CalendarAdapter",)),
    AdapterSpec("whatsapp", "app.adapters.twilio", ("TwilioChannelAdapter",)),
)


@dataclass(frozen=True)
class AdapterHealth:
    """One entry of GET /health/adapters."""

    system: str
    status: str
    last_checked_at: datetime
    failure_reason: str | None


HealthProbe = Callable[[], None]


def _resolve_probe(spec: AdapterSpec) -> tuple[HealthProbe | None, str | None]:
    """importlib discovery -> (probe, unknown_reason).

    Returns (probe, None) when the adapter implements the health-probe
    protocol; (None, reason) when the system must be reported unknown.
    """
    try:
        module = importlib.import_module(spec.module)
    except ModuleNotFoundError as exc:
        if exc.name is not None and exc.name == spec.module:
            return None, f"adapter not registered: no module {spec.module}"
        # The module path exists but an import inside it failed: still
        # unknown, never a crash, with the import error named.
        return None, f"adapter could not be imported: {exc}"
    except Exception as exc:  # defensive: any import failure is unknown
        return None, f"adapter could not be imported: {exc}"

    cls = None
    for attribute in spec.attributes:
        candidate = getattr(module, attribute, None)
        if candidate is not None:
            cls = candidate
            break
    if cls is None:
        return None, (
            f"adapter class not found in {spec.module} "
            f"(expected one of {', '.join(spec.attributes)})"
        )

    try:
        from_settings = getattr(cls, "from_settings", None)
        if callable(from_settings):
            from app.settings import settings

            instance = from_settings(settings)
        else:
            instance = cls()
    except Exception as exc:
        return None, f"adapter could not be constructed: {exc}"

    probe = getattr(instance, "health_check", None)
    if not callable(probe):
        return None, (
            f"adapter {cls.__name__} has no health probe: "
            "implement health_check() to enable status ok/degraded"
        )
    return probe, None


def _run_probe(
    system: str,
    probe: HealthProbe | None,
    unknown_reason: str | None,
    timeout: float,
    at: datetime,
) -> AdapterHealth:
    """One probe run under the short-timeout budget; never raises."""
    if probe is None:
        return AdapterHealth(system, STATUS_UNKNOWN, at, unknown_reason)

    # A worker thread bounds the wait: shutdown(wait=False) abandons a hung
    # probe instead of letting the health endpoint wait out the full call.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"health-{system}")
    try:
        future: Future[None] = executor.submit(probe)
        try:
            future.result(timeout=timeout)
        except FuturesTimeoutError:
            return AdapterHealth(
                system,
                STATUS_DEGRADED,
                at,
                f"health probe timed out after {timeout}s",
            )
        except Exception as exc:
            return AdapterHealth(system, STATUS_DEGRADED, at, f"health probe failed: {exc}")
    finally:
        executor.shutdown(wait=False)
    return AdapterHealth(system, STATUS_OK, at, None)


def check_adapters(
    probes: Mapping[str, HealthProbe] | None = None,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    now: datetime | None = None,
    specs: tuple[AdapterSpec, ...] = ADAPTER_SPECS,
) -> list[AdapterHealth]:
    """One health check per registered client system.

    ``probes`` injects explicit probes per system (tests fault per test,
    never ambient); systems absent from the map report unknown. Without it,
    adapters are discovered defensively via importlib.
    """
    at = now or datetime.now(UTC)
    results: list[AdapterHealth] = []
    for spec in specs:
        if probes is not None:
            probe = probes.get(spec.system)
            reason = None if probe else "adapter not registered: no health probe"
        else:
            probe, reason = _resolve_probe(spec)
        results.append(_run_probe(spec.system, probe, reason, timeout, at))
    return results


@router.get("/health/adapters")
def adapters_health() -> dict[str, object]:
    """Per-adapter health: one entry per registered client system.

    Defensive by contract: a missing or broken adapter is an entry with
    status unknown, never a failed request.
    """
    checks = check_adapters()
    return {
        "adapters": [
            {
                "system": check.system,
                "status": check.status,
                "last_checked_at": check.last_checked_at.isoformat(),
                "failure_reason": check.failure_reason,
            }
            for check in checks
        ]
    }
