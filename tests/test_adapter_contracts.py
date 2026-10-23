"""F12 T1 (S2): contract suites for every port, run against the mock.

Each suite drives the adapter exactly as a client sandbox would: through its
public methods over HTTP, with payloads from design/integration-contracts.md.
The suites are structured so the same assertions can point at a real sandbox
later: replace the in-process transport (``_mock_client``) with an
``httpx.Client(base_url=<sandbox url>)`` and keep every body unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.hiredesk import HireDeskAdapter
from app.adapters.learnbite import LearnBiteAdapter
from app.adapters.m365 import M365Adapter
from app.adapters.nomina360 import Nomina360Adapter, TokenBucket, reconcile
from app.adapters.shiftgrid import ShiftGridAdapter
from app.ports.nomina360 import (
    EmployeeCreate,
    Nomina360ValidationError,
    PendingWrite,
)
from app.ports.shiftgrid import ShiftAssign
from mocks.faults import faults
from mocks.services.main import app as mocks_app
from mocks.services.webhooks import ATTEMPTS

MOCKS_BASE = "http://mocks.test"


@pytest.fixture()
def mock_client() -> Iterator[TestClient]:
    """The mock app over an in-process transport (no sockets, offline)."""

    ATTEMPTS.clear()  # isolation: webhook emission counts are per test
    with TestClient(mocks_app) as client:
        yield client
    faults.clear()


class FakeClock:
    """Deterministic monotonic clock and sleeper for the token bucket."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _bucket(clock: FakeClock | None = None) -> tuple[TokenBucket, FakeClock]:
    clock = clock or FakeClock()
    return TokenBucket(60, clock=clock, sleep=clock.sleep), clock


def _adapter(client: httpx.Client, clock: FakeClock | None = None) -> Nomina360Adapter:
    bucket, _ = _bucket(clock)
    return Nomina360Adapter(MOCKS_BASE, client=client, bucket=bucket)


# ---------------------------------------------------------------------------
# Nomina360Port contract
# ---------------------------------------------------------------------------


def test_nomina360_create_employee_contract(mock_client: httpx.Client) -> None:
    adapter = _adapter(mock_client)
    result = adapter.create_employee(
        EmployeeCreate(
            candidate_id="cand_9f31",
            first_name="Marta",
            last_name="Ibanez",
            document_refs=["doc_1"],
            contract_ref="contract_77",
            requested_by="people_ops_sofia",
        ),
        idempotency_key="fs/nomina360/create_employee/ben-playa/cand_9f31/ob_5c02",
    )

    assert result["status"] == "ok"
    assert result["employee_ref"] == "N360-cand_9f31"


def test_nomina360_create_employee_is_idempotent_on_replay(
    mock_client: httpx.Client,
) -> None:
    """Same idempotency key replayed returns the same ref and creates nothing."""

    from mocks.services.routers import nomina360

    adapter = _adapter(mock_client)
    payload = EmployeeCreate(
        candidate_id="cand_9f31",
        first_name="Marta",
        last_name="Ibanez",
        document_refs=[],
        contract_ref="contract_77",
        requested_by="people_ops_sofia",
    )
    key = "fs/nomina360/create_employee/ben-playa/cand_9f31/ob_5c02"
    first = adapter.create_employee(payload, idempotency_key=key)
    second = adapter.create_employee(payload, idempotency_key=key)

    assert first["employee_ref"] == second["employee_ref"]
    assert len(nomina360.store.employees) == 1


def test_nomina360_rejects_payload_as_typed_validation_error(
    mock_client: httpx.Client,
) -> None:
    """The documented quirk: validation failures are HTTP 200 error bodies.

    The contract is that the adapter validates by body, never by status code
    (C-T3), so a rejected payload surfaces as Nomina360ValidationError.
    """

    adapter = _adapter(mock_client)
    with pytest.raises(Nomina360ValidationError) as excinfo:
        adapter.create_employee(
            EmployeeCreate(
                candidate_id="cand_bad",
                first_name="Marta",
                last_name="",  # required by the Nómina360 registration
                document_refs=[],
                contract_ref="contract_77",
                requested_by="people_ops_sofia",
            ),
            idempotency_key="fs/nomina360/create_employee/ben-playa/cand_bad/ob_1",
        )

    assert excinfo.value.fields == ["last_name"]


