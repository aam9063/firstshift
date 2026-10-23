"""Nomina360Port: HRIS and payroll (integration-contracts section 2).

Employee-creation REST only, no webhooks, on-premise behind a self-maintained
gateway. The documented quirk (C-T3): validation failures return HTTP 200
with an error body, so every response is validated by body, never by status
code. The nightly CSV export is the only trusted read path (C-T4) and feeds
the O12 reconciliation.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.ports.errors import PortValidationError


class Nomina360ValidationError(PortValidationError):
    """The 200-with-error-body quirk, surfaced as a typed error."""

    def __init__(self, code: str | None, fields: list[str], message: str | None) -> None:
        self.code = code
        self.fields = fields
        super().__init__(f"nomina360 rejected the write: {code} {message or ''}".strip())


class EmployeeCreate(BaseModel):
    """The only write FirstShift performs in Nómina360 (C-L9, T-sofia-04).

    Validation errors carry the field names so the human task is actionable.
    """

    candidate_id: str  # becomes the external ref for idempotency
    first_name: str
    last_name: str  # required only here: Nómina360 registration needs it
    document_refs: list[str] = []  # Document.ids; contents never leave storage
    contract_ref: str  # signed by People Ops, referenced not carried
    requested_by: str  # People Ops actor; FirstShift never requests on its own


class Nomina360Body(BaseModel):
    """Schema of every Nómina360 response body, success or error."""

    status: Literal["ok", "error"]
    error_code: str | None = None
    message: str | None = None
    field_errors: list[str] = []


class EmployeeCsvRow(BaseModel):
    """One row of the nightly export: what is in the file is what is in the
    system (C-T4, T-hugo-18)."""

    employee_ref: str
    candidate_id: str
    first_name: str
    last_name: str
    created_at: str


class CsvSnapshot(BaseModel):
    """Parsed nightly CSV snapshot used by the reconciliation job."""

    date: str
    rows: list[EmployeeCsvRow]


class PendingWrite(BaseModel):
    """An outbox write in ``api_confirmed`` awaiting CSV confirmation (O12)."""

    outbox_message_id: str
    idempotency_key: str
    candidate_id: str
    expected_employee_ref: str


class ReconciliationTask(BaseModel):
    """The human work item a drift detection opens (design/data-model.md).

    Record fixes belong to People Ops, gateway investigations to IT; the
    compensating_action_ref points at the runbook entry per write type
    (C-T7). Until the task is resolved, ready_for_rota stays unsignaled.
    """

    id: str
    reconciliation_run_id: str
    outbox_message_id: str
    mismatch_type: Literal["missing_in_csv", "unexpected_in_csv"]
    assigned_to: Literal["people_ops", "it"]
    compensating_action_ref: str
    status: Literal["open", "acknowledged", "resolved"] = "open"


class ReconciliationReport(BaseModel):
    """Outcome of one nightly reconciliation run (O12)."""

    run_id: str
    confirmed: list[str] = []  # outbox message ids now csv_confirmed
    downgraded: list[str] = []  # outbox message ids downgraded from api_confirmed
    tasks: list[ReconciliationTask] = []
    unexpected_in_csv: list[str] = []  # employee refs with no FirstShift write


class Nomina360Port(Protocol):
    """Contract for the HRIS/payroll adapter."""

    def create_employee(self, payload: EmployeeCreate, *, idempotency_key: str) -> dict[str, Any]:
        """Idempotent employee creation keyed by the C-T5 scheme.

        Returns ``{"status": "ok", "employee_ref": ...}``; a replay returns
        the same ref without creating a duplicate. Validation failures raise
        Nomina360ValidationError (never retried, never recorded as success).
        """
        ...

    def fetch_nightly_csv(self, date: str | None = None) -> CsvSnapshot:
        """Read the nightly export, the system's only trusted read path."""
        ...


__all__ = [
    "CsvSnapshot",
    "EmployeeCreate",
    "EmployeeCsvRow",
    "Nomina360Body",
    "Nomina360Port",
    "Nomina360ValidationError",
    "PendingWrite",
    "ReconciliationReport",
    "ReconciliationTask",
]
