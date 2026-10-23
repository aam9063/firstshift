"""F12 T1 (S1): one test per listed failure mode, each starting RED.

Failure modes from specs/06-integration-rollout.md section 1, injected
through the deterministic fault registry in mocks/faults.py (toggled per
test, never ambient). Everything is offline: the mock app runs over an
in-process ASGI transport and Twilio is respx-mocked.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from mocks.faults import faults
from mocks.services.main import app as mocks_app
from mocks.services.webhooks import ATTEMPTS

MOCKS_BASE = "http://mocks.test"
M365_MANAGER = "mgr-r001"


@pytest.fixture()
def mock_client() -> Iterator[TestClient]:
    """The mock app over an in-process transport (no sockets, offline)."""

    ATTEMPTS.clear()  # isolation: webhook emission counts are per test
    with TestClient(mocks_app) as client:
        yield client
    faults.clear()


def _fire_application(
    client: httpx.Client, restaurant_id: str = "R001", requisition_id: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"restaurant_id": restaurant_id}
    if requisition_id:
        body["requisition_id"] = requisition_id
    return client.post("/hiredesk/internal/fire-new-application", json=body).json()


def _nomina_adapter(client: httpx.Client) -> Any:
    from app.adapters.nomina360 import Nomina360Adapter, TokenBucket

    class NoClock:
        def __call__(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            raise AssertionError("token bucket must never sleep in this test")

    bucket = TokenBucket(60, clock=NoClock(), sleep=NoClock.sleep)
    return Nomina360Adapter(MOCKS_BASE, client=client, bucket=bucket)


def _employee_payload(candidate_id: str = "cand_9f31") -> Any:
    from app.ports.nomina360 import EmployeeCreate

    return EmployeeCreate(
        candidate_id=candidate_id,
        first_name="Marta",
        last_name="Ibanez",
        document_refs=["doc_1"],
        contract_ref="contract_77",
        requested_by="people_ops_sofia",
    )


# ---------------------------------------------------------------------------
# HireDesk (ATS)
# ---------------------------------------------------------------------------


def test_hiredesk_duplicate_webhook_delivery_is_deduplicated(
    mock_client: httpx.Client,
) -> None:
    faults.inject("hiredesk", "duplicate_webhook_delivery")
    before = len(ATTEMPTS)
    delivery = _fire_application(mock_client)

    # The mock delivered the same event twice (at-least-once gateway).
    assert delivery["webhook_deliveries"] == 2
    first, second = ATTEMPTS[before], ATTEMPTS[before + 1]
    assert first["payload"]["event_id"] == second["payload"]["event_id"]

    from app.adapters.hiredesk import HireDeskAdapter

    adapter = HireDeskAdapter(MOCKS_BASE, client=mock_client)
    applied = adapter.handle_application_webhook(first["payload"])
    deduped = adapter.handle_application_webhook(second["payload"])

    assert applied["status"] == "applied"
    assert deduped["status"] == "duplicate"


def test_hiredesk_out_of_order_stage_event(mock_client: httpx.Client) -> None:
    application = _fire_application(mock_client)
    app_id = application["application_id"]
    for stage, decision in (("screening", "dec_1"), ("interview", "dec_2")):
        response = mock_client.patch(
            f"/hiredesk/applications/{app_id}/stage",
            json={"stage": stage, "rejection_reason": None, "decision_id": decision},
        )
        assert response.status_code == 200

    faults.inject("hiredesk", "out_of_order_stage_event")

    from app.adapters.hiredesk import HireDeskAdapter

    adapter = HireDeskAdapter(MOCKS_BASE, client=mock_client)
    events = adapter.stage_events(app_id)

    # The mock serves the raw stream out of order (interview before screening).
    assert [e.stage for e in events] == ["interview", "screening"]
    # The adapter must reconstruct the real order by sequence.
    response = mock_client.get(f"/hiredesk/applications/{app_id}")
    assert response.json()["stage"] == adapter.effective_stage(events) == "interview"


def test_hiredesk_candidate_merged_upstream(mock_client: httpx.Client) -> None:
    application = _fire_application(mock_client)
    app_id = application["application_id"]
    faults.inject(
        "hiredesk",
        "candidate_merged",
        application_id=app_id,
        merged_into="hd-app-999999",
    )

    from app.adapters.hiredesk import HireDeskAdapter
    from app.ports.hiredesk import HireDeskCandidateMergedError, StageUpdate

    adapter = HireDeskAdapter(MOCKS_BASE, client=mock_client)
    with pytest.raises(HireDeskCandidateMergedError) as excinfo:
        adapter.update_stage(
            StageUpdate(
                hiredesk_application_id=app_id,
                stage="screening",
                rejection_reason=None,
                decision_id="dec_1",
            )
        )

    assert excinfo.value.merged_into == "hd-app-999999"


def test_hiredesk_requisition_closed_mid_flow(mock_client: httpx.Client) -> None:
    from app.adapters.hiredesk import HireDeskAdapter
    from app.ports.hiredesk import HireDeskRequisitionClosedError, StageUpdate

    requisition = HireDeskAdapter(MOCKS_BASE, client=mock_client).create_requisition(
        {
            "restaurant_id": "R001",
            "role": "kitchen",
            "target_open_shift_ids": [],
            "opened_by": "mgr-r001",
        },
        idempotency_key="fs/hiredesk/create_requisition/r001/req/ob1",
    )
    application = _fire_application(
        mock_client, requisition_id=requisition["requisition_id"]
    )
    faults.inject(
        "hiredesk", "requisition_closed", requisition_id=requisition["requisition_id"]
    )

    adapter = HireDeskAdapter(MOCKS_BASE, client=mock_client)
    with pytest.raises(HireDeskRequisitionClosedError):
        adapter.update_stage(
            StageUpdate(
                hiredesk_application_id=application["application_id"],
                stage="offer",
                rejection_reason=None,
                decision_id="dec_2",
            )
        )


# ---------------------------------------------------------------------------
# Nómina360 (HRIS and payroll)
# ---------------------------------------------------------------------------


def test_nomina360_token_bucket_60_per_minute(mock_client: httpx.Client) -> None:
    """The adapter's client-side bucket serializes bursts so the 60 req/min
    limit is never tested against the gateway (C-T2)."""

    from app.adapters.nomina360 import Nomina360Adapter, TokenBucket

    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0
            self.sleeps: list[float] = []

        def __call__(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    clock = FakeClock()
    bucket = TokenBucket(60, clock=clock, sleep=clock.sleep)
    adapter = Nomina360Adapter(MOCKS_BASE, client=mock_client, bucket=bucket)

    results = [
        adapter.create_employee(
            _employee_payload(f"cand_burst_{i:03d}"),
            idempotency_key=f"fs/nomina360/create_employee/r/cand_burst_{i:03d}/ob_{i}",
        )
        for i in range(61)
    ]

    assert all(r["status"] == "ok" for r in results)
    # The 61st request inside the same minute had to wait one slot.
    assert clock.sleeps == [1.0]


@respx.mock
def test_nomina360_429_maps_to_rate_limited_error() -> None:
    """A throttle signal from the gateway maps to PortRateLimitedError."""

    from app.ports.errors import PortRateLimitedError

    url = f"{MOCKS_BASE}/nomina360/employees"
    respx.post(url).mock(
        return_value=Response(429, headers={"Retry-After": "2"}, text="slow down")
    )
    from app.adapters.nomina360 import Nomina360Adapter, TokenBucket

    class NoClock:
        def __call__(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            pass

    adapter = Nomina360Adapter(
        MOCKS_BASE,
        client=httpx.Client(base_url=MOCKS_BASE, trust_env=False),
        bucket=TokenBucket(60),
    )
    with pytest.raises(PortRateLimitedError):
        adapter.create_employee(
            _employee_payload(), idempotency_key="fs/nomina360/create/r/c/ob"
        )


def test_nomina360_http_200_with_error_body(mock_client: httpx.Client) -> None:
    """The July incident: HTTP 200 wrapping a validation failure must be
    typed, never retried and never recorded as success (C-T3)."""

    from mocks.services.routers import nomina360

    faults.inject(
        "nomina360",
        "error_body_200",
        error_code="NOMINA_GATEWAY_DOWN",
        message="gateway cannot reach the payroll core",
        field_errors=[],
    )
    adapter = _nomina_adapter(mock_client)

    from app.ports.nomina360 import Nomina360ValidationError

    with pytest.raises(Nomina360ValidationError) as excinfo:
        adapter.create_employee(
            _employee_payload(), idempotency_key="fs/nomina360/create/r/cand_9f31/ob_1"
        )

    assert excinfo.value.code == "NOMINA_GATEWAY_DOWN"
    # The write was never recorded as a success anywhere.
    assert nomina360.store.employees == []


def test_nomina360_partial_creation(mock_client: httpx.Client) -> None:
    """The employee exists but the call returned an error body: the typed
    error surfaces, and the idempotent replay then reports success."""

    from mocks.services.routers import nomina360

    faults.inject("nomina360", "partial_creation")
    adapter = _nomina_adapter(mock_client)

    from app.ports.nomina360 import Nomina360ValidationError

    with pytest.raises(Nomina360ValidationError) as excinfo:
        adapter.create_employee(
            _employee_payload(), idempotency_key="fs/nomina360/create/r/cand_9f31/ob_1"
        )
    assert excinfo.value.code == "NOMINA_PARTIAL_CREATION"
    assert len(nomina360.store.employees) == 1, "creation partially succeeded"

    retried = adapter.create_employee(
        _employee_payload(), idempotency_key="fs/nomina360/create/r/cand_9f31/ob_1"
    )
    assert retried["status"] == "ok"
    assert retried["employee_ref"] == "N360-cand_9f31"
    assert len(nomina360.store.employees) == 1, "replay creates no duplicate"


def test_nomina360_nightly_csv_drift_opens_reconciliation_task(
    mock_client: httpx.Client,
) -> None:

    adapter = _nomina_adapter(mock_client)
    created = adapter.create_employee(
        _employee_payload("cand_drift"),
        idempotency_key="fs/nomina360/create/r/cand_drift/ob_9",
    )
    assert created["status"] == "ok"

    # Tonight's CSV is missing the employee even though the API said ok.
    faults.inject("nomina360", "csv_drift", omit_candidate_ids=["cand_drift"])
    snapshot = adapter.fetch_nightly_csv()
    assert all(row.candidate_id != "cand_drift" for row in snapshot.rows)

    from app.adapters.nomina360 import reconcile
    from app.ports.nomina360 import PendingWrite

    report = reconcile(
        snapshot,
        [
            PendingWrite(
                outbox_message_id="ob_9",
                idempotency_key="fs/nomina360/create/r/cand_drift/ob_9",
                candidate_id="cand_drift",
                expected_employee_ref="N360-cand_drift",
            )
        ],
        run_id="run-nightly",
    )

    assert report.downgraded == ["ob_9"]
    assert report.tasks
    task = report.tasks[0]
    assert task.mismatch_type == "missing_in_csv"
    assert task.assigned_to == "people_ops"
    assert task.status == "open"


# ---------------------------------------------------------------------------
# ShiftGrid (workforce management)
# ---------------------------------------------------------------------------


def test_shiftgrid_open_shift_filled_by_manager_optimistic_check(
    mock_client: httpx.Client,
) -> None:
    """The manager fills the open shift while the agent is offering it: the
    adapter re-checks before confirming and raises a typed error."""

    from app.adapters.shiftgrid import ShiftGridAdapter
    from app.ports.shiftgrid import ShiftAssign, ShiftGridShiftFilledError

    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    shift = adapter.list_open_shifts("R001")[0]
    faults.inject(
        "shiftgrid", "shift_filled", shift_id=shift.shiftgrid_shift_id, filled_by=M365_MANAGER
    )

    with pytest.raises(ShiftGridShiftFilledError) as excinfo:
        adapter.assign_shift(
            ShiftAssign(
                shiftgrid_shift_id=shift.shiftgrid_shift_id,
                nomina360_employee_ref="N360-cand_csv",
                or_people_ops_exception_id=None,
            ),
            idempotency_key="fs/shiftgrid/assign/r/s/ob1",
        )

    assert excinfo.value.assigned_to == M365_MANAGER
    optimistic = adapter.get_shift(shift.shiftgrid_shift_id)
    assert optimistic.assigned_to == M365_MANAGER, "optimistic re-check saw the fill"


def test_shiftgrid_rota_published_on_thursdays(mock_client: httpx.Client) -> None:
    """The rota locks until Thursday: next week's rota is only published on
    the Thursday before its Monday (respect the cycle)."""

    from app.adapters.shiftgrid import ShiftGridAdapter

    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    faults.inject("shiftgrid", "thursday_rota", today="2026-03-25")  # Wednesday

    wednesday = adapter.get_rota(week="2026-03-30", today="2026-03-25")
    assert wednesday.published is False

    thursday = adapter.get_rota(week="2026-03-30", today="2026-03-26")  # Thursday
    assert thursday.published is True


def test_shiftgrid_timezone_dst_boundary(mock_client: httpx.Client) -> None:
    """Shift times crossing the DST spring-forward gap are converted with
    the zone's rules (fold=0) and always leave the adapter as aware UTC."""

    from zoneinfo import ZoneInfo

    from app.adapters.shiftgrid import ShiftGridAdapter

    adapter = ShiftGridAdapter(MOCKS_BASE, client=mock_client)
    faults.inject(
        "shiftgrid",
        "dst_boundary",
        timezone="Europe/Madrid",
        shift_id=None,
        force_local_starts_at="2026-03-29T02:30:00",
    )

    shifts = adapter.list_open_shifts("R001")
    assert shifts
    for shift in shifts:
        assert shift.starts_at.tzinfo is UTC
    boundary = shifts[0]
    expected = datetime(2026, 3, 29, 2, 30, tzinfo=ZoneInfo("Europe/Madrid")).astimezone(
        UTC
    )
    assert boundary.starts_at == expected


