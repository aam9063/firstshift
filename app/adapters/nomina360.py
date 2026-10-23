"""Nómina360 adapter: HRIS and payroll writes with the documented quirks.

Contract: app/ports/nomina360.py Nomina360Port; design/integration-contracts
section 2. Hardened failure modes (specs/06 §1):

- 60 req/min rate limit: enforced by a client-side token bucket (C-T2) so
  the limit is never tested against the gateway; a gateway 429 maps to
  PortRateLimitedError.
- HTTP 200 with an error body (C-T3): every response is validated by body,
  never by status code; validation failures raise Nomina360ValidationError,
  are never retried and never recorded as success.
- Partial creation: the employee exists but the call returned an error body;
  the typed error surfaces and the idempotent replay reports success.
- Nightly CSV reconciliation (O12): ``reconcile`` matches pending writes
  against the CSV (the truth, C-T4), confirms, downgrades and opens
  ReconciliationTasks for People Ops or IT.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from app.ports.errors import (
    PortProtocolError,
    PortRateLimitedError,
    PortTransientError,
)
from app.ports.nomina360 import (
    CsvSnapshot,
    EmployeeCreate,
    EmployeeCsvRow,
    Nomina360Body,
    Nomina360ValidationError,
    PendingWrite,
    ReconciliationReport,
    ReconciliationTask,
)

DEFAULT_REQUESTS_PER_MINUTE = 60
RUNBOOK_COMPENSATION_REF = "runbook.md#nomina360-create-employee"
_RECONCILIATION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "firstshift:reconciliation")


class TokenBucket:
    """Client-side token bucket serializing bursts (registration waves in
    June/July, T-sofia-24) so the gateway limit is never tested.

    Deterministic: the clock and sleeper are injectable, so tests advance
    time without sleeping.
    """

    def __init__(
        self,
        capacity_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if capacity_per_minute < 1:
            raise ValueError("capacity_per_minute must be positive")
        self._capacity = float(capacity_per_minute)
        self._rate_per_second = capacity_per_minute / 60.0
        self._tokens = float(capacity_per_minute)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()

    def acquire(self) -> None:
        """Block until one token is available (drains at capacity/minute)."""

        while True:
            now = self._clock()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_second)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            self._sleep(max(1.0 / self._rate_per_second, 0.001))


def parse_response(http_status: int, body: bytes) -> dict[str, Any]:
    """Validate a Nómina360 response by body, never by status code (C-T3).

    A malformed body is a protocol error; a non-ok body raises
    Nomina360ValidationError; a success body with an odd HTTP status is also
    a protocol error.
    """

    try:
        parsed = Nomina360Body.model_validate_json(body)
    except ValueError as exc:
        raise PortProtocolError(f"nomina360 sent a malformed body: {body[:120]!r}") from exc
    if parsed.status != "ok":
        raise Nomina360ValidationError(
            code=parsed.error_code, fields=parsed.field_errors, message=parsed.message
        )
    if http_status != 200:  # documented code with a success body: still odd
        raise PortProtocolError(f"nomina360 returned {http_status} with a success body")
    return parsed.model_dump()


class Nomina360Adapter:
    """HTTP adapter against the Nómina360 gateway (mock now, real later)."""

    def __init__(
        self,
        base_url: str,
        client: httpx.Client | None = None,
        *,
        bucket: TokenBucket | None = None,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=10.0, trust_env=False
        )
        self._bucket = bucket or TokenBucket(requests_per_minute)

    def create_employee(self, payload: EmployeeCreate, *, idempotency_key: str) -> dict[str, Any]:
        """Idempotent create keyed by the C-T5 scheme (candidate_id is the
        external ref, so a replay returns the same ref, never a duplicate)."""

        self._bucket.acquire()
        try:
            response = self._client.post(
                "/nomina360/employees",
                json=payload.model_dump(),
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"nomina360 unreachable: {exc}") from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "no retry-after")
            raise PortRateLimitedError(f"nomina360 throttled the write: {retry_after}")
        if response.status_code >= 500:
            raise PortTransientError(f"nomina360 transient failure: {response.status_code}")

        try:
            parsed = parse_response(response.status_code, response.content)
        except Nomina360ValidationError as exc:
            if exc.code == "NOMINA_DUPLICATE_EMPLOYEE":
                # Idempotent replay: the employee already exists, report the
                # same ref instead of failing (or creating) again.
                return {
                    "status": "ok",
                    "employee_ref": f"N360-{payload.candidate_id}",
                    "duplicate": True,
                }
            raise
        employee_ref = parsed.get("employee_ref", f"N360-{payload.candidate_id}")
        return {**parsed, "employee_ref": employee_ref}

    def fetch_nightly_csv(self, date: str | None = None) -> CsvSnapshot:
        """Read the nightly export, the only trusted read path (C-T4)."""

        try:
            response = self._client.get(
                "/nomina360/exports/employees.csv", params={"date": date}
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"nomina360 unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise PortTransientError(f"nomina360 csv export failed: {response.status_code}")

        rows: list[EmployeeCsvRow] = []
        lines = [line for line in response.text.splitlines() if line.strip()]
        for line in lines[1:]:  # skip the header
            fields = line.split(",")
            rows.append(
                EmployeeCsvRow(
                    employee_ref=fields[0],
                    candidate_id=fields[1],
                    first_name=fields[2],
                    last_name=fields[3],
                    created_at=fields[4],
                )
            )
        return CsvSnapshot(date=date or "latest", rows=rows)


def reconcile(
    csv: CsvSnapshot,
    pending: Sequence[PendingWrite],
    *,
    run_id: str,
) -> ReconciliationReport:
    """One nightly O12 reconciliation run over the CSV snapshot (C-T4).

    Found writes become csv_confirmed candidates; absent writes are
    downgraded and a ReconciliationTask opens for People Ops (the record fix)
    while IT investigates the gateway. CSV rows with no FirstShift write are
    reported as unexpected_in_csv for People Ops to classify.
    """

    by_candidate = {row.candidate_id: row for row in csv.rows}
    confirmed: list[str] = []
    downgraded: list[str] = []
    tasks: list[ReconciliationTask] = []
    expected_candidates: set[str] = set()

    for write in pending:
        expected_candidates.add(write.candidate_id)
        row = by_candidate.get(write.candidate_id)
        if row is not None and row.employee_ref == write.expected_employee_ref:
            confirmed.append(write.outbox_message_id)
            continue
        downgraded.append(write.outbox_message_id)
        tasks.append(
            ReconciliationTask(
                id=str(
                    uuid.uuid5(
                        _RECONCILIATION_NAMESPACE, f"{run_id}:{write.outbox_message_id}"
                    )
                ),
                reconciliation_run_id=run_id,
                outbox_message_id=write.outbox_message_id,
                mismatch_type="missing_in_csv",
                assigned_to="people_ops",
                compensating_action_ref=RUNBOOK_COMPENSATION_REF,
            )
        )

    unexpected = [
        row.employee_ref for row in csv.rows if row.candidate_id not in expected_candidates
    ]
    return ReconciliationReport(
        run_id=run_id,
        confirmed=confirmed,
        downgraded=downgraded,
        tasks=tasks,
        unexpected_in_csv=unexpected,
    )
