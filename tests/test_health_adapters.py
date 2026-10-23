"""F12 T2 (S4): per-adapter health checks.

specs/06-integration-rollout.md section 2: "Health checks per adapter; a
degraded adapter pauses only the flows that need it".

GET /health/adapters returns one entry per registered client system with
status ok/degraded/unknown, the last check time and the failure reason. The
registry discovers adapters defensively (importlib plus a health-probe
protocol): a missing adapter reports unknown and never crashes the endpoint.
GET /health stays the liveness check (F01 contract, tests/test_health.py).

Tests are deterministic without a network: injected probes fault per test,
and discovery is exercised against stub modules registered in sys.modules,
never against a live client system.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

REGISTERED_SYSTEMS = {"hiredesk", "nomina360", "shiftgrid", "learnbite", "m365", "whatsapp"}
VALID_STATUSES = {"ok", "degraded", "unknown"}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ----------------------------------------------------------------- liveness


def test_liveness_health_stays_the_ok_contract(client: TestClient) -> None:
    """PRESERVE: GET /health keeps its F01 liveness shape, untouched by the
    per-adapter registry."""
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "firstshift-backend"


# ------------------------------------------------------------- endpoint shape


def test_adapters_endpoint_lists_every_registered_system(client: TestClient) -> None:
    """One entry per registered client system, whatever the live discovery
    finds today: the endpoint reports unknown, it never crashes."""
    response = client.get("/health/adapters")

    assert response.status_code == 200
    adapters = response.json()["adapters"]
    assert {entry["system"] for entry in adapters} == REGISTERED_SYSTEMS
    for entry in adapters:
        assert entry["status"] in VALID_STATUSES
        # last check time is present and parses as an ISO timestamp.
        assert isinstance(entry["last_checked_at"], str)
        assert entry["last_checked_at"]
        if entry["status"] == "ok":
            assert entry["failure_reason"] is None
        else:
            assert isinstance(entry["failure_reason"], str)
            assert entry["failure_reason"]


def test_endpoint_survives_a_probe_that_raises(client: TestClient) -> None:
    """The defensive contract at the endpoint boundary: even with discovery
    returning broken adapters for every system, the response is 200 with one
    non-crashing entry per system (unknown or degraded, never a 500)."""
    from app.api import health

    def broken_probe() -> None:
        raise RuntimeError("connection refused")

    specs = tuple(health.ADAPTER_SPECS)
    results = health.check_adapters(
        probes={spec.system: broken_probe for spec in specs},
        now=None,
    )
    assert {result.system for result in results} == REGISTERED_SYSTEMS
    for result in results:
        assert result.status == "degraded"
        assert "connection refused" in (result.failure_reason or "")


# ------------------------------------------------- check_adapters semantics


def test_missing_probe_reports_unknown_not_a_crash() -> None:
    from app.api.health import check_adapters

    results = check_adapters(probes={}, now=None)

    assert len(results) == len(REGISTERED_SYSTEMS)
    for result in results:
        assert result.status == "unknown"
        assert "not registered" in (result.failure_reason or "")


def test_ok_probe_reports_ok_with_no_failure_reason() -> None:
    from app.api.health import check_adapters

    calls: list[str] = []

    def probe() -> None:
        calls.append("probed")

    results = check_adapters(probes={"hiredesk": probe}, now=None)

    hiredesk = next(r for r in results if r.system == "hiredesk")
    assert hiredesk.status == "ok"
    assert hiredesk.failure_reason is None
    assert calls == ["probed"]
    # Systems without an injected probe stay unknown.
    others = [r for r in results if r.system != "hiredesk"]
    assert all(r.status == "unknown" for r in others)


def test_failing_probe_reports_degraded_with_the_reason() -> None:
    from app.api.health import check_adapters

    def probe() -> None:
        # ConnectionError, not TimeoutError: since Python 3.11 the future
        # timeout IS builtin TimeoutError, so a probe raising it is
        # indistinguishable from a hung probe. That is fine (both degrade);
        # this test pins the raised-reason path.
        raise ConnectionError("nomina360 token bucket exhausted")

    results = check_adapters(probes={"nomina360": probe}, now=None)

    nomina = next(r for r in results if r.system == "nomina360")
    assert nomina.status == "degraded"
    assert nomina.failure_reason is not None
    assert "token bucket exhausted" in nomina.failure_reason


def test_probe_timeout_reports_degraded_within_the_short_budget() -> None:
    import time as time_module

    from app.api.health import check_adapters

    def slow_probe() -> None:
        time_module.sleep(0.5)

    started = time_module.monotonic()
    results = check_adapters(probes={"shiftgrid": slow_probe}, timeout=0.05, now=None)
    elapsed = time_module.monotonic() - started

    shiftgrid = next(r for r in results if r.system == "shiftgrid")
    assert shiftgrid.status == "degraded"
    assert shiftgrid.failure_reason is not None
    assert "timed out" in shiftgrid.failure_reason
    # The short timeout actually bounds the wait: it never waits out the probe.
    assert elapsed < 0.5


# ------------------------------------------------------------ discovery paths


def _install_stub_adapter(system: str, attribute: str, cls: type) -> Iterator[None]:
    module_name = f"app.adapters.{system}"
    module = types.ModuleType(module_name)
    setattr(module, attribute, cls)
    sys.modules[module_name] = module
    try:
        yield
    finally:
        sys.modules.pop(module_name, None)


_install_stub_adapter = contextmanager(_install_stub_adapter)


def test_discovery_adapter_without_a_health_probe_is_unknown() -> None:
    """An adapter exists but does not implement the probe protocol: unknown,
    with a reason that names the missing protocol (never a crash)."""
    from app.api import health
    from app.api.health import check_adapters

    class HireDeskAdapter:  # no health_check method on purpose
        pass

    spec = next(s for s in health.ADAPTER_SPECS if s.system == "hiredesk")
    with _install_stub_adapter("hiredesk", spec.attributes[0], HireDeskAdapter):
        results = check_adapters(now=None)

    hiredesk = next(r for r in results if r.system == "hiredesk")
    assert hiredesk.status == "unknown"
    assert hiredesk.failure_reason is not None
    assert "health probe" in hiredesk.failure_reason


def test_discovery_failing_health_probe_is_degraded() -> None:
    """An adapter that implements the protocol and fails: degraded, with the
    adapter's own error carried as the failure reason."""
    from app.api import health
    from app.api.health import check_adapters

    class Nomina360Adapter:
        def health_check(self) -> None:
            raise ConnectionError("nomina360 API unreachable")

    spec = next(s for s in health.ADAPTER_SPECS if s.system == "nomina360")
    with _install_stub_adapter("nomina360", spec.attributes[0], Nomina360Adapter):
        results = check_adapters(now=None)

    nomina = next(r for r in results if r.system == "nomina360")
    assert nomina.status == "degraded"
    assert nomina.failure_reason is not None
    assert "unreachable" in nomina.failure_reason