# ---------------------------------------------------------------------------
# LearnBite (LMS)
# ---------------------------------------------------------------------------


def _enroll(client: httpx.Client, candidate_id: str = "cand_lb") -> str:
    response = client.post(
        "/learnbite/enrollments",
        json={"candidate_id": candidate_id, "module_key": "food_hygiene", "consent_id": "c1"},
    )
    assert response.status_code == 200
    return response.json()["learnbite_enrollment_id"]


def test_learnbite_late_completion_webhook_is_idempotent(
    mock_client: httpx.Client,
) -> None:
    """The completion webhook arrives late, after polling already learned the
    completion: it is deduplicated and changes nothing."""

    enrollment_id = _enroll(mock_client)
    faults.inject("learnbite", "late_completion_webhook")

    response = mock_client.post(f"/learnbite/enrollments/{enrollment_id}/complete")
    assert response.status_code == 200
    assert len(ATTEMPTS) == 0, "the webhook is late, not immediate"

    from app.adapters.learnbite import LearnBiteAdapter

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    polled = adapter.get_enrollment_status(enrollment_id)
    assert polled.status == "completed"
    completed_at = polled.completed_at

    # The delayed emission fires when the enrollment is next read.
    mock_client.get(f"/learnbite/enrollments/{enrollment_id}")
    assert len(ATTEMPTS) == 1, "the late webhook eventually arrives"
    event = ATTEMPTS[-1]["payload"]

    applied = adapter.handle_completion_webhook(event)
    assert applied["status"] == "duplicate"
    again = adapter.get_enrollment_status(enrollment_id)
    assert again.completed_at == completed_at, "late webhook changed nothing"


