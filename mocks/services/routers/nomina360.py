"""Nómina360 mock (HRIS and payroll) with its documented quirks.

The quirk (C-T3, discovery/systems-and-data.md section 2): validation
failures return HTTP 200 with an error body, so a client that checks only
the status code believes the write succeeded while the employee does not
exist. The adapter (not this mock) must validate every response by body.

Also serves the nightly CSV export, the only reliable read path
(design/integration-contracts.md section 2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

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


@router.post("/employees")
def create_employee(payload: EmployeeCreate) -> dict[str, Any]:
    """Employee creation. Validation failures are HTTP 200 error bodies."""

    missing = _validate(payload)
    if missing:
        return {
            "status": "error",
            "error_code": "NOMINA_VALIDATION_FAILED",
            "message": f"validation failed for fields: {', '.join(missing)}",
            "field_errors": missing,
        }

    if any(e["candidate_id"] == payload.candidate_id for e in store.employees):
        return {
            "status": "error",
            "error_code": "NOMINA_DUPLICATE_EMPLOYEE",
            "message": f"employee for candidate {payload.candidate_id} exists",
            "field_errors": ["candidate_id"],
        }

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

    rows = ["employee_ref,candidate_id,first_name,last_name,created_at"]
    for employee in store.employees:
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
