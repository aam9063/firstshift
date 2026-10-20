"""T2 (S2) router smoke tests for the mock services app: specs/04 section 1.2.

One test per client system (HireDesk, Nómina360, ShiftGrid, TillCloud,
LearnBite), the Nómina360 HTTP-200-with-error-body quirk from
discovery/systems-and-data.md section 2, the per-router /reset endpoints, and
one uvicorn boot check through TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from mocks.services.main import app
from mocks.services.routers import hiredesk
from mocks.services.webhooks import ATTEMPTS


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_boot_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mocks"}


def test_hiredesk_smoke_fire_new_application(client: TestClient) -> None:
    seeded = client.get("/hiredesk/candidates")
    assert seeded.status_code == 200
    assert len(seeded.json()) == 200

    before = len(ATTEMPTS)
    response = client.post(
        "/hiredesk/internal/fire-new-application",
        json={"restaurant_id": "R001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["application_id"]
    assert body["candidate_id"]
    assert len(ATTEMPTS) == before + 1
    attempt = ATTEMPTS[-1]
    assert attempt["payload"]["application_id"] == body["application_id"]
    assert attempt["payload"]["event"] == "new_application"


def test_hiredesk_stage_update(client: TestClient) -> None:
    created = client.post(
        "/hiredesk/internal/fire-new-application",
        json={"restaurant_id": "R001"},
    ).json()

    response = client.patch(
        f"/hiredesk/applications/{created['application_id']}/stage",
        json={
            "stage": "screening",
            "rejection_reason": None,
            "decision_id": "dec_1",
        },
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "screening"


def test_hiredesk_requisitions(client: TestClient) -> None:
    response = client.post(
        "/hiredesk/requisitions",
        json={
            "restaurant_id": "R001",
            "role": "kitchen",
            "target_open_shift_ids": ["sg-r001-x"],
            "opened_by": "mgr-r001",
        },
    )

    assert response.status_code == 200
    requisition = response.json()
    assert requisition["restaurant_id"] == "R001"
    assert client.get("/hiredesk/requisitions").status_code == 200


def test_nomina360_quirk_validation_failure_is_http_200_error_body(
    client: TestClient,
) -> None:
    response = client.post(
        "/nomina360/employees",
        json={
            "candidate_id": "cand_quirk",
            "first_name": "Nerea",
            "last_name": "",
            "document_refs": [],
            "contract_ref": "",
            "requested_by": "people_ops",
        },
    )

    # The quirk (C-T3): validation failures come back as HTTP 200 with an
    # error body, so a client that checks only the status code is fooled.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"]
    assert body["field_errors"]


def test_nomina360_smoke_create_and_nightly_csv(client: TestClient) -> None:
    response = client.post(
        "/nomina360/employees",
        json={
            "candidate_id": "cand_ok_1",
            "first_name": "Diego",
            "last_name": "Ferrán",
            "document_refs": ["doc_1"],
            "contract_ref": "contract_1",
            "requested_by": "people_ops",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "employee_ref": "N360-cand_ok_1"}

    duplicate = client.post(
        "/nomina360/employees",
        json={
            "candidate_id": "cand_ok_1",
            "first_name": "Diego",
            "last_name": "Ferrán",
            "document_refs": ["doc_1"],
            "contract_ref": "contract_1",
            "requested_by": "people_ops",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "error"

    export = client.get("/nomina360/exports/employees.csv")
    assert export.status_code == 200
    assert "employee_ref,candidate_id,first_name,last_name" in export.text
    assert "N360-cand_ok_1" in export.text


def test_shiftgrid_smoke_open_shifts_and_assign(client: TestClient) -> None:
    shifts = client.get("/shiftgrid/restaurants/R001/open-shifts")
    assert shifts.status_code == 200
    open_shifts = shifts.json()
    assert open_shifts
    assert {"shiftgrid_shift_id", "restaurant_id", "starts_at", "ends_at", "role"} <= (
        open_shifts[0].keys()
    )

    shift_id = open_shifts[0]["shiftgrid_shift_id"]
    assign = client.post(
        f"/shiftgrid/shifts/{shift_id}/assign",
        json={"nomina360_employee_ref": "N360-cand_ok_1"},
    )
    assert assign.status_code == 200

    again = client.post(
        f"/shiftgrid/shifts/{shift_id}/assign",
        json={"nomina360_employee_ref": "N360-cand_ok_1"},
    )
    assert again.status_code == 200, "assign is idempotent on retry"

    conflict = client.post(
        f"/shiftgrid/shifts/{shift_id}/assign",
        json={"nomina360_employee_ref": "N360-someone_else"},
    )
    assert conflict.status_code == 409

    assert client.get("/shiftgrid/rotas").status_code == 200

    unknown = client.get("/shiftgrid/restaurants/R999/open-shifts")
    assert unknown.status_code == 404


def test_tillcloud_smoke_read_only_sales_and_forecast(
    client: TestClient,
) -> None:
    sales = client.get(
        "/tillcloud/restaurants/R001/sales",
        params={"date": "2025-07-04", "granularity": "15m"},
    )
    assert sales.status_code == 200
    body = sales.json()
    assert body["restaurant_id"] == "R001"
    assert body["slices"]
    assert "sales_eur" in body["slices"][0]

    forecast = client.get("/tillcloud/restaurants/R001/forecast")
    assert forecast.status_code == 200
    assert forecast.json()["restaurant_id"] == "R001"


def test_learnbite_smoke_enroll_complete_webhook(client: TestClient) -> None:
    enroll = client.post(
        "/learnbite/enrollments",
        json={
            "candidate_id": "cand_ok_1",
            "module_key": "food_hygiene",
            "consent_id": "consent_1",
        },
    )
    assert enroll.status_code == 200
    enrollment_id = enroll.json()["learnbite_enrollment_id"]
    assert enroll.json()["status"] == "enrolled"

    before = len(ATTEMPTS)
    complete = client.post(f"/learnbite/enrollments/{enrollment_id}/complete")
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["completed_at"]
    assert len(ATTEMPTS) == before + 1
    assert ATTEMPTS[-1]["payload"]["event"] == "enrollment_completed"

    status = client.get(f"/learnbite/enrollments/{enrollment_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    missing = client.get("/learnbite/enrollments/lb-unknown")
    assert missing.status_code == 404


def test_reset_endpoints_restore_seeded_state(client: TestClient) -> None:
    client.post(
        "/hiredesk/internal/fire-new-application",
        json={"restaurant_id": "R001"},
    )

    assert client.post("/hiredesk/reset").status_code == 200
    assert len(hiredesk.store.applications) == 0
    assert len(client.get("/hiredesk/candidates").json()) == 200

    for prefix in ("nomina360", "shiftgrid", "tillcloud", "learnbite"):
        assert client.post(f"/{prefix}/reset").status_code == 200