def test_learnbite_re_enrollment_uses_latest(mock_client: httpx.Client) -> None:
    """A failed module is re-enrolled: LearnBite then holds two enrollments
    and the adapter must resolve the latest one."""

    first = _enroll(mock_client)
    response = mock_client.post(
        "/learnbite/internal/fail-enrollment", json={"enrollment_id": first}
    )
    assert response.status_code == 200

    faults.inject("learnbite", "re_enrollment")
    second = _enroll(mock_client)
    assert second != first, "re-enrollment creates a fresh enrollment"

    from app.adapters.learnbite import LearnBiteAdapter

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    latest = adapter.latest_status_for("cand_lb")

    assert latest.learnbite_enrollment_id == second
    assert latest.status == "enrolled"


def test_learnbite_completion_without_webhook_poll_fallback(
    mock_client: httpx.Client,
) -> None:
    """The webhook never arrives: the poll fallback still sees completion."""

    enrollment_id = _enroll(mock_client)
    faults.inject("learnbite", "completion_without_webhook")

    response = mock_client.post(f"/learnbite/enrollments/{enrollment_id}/complete")
    assert response.status_code == 200
    assert len(ATTEMPTS) == 0, "the webhook was lost and never arrives"

    from app.adapters.learnbite import LearnBiteAdapter

    adapter = LearnBiteAdapter(MOCKS_BASE, client=mock_client)
    status = adapter.get_enrollment_status(enrollment_id)

    assert status.status == "completed"
    assert status.completed_at is not None