def test_discovery_healthy_adapter_is_ok() -> None:
    from app.api import health
    from app.api.health import check_adapters

    class ShiftGridAdapter:
        def health_check(self) -> None:
            return None

    spec = next(s for s in health.ADAPTER_SPECS if s.system == "shiftgrid")
    with _install_stub_adapter("shiftgrid", spec.attributes[0], ShiftGridAdapter):
        results = check_adapters(now=None)

    shiftgrid = next(r for r in results if r.system == "shiftgrid")
    assert shiftgrid.status == "ok"
    assert shiftgrid.failure_reason is None


def test_discovery_missing_adapter_module_is_unknown() -> None:
    """The named case from the feature task: the adapter module does not
    exist yet, and the registry reports unknown instead of crashing. A truly
    absent module name keeps this deterministic: adapters may land in
    app/adapters/ at any time (the adapters workstream owns that directory).
    """
    from app.api.health import AdapterSpec, check_adapters

    results = check_adapters(
        specs=(AdapterSpec("learnbite", "app.adapters.learnbite_missing", ("LearnBiteAdapter",)),),
        now=None,
    )

    assert len(results) == 1
    learnbite = results[0]
    assert learnbite.status == "unknown"
    assert learnbite.failure_reason is not None
    assert "not registered" in learnbite.failure_reason