def test_nomina360_malformed_body_is_protocol_error(mock_client: httpx.Client) -> None:
    """A body that does not match the documented schema is PortProtocolError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"this is not the documented schema")

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url=MOCKS_BASE, trust_env=False
    )
    adapter = Nomina360Adapter(MOCKS_BASE, client=client)
    from app.ports.errors import PortProtocolError

    with pytest.raises(PortProtocolError):
        adapter.create_employee(
            EmployeeCreate(
                candidate_id="cand_x",
                first_name="Marta",
                last_name="Ibanez",
                document_refs=[],
                contract_ref="c1",
                requested_by="sofia",
            ),
            idempotency_key="fs/nomina360/create_employee/r/cand_x/ob_x",
        )


def test_nomina360_fetch_nightly_csv_contract(mock_client: httpx.Client) -> None:
    adapter = _adapter(mock_client)
    adapter.create_employee(
        EmployeeCreate(
            candidate_id="cand_csv",
            first_name="Nerea",
            last_name="Dominguez",
            document_refs=[],
            contract_ref="contract_9",
            requested_by="people_ops_sofia",
        ),
        idempotency_key="fs/nomina360/create_employee/ben-playa/cand_csv/ob_2",
    )

    snapshot = adapter.fetch_nightly_csv()

    assert snapshot.rows
    row = next(r for r in snapshot.rows if r.candidate_id == "cand_csv")
    assert row.employee_ref == "N360-cand_csv"


def test_nomina360_reconciliation_detects_drift_and_opens_task(
    mock_client: httpx.Client,
) -> None:
    """O12: the CSV is truth; a confirmed write absent from it is downgraded
    and a ReconciliationTask is opened for People Ops."""

    adapter = _adapter(mock_client)
    adapter.create_employee(
        EmployeeCreate(
            candidate_id="cand_drift",
            first_name="Iker",
            last_name="Serrano",
            document_refs=[],
            contract_ref="contract_5",
            requested_by="people_ops_sofia",
        ),
        idempotency_key="fs/nomina360/create_employee/ben-playa/cand_drift/ob_3",
    )
    snapshot = adapter.fetch_nightly_csv()
    # Simulate drift: pretend the nightly file does not contain the write.
    from app.ports.nomina360 import CsvSnapshot, EmployeeCsvRow

    drifted = CsvSnapshot(
        date=snapshot.date,
        rows=[
            EmployeeCsvRow(
                employee_ref="N360-someone_else",
                candidate_id="cand_other",
                first_name="Otro",
                last_name="Empleado",
                created_at="2026-04-01T00:00:00+00:00",
            )
        ],
    )
    pending = [
        PendingWrite(
            outbox_message_id="ob_3",
            idempotency_key="fs/nomina360/create_employee/ben-playa/cand_drift/ob_3",
            candidate_id="cand_drift",
            expected_employee_ref="N360-cand_drift",
        )
    ]

    report = reconcile(drifted, pending, run_id="run-2026-04-01")

    assert report.confirmed == []
    assert report.downgraded == ["ob_3"]
    assert len(report.tasks) == 1
    task = report.tasks[0]
    assert task.mismatch_type == "missing_in_csv"
    assert task.assigned_to == "people_ops"
    assert task.outbox_message_id == "ob_3"
    assert report.unexpected_in_csv == ["N360-someone_else"]


def test_nomina360_reconciliation_confirms_when_csv_matches(
    mock_client: httpx.Client,
) -> None:
    adapter = _adapter(mock_client)
    adapter.create_employee(
        EmployeeCreate(
            candidate_id="cand_ok",
            first_name="Bruno",
            last_name="Ferran",
            document_refs=[],
            contract_ref="contract_6",
            requested_by="people_ops_sofia",
        ),
        idempotency_key="fs/nomina360/create_employee/ben-playa/cand_ok/ob_4",
    )
    snapshot = adapter.fetch_nightly_csv()
    pending = [
        PendingWrite(
            outbox_message_id="ob_4",
            idempotency_key="fs/nomina360/create_employee/ben-playa/cand_ok/ob_4",
            candidate_id="cand_ok",
            expected_employee_ref="N360-cand_ok",
        )
    ]

    report = reconcile(snapshot, pending, run_id="run-2")

    assert report.confirmed == ["ob_4"]
    assert report.downgraded == []
    assert report.tasks == []


# ---------------------------------------------------------------------------
# ShiftGridPort contract
# ---------------------------------------------------------------------------


def test_shiftgrid_list_open_shifts_contract(mock_client: httpx.Client) -> None:
    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)

    shifts = adapter.list_open_shifts("R001")

    assert shifts
    shift = shifts[0]
    assert shift.shiftgrid_shift_id
    assert shift.restaurant_id == "R001"
    assert shift.role in ("kitchen", "till", "foh", "drive_thru")
    assert shift.starts_at.tzinfo is not None, "datetimes are timezone-safe"


def test_shiftgrid_assign_and_idempotent_replay(mock_client: httpx.Client) -> None:
    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    shift_id = adapter.list_open_shifts("R001")[0].shiftgrid_shift_id
    payload = ShiftAssign(
        shiftgrid_shift_id=shift_id,
        nomina360_employee_ref="N360-cand_csv",
        or_people_ops_exception_id=None,
    )

    first = adapter.assign_shift(payload, idempotency_key="fs/shiftgrid/assign/r/s/ob1")
    second = adapter.assign_shift(payload, idempotency_key="fs/shiftgrid/assign/r/s/ob1")

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second.get("idempotent") is True


def test_shiftgrid_get_rota_contract(mock_client: httpx.Client) -> None:
    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    shift_id = adapter.list_open_shifts("R001")[0].shiftgrid_shift_id
    adapter.assign_shift(
        ShiftAssign(
            shiftgrid_shift_id=shift_id,
            nomina360_employee_ref="N360-cand_csv",
            or_people_ops_exception_id=None,
        ),
        idempotency_key="fs/shiftgrid/assign/r/s/ob2",
    )

    rota = adapter.get_rota(week="2026-03-30", today="2026-03-26")

    assert rota.published is True
    assert rota.week == "2026-03-30"
    assert any(a.shiftgrid_shift_id == shift_id for a in rota.assignments)


def test_shiftgrid_release_shift_contract(mock_client: httpx.Client) -> None:
    from app.ports.shiftgrid import ShiftRelease

    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    shift_id = adapter.list_open_shifts("R001")[0].shiftgrid_shift_id
    adapter.assign_shift(
        ShiftAssign(
            shiftgrid_shift_id=shift_id,
            nomina360_employee_ref="N360-cand_csv",
            or_people_ops_exception_id=None,
        ),
        idempotency_key="fs/shiftgrid/assign/r/s/ob3",
    )

    adapter.release_shift(ShiftRelease(shiftgrid_shift_id=shift_id))

    assert adapter.get_shift(shift_id).assigned_to is None


# ---------------------------------------------------------------------------
# LearnBitePort contract
# ---------------------------------------------------------------------------


def test_learnbite_enroll_contract(mock_client: httpx.Client) -> None:
    from app.ports.learnbite import EnrollmentCreate

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    status = adapter.enroll(
        EnrollmentCreate(
            candidate_id="cand_lb", module_key="food_hygiene", consent_id="consent_1"
        ),
        idempotency_key="fs/learnbite/enroll/r/cand_lb/ob1",
    )

    assert status.status == "enrolled"
    assert status.learnbite_enrollment_id


def test_learnbite_enroll_is_idempotent(mock_client: httpx.Client) -> None:
    from app.ports.learnbite import EnrollmentCreate

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    payload = EnrollmentCreate(
        candidate_id="cand_lb", module_key="food_hygiene", consent_id="consent_1"
    )
    first = adapter.enroll(payload, idempotency_key="fs/learnbite/enroll/r/cand_lb/ob2")
    second = adapter.enroll(payload, idempotency_key="fs/learnbite/enroll/r/cand_lb/ob2")

    assert first.learnbite_enrollment_id == second.learnbite_enrollment_id


def test_learnbite_get_status_contract(mock_client: httpx.Client) -> None:
    from app.ports.learnbite import EnrollmentCreate

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    enrolled = adapter.enroll(
        EnrollmentCreate(
            candidate_id="cand_lb", module_key="food_hygiene", consent_id="consent_1"
        ),
        idempotency_key="fs/learnbite/enroll/r/cand_lb/ob3",
    )

    status = adapter.get_enrollment_status(enrolled.learnbite_enrollment_id)

    assert status.status == "enrolled"
    assert status.completed_at is None


def test_learnbite_latest_status_for_contract(mock_client: httpx.Client) -> None:
    from app.ports.learnbite import EnrollmentCreate

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    enrolled = adapter.enroll(
        EnrollmentCreate(
            candidate_id="cand_lb", module_key="food_hygiene", consent_id="consent_1"
        ),
        idempotency_key="fs/learnbite/enroll/r/cand_lb/ob4",
    )

    latest = adapter.latest_status_for("cand_lb")

    assert latest.learnbite_enrollment_id == enrolled.learnbite_enrollment_id
    assert latest.status == "enrolled"


# ---------------------------------------------------------------------------
# M365Port contract
# ---------------------------------------------------------------------------


def test_m365_get_manager_calendar_contract(mock_client: httpx.Client) -> None:
    adapter = M365Adapter(MOCKS_BASE, client=mock_client)

    calendar = adapter.get_manager_calendar("mgr-r001")

    assert calendar.manager_id == "mgr-r001"
    assert calendar.slots
    assert calendar.slots[0].starts_at.tzinfo is not None


def test_m365_create_interview_event_contract(mock_client: httpx.Client) -> None:
    from app.ports.m365 import InterviewEvent

    adapter = M365Adapter(MOCKS_BASE, client=mock_client)
    event = adapter.create_interview_event(
        InterviewEvent(
            manager_id="mgr-r001",
            candidate_ref="Marta",
            starts_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            location="BeniBeach, Paseo maritimo 1",
        )
    )

    assert event["event_id"]


def test_m365_send_email_contract(mock_client: httpx.Client) -> None:
    from app.ports.m365 import DocumentRequestEmail
    from mocks.services.routers import m365

    adapter = M365Adapter(MOCKS_BASE, client=mock_client)
    adapter.send_email(
        DocumentRequestEmail(
            to_person_ops="people_ops@lumbre.example",
            document_types=["ss_number", "bank_iban"],
            upload_link="https://docs.firstshift.eu/u/doc_42",
        )
    )

    assert m365.store.mail
    assert m365.store.mail[-1]["document_types"] == ["ss_number", "bank_iban"]


# ---------------------------------------------------------------------------
# HireDeskPort contract
# ---------------------------------------------------------------------------


def _hiredesk_adapter(client: httpx.Client) -> HireDeskAdapter:
    return HireDeskAdapter(MOCKS_BASE, client=client)


def _make_application(client: httpx.Client) -> dict[str, Any]:
    adapter = _hiredesk_adapter(client)
    requisition = adapter.create_requisition(
        {
            "restaurant_id": "R001",
            "role": "kitchen",
            "target_open_shift_ids": [],
            "opened_by": "mgr-r001",
        },
        idempotency_key="fs/hiredesk/create_requisition/r001/req/ob1",
    )
    application = adapter.create_application(
        {
            "candidate_id": "cand_hd",
            "restaurant_id": "R001",
            "requisition_id": requisition["requisition_id"],
        },
        idempotency_key="fs/hiredesk/create_application/r001/cand_hd/ob2",
    )
    return {"requisition": requisition, "application": application}


def test_hiredesk_create_requisition_contract(mock_client: httpx.Client) -> None:
    created = _make_application(mock_client)

    assert created["requisition"]["requisition_id"].startswith("hd-req")


def test_hiredesk_create_candidate_contract(mock_client: httpx.Client) -> None:
    adapter = _hiredesk_adapter(mock_client)

    candidate = adapter.create_candidate(
        {
            "first_name": "Marta",
            "last_name": "Serrano",
            "phone": "+34 600 111 222",
            "restaurant_id": "R001",
        },
        idempotency_key="fs/hiredesk/create_candidate/r001/cand_hd/ob0",
    )

    assert candidate["candidate_id"]


def test_hiredesk_create_application_contract(mock_client: httpx.Client) -> None:
    created = _make_application(mock_client)

    assert created["application"]["application_id"].startswith("hd-app")


def test_hiredesk_update_stage_contract(mock_client: httpx.Client) -> None:
    from app.ports.hiredesk import StageUpdate

    created = _make_application(mock_client)
    adapter = _hiredesk_adapter(mock_client)

    adapter.update_stage(
        StageUpdate(
            hiredesk_application_id=created["application"]["application_id"],
            stage="screening",
            rejection_reason=None,
            decision_id="dec_1",
        )
    )

    events = adapter.stage_events(created["application"]["application_id"])
    assert events[-1].stage == "screening"
    assert events[-1].decision_id == "dec_1"


def test_hiredesk_webhook_contract_parse_and_dedupe(mock_client: httpx.Client) -> None:
    adapter = _hiredesk_adapter(mock_client)
    event = {
        "event": "new_application",
        "event_id": "hd-evt-test-1",
        "application_id": "hd-app-000001",
        "candidate_id": "cand_hd",
        "restaurant_id": "R001",
        "applied_at": "2026-04-01T10:00:00+00:00",
    }

    first = adapter.handle_application_webhook(event)
    second = adapter.handle_application_webhook(event)

    assert first["status"] == "applied"
    assert second["status"] == "duplicate"