# ---------------------------------------------------------------------------
# M365 calendar
# ---------------------------------------------------------------------------


def test_m365_manager_without_calendar_slots_falls_back_to_whatsapp(
    mock_client: httpx.Client,
) -> None:
    """No calendar slots: the agent proposes slots through WhatsApp quick
    replies instead (at most 3, C-O2)."""

    from app.adapters.m365 import M365Adapter, propose_slots_via_whatsapp

    faults.inject("m365", "no_calendar_slots", manager_id=M365_MANAGER)
    adapter = M365Adapter(MOCKS_BASE, client=mock_client)

    calendar = adapter.get_manager_calendar(M365_MANAGER)
    assert calendar.slots == [], "the manager has no calendar slots"

    options = [
        datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
        datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
        datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
        datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    ]
    message = propose_slots_via_whatsapp(
        options,
        recipient_ref="whatsapp:+34600111222",
        candidate_ref="Marta",
        correlation_id="trace-1",
    )

    assert 1 <= len(message.quick_replies) <= 3, "at most 3 buttons (C-O2)"
    assert message.recipient_ref == "whatsapp:+34600111222"
    assert message.correlation_id == "trace-1"
    assert "Marta" in message.body


# ---------------------------------------------------------------------------
# WhatsApp channel (Twilio adapter, respx-mocked)
# ---------------------------------------------------------------------------

MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/ACsub/Messages.json"


def _whatsapp_adapter(now: datetime) -> Any:
    from app.adapters.twilio import TwilioChannelAdapter

    return TwilioChannelAdapter(
        account_sid="ACsub",
        api_key_sid="SKtestkey",
        api_key_secret="testsecret",
        auth_token=None,
        whatsapp_from="whatsapp:+14155238886",
        now=lambda: now,
    )


def _outbound() -> Any:
    from app.ports.messaging import OutboundMessage

    return OutboundMessage(
        recipient_ref="whatsapp:+34600111222",
        body="Hola: soy el asistente virtual de contratacion.",
        quick_replies=[],
        correlation_id="trace-1",
    )


@respx.mock
def test_whatsapp_outside_24h_window_requires_template() -> None:
    """Free-form sends outside the 24h customer service window are refused;
    a pre-approved template is the only way out (spec 06 section 1)."""

    from app.adapters.twilio import TemplateMessage, TwilioChannelWindowClosedError

    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    adapter = _whatsapp_adapter(now)
    respx.post(MESSAGES_URL).mock(return_value=Response(201, json={"sid": "SM1"}))

    with pytest.raises(TwilioChannelWindowClosedError):
        adapter.send_message(_outbound())  # no inbound ever: window closed

    sid = adapter.send_message(
        _outbound(),
        template=TemplateMessage(
            content_sid="HXtemplate1", variables={"1": "Marta"}
        ),
    )
    assert sid == "SM1"
    form = respx.calls.last.request.content.decode()
    assert "ContentSid=HXtemplate1" in form
    assert "Marta" in form


