"""Nómina360 mock (HRIS and payroll) with its documented quirks.

The quirk (C-T3, discovery/systems-and-data.md section 2): validation
failures return HTTP 200 with an error body, so a client that checks only
the status code believes the write succeeded while the employee does not
exist. The adapter (not this mock) must validate every response by body.

Also serves the nightly CSV export, the only reliable read path
(design/integration-contracts.md section 2).

Fault injection (mocks/faults.py, F12 T1): throttle_429 answers 429 after
``limit`` requests, error_body_200 wraps a rejection in HTTP 200,
partial_creation creates the employee and still answers the error body, and
csv_drift omits employees from the nightly export.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from mocks.faults import faults
from mocks.services.seed import SeedData

router = APIRouter(prefix="/nomina360", tags=["nomina360"])


class EmployeeCreate(BaseModel):
    candidate_id: str
    first_name: str
    last_name: str
    document_refs: list[str] = []
    contract_ref: str
    requested_by: str


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.employees: list[dict[str, Any]] = []

    def reset(self, seed: SeedData) -> None:
        self.employees = []


store = Store()

REQUIRED_FIELDS = ("candidate_id", "first_name", "last_name", "contract_ref")


def _validate(payload: EmployeeCreate) -> list[str]:
    """Validation rules; any failure produces the 200-with-error-body."""

    values = {
        "candidate_id": payload.candidate_id,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "contract_ref": payload.contract_ref,
    }
    return [
        field
        for field in REQUIRED_FIELDS
        if not values[field] or not values[field].strip()
    ]


def _error_body(error_code: str, message: str, field_errors: list[str]) -> dict[str, Any]:
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "field_errors": field_errors,
    }


@router.post("/employees")
def create_employee(payload: EmployeeCreate, response: Response) -> dict[str, Any]:
    """Employee creation. Validation failures are HTTP 200 error bodies."""

    # Fault: the gateway throttles after ``limit`` requests (429 + Retry-After).
    throttle = faults.params("nomina360", "throttle_429")
    if throttle:
        limit = int(throttle.get("limit", 60))
        seen = int(throttle.get("_seen", 0)) + 1
        throttle["_seen"] = seen  # the registry entry is this fault's state
        if seen > limit:
            response.status_code = 429
            return {"detail": "rate limit exceeded", "retry_after": 1}

    missing = _validate(payload)
    if missing:
        return _error_body(
            "NOMINA_VALIDATION_FAILED",
            f"validation failed for fields: {', '.join(missing)}",
            missing,
        )

    # Fault: the employee exists but the call still answers an error body.
    # One-shot: the partial failure happens on the first attempt only; the
    # idempotent replay then succeeds.
    if faults.is_active("nomina360", "partial_creation"):
        faults.consume("nomina360", "partial_creation")  # one-shot: replay succeeds
        employee_ref = f"N360-{payload.candidate_id}"
        if not any(e["candidate_id"] == payload.candidate_id for e in store.employees):
            store.employees.append(
                {
                    "employee_ref": employee_ref,
                    "candidate_id": payload.candidate_id,
                    "first_name": payload.first_name,
                    "last_name": payload.last_name,
                    "contract_ref": payload.contract_ref,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        return _error_body(
            "NOMINA_PARTIAL_CREATION",
            "employee row created but contract attachment failed; retry the call",
            [],
        )

    if any(e["candidate_id"] == payload.candidate_id for e in store.employees):
        return _error_body(
            "NOMINA_DUPLICATE_EMPLOYEE",
            f"employee for candidate {payload.candidate_id} exists",
            ["candidate_id"],
        )

    # Fault: HTTP 200 wrapping a validation failure for a valid payload.
    error_body = faults.params("nomina360", "error_body_200")
    if error_body:
        return _error_body(
            str(error_body.get("error_code", "NOMINA_API_ERROR")),
            str(error_body.get("message", "gateway error")),
            list(error_body.get("field_errors", [])),
        )

    employee_ref = f"N360-{payload.candidate_id}"
    store.employees.append(
        {
            "employee_ref": employee_ref,
            "candidate_id": payload.candidate_id,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "contract_ref": payload.contract_ref,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return {"status": "ok", "employee_ref": employee_ref}


@router.get("/exports/employees.csv", response_class=PlainTextResponse)
def export_employees_csv(date: str | None = None) -> str:
    """Nightly CSV export; what is in the file is what is in the system."""

    drift = faults.params("nomina360", "csv_drift")
    omit = set(drift.get("omit_candidate_ids", []))
    rows = ["employee_ref,candidate_id,first_name,last_name,created_at"]
    for employee in store.employees:
        if employee["candidate_id"] in omit:
            continue  # drift: the API said ok but the file disagrees
        if date and not employee["created_at"].startswith(date):
            continue
        rows.append(
            "{employee_ref},{candidate_id},{first_name},{last_name},{created_at}"
            .format(**employee)
        )
    return "\n".join(rows) + "\n"


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(SeedData(restaurants=[], managers=[], open_shifts=[], candidates=[]))
    return {"status": "reset"}