@respx.mock
def test_whatsapp_within_window_sends_free_form() -> None:
    """An inbound message opens the 24h window: free-form is allowed."""

    from app.ports.messaging import InboundMessage

    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    adapter = _whatsapp_adapter(now)
    route = respx.post(MESSAGES_URL).mock(return_value=Response(201, json={"sid": "SM2"}))

    adapter.handle_inbound(
        InboundMessage(
            provider_message_id="SMin1",
            sender_ref="whatsapp:+34600111222",
            body="Hola",
            received_at=now - timedelta(hours=2),
            quick_reply_id=None,
        )
    )

    sid = adapter.send_message(_outbound())

    assert sid == "SM2"
    assert "Body=" in route.calls.last.request.content.decode()
    assert "ContentSid" not in route.calls.last.request.content.decode()


@respx.mock
def test_whatsapp_window_expires_after_24h() -> None:
    """The window closes 24 hours after the last inbound message."""

    from app.adapters.twilio import TwilioChannelWindowClosedError
    from app.ports.messaging import InboundMessage

    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    adapter = _whatsapp_adapter(now)
    respx.post(MESSAGES_URL).mock(return_value=Response(201, json={"sid": "SM3"}))

    adapter.handle_inbound(
        InboundMessage(
            provider_message_id="SMin2",
            sender_ref="whatsapp:+34600111222",
            body="Hola",
            received_at=now - timedelta(hours=25),
            quick_reply_id=None,
        )
    )

    with pytest.raises(TwilioChannelWindowClosedError):
        adapter.send_message(_outbound())


@respx.mock
def test_whatsapp_opt_out_keyword_stops_all_sends() -> None:
    """Opt-out keywords (EN and ES) mark the recipient; sends stop."""

    from app.adapters.twilio import TwilioChannelRejectedError
    from app.ports.messaging import InboundMessage

    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    adapter = _whatsapp_adapter(now)
    route = respx.post(MESSAGES_URL).mock(return_value=Response(201, json={"sid": "SM4"}))

    for keyword in ("STOP", "ALTO", "Baja"):
        adapter.handle_inbound(
            InboundMessage(
                provider_message_id=f"SMin-{keyword}",
                sender_ref="whatsapp:+34600111222",
                body=f"{keyword}",
                received_at=now - timedelta(minutes=1),
                quick_reply_id=None,
            )
        )
        assert adapter.is_opted_out("whatsapp:+34600111222")

    with pytest.raises(TwilioChannelRejectedError):
        adapter.send_message(_outbound())
    assert not route.called, "nothing is sent to an opted-out recipient"


@respx.mock
def test_whatsapp_delivery_and_read_receipts() -> None:
    """Status callbacks update the receipt status per provider message id."""

    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    adapter = _whatsapp_adapter(now)

    adapter.handle_status_callback({"MessageSid": "SMX", "MessageStatus": "delivered"})
    assert adapter.receipt_status("SMX") == "delivered"

    adapter.handle_status_callback({"MessageSid": "SMX", "MessageStatus": "read"})
    assert adapter.receipt_status("SMX") == "read"
    assert adapter.receipt_status("SMY") is None
