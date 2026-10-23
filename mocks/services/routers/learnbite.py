"""LearnBite mock (LMS): enrollment API plus completion webhooks.

Mock API per design/integration-contracts.md section 5. The food hygiene
module is the binary gate for food contact on day 1; completion is emitted
to FirstShift as a webhook, deduplicated upstream on the event id.

Fault injection (mocks/faults.py, F12 T1): late_completion_webhook holds the
completion webhook and emits it on the next read of the enrollment,
completion_without_webhook suppresses the webhook entirely (the poll
fallback must catch it), and re_enrollment creates a fresh enrollment on
every call instead of returning the existing one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mocks.faults import faults
from mocks.services import webhooks
from mocks.services.seed import SeedData

router = APIRouter(prefix="/learnbite", tags=["learnbite"])

# Strictly increasing enrollment timestamps: one microsecond per enrollment
# from a fixed base, so re-enrollment ordering is deterministic.
_ENROLLMENT_BASE = datetime(2026, 4, 1, 8, 0, 0, tzinfo=UTC)


class EnrollmentCreate(BaseModel):
    candidate_id: str
    module_key: Literal["food_hygiene"]
    consent_id: str


class FailEnrollment(BaseModel):
    enrollment_id: str


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.enrollments: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self.pending_events: list[dict[str, Any]] = []

    def reset(self, seed: SeedData) -> None:
        self.enrollments = {}
        self._seq = 0
        self.pending_events = []


store = Store()


def _new_enrollment(payload: EnrollmentCreate) -> dict[str, Any]:
    store._seq += 1
    enrolled_at = _ENROLLMENT_BASE + timedelta(microseconds=store._seq)
    enrollment = {
        "learnbite_enrollment_id": f"lb-{store._seq:04d}",
        "candidate_id": payload.candidate_id,
        "module_key": payload.module_key,
        "consent_id": payload.consent_id,
        "status": "enrolled",
        "enrolled_at": enrolled_at.isoformat(),
        "completed_at": None,
    }
    store.enrollments[enrollment["learnbite_enrollment_id"]] = enrollment
    return enrollment


@router.post("/enrollments")
def enroll(payload: EnrollmentCreate) -> dict[str, Any]:
    if not faults.is_active("learnbite", "re_enrollment"):
        for enrollment in store.enrollments.values():
            if (
                enrollment["candidate_id"] == payload.candidate_id
                and enrollment["module_key"] == payload.module_key
            ):
                return enrollment

    return _new_enrollment(payload)


@router.get("/enrollments")
def list_enrollments(
    candidate_id: str | None = None, module_key: str | None = None
) -> list[dict[str, Any]]:
    return [
        enrollment
        for enrollment in store.enrollments.values()
        if (candidate_id is None or enrollment["candidate_id"] == candidate_id)
        and (module_key is None or enrollment["module_key"] == module_key)
    ]


@router.get("/enrollments/{enrollment_id}")
def get_enrollment(enrollment_id: str) -> dict[str, Any]:
    # A late completion webhook is emitted when the enrollment is next read.
    late = faults.is_active("learnbite", "late_completion_webhook")
    if late:
        pending = [
            event
            for event in store.pending_events
            if event["learnbite_enrollment_id"] == enrollment_id
        ]
        for event in pending:
            webhooks.emit(
                webhooks.LEARNBITE_WEBHOOK_URL,
                webhooks.DEFAULT_LEARNBITE_TARGET,
                event,
            )
            store.pending_events.remove(event)
    return _get(enrollment_id)


def _get(enrollment_id: str) -> dict[str, Any]:
    enrollment = store.enrollments.get(enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="enrollment not found")
    return enrollment


@router.post("/enrollments/{enrollment_id}/complete")
def complete(enrollment_id: str) -> dict[str, Any]:
    enrollment = _get(enrollment_id)

    if enrollment["status"] != "completed":
        enrollment["status"] = "completed"
        enrollment["completed_at"] = datetime.now(UTC).isoformat()
        event = {
            "event": "enrollment_completed",
            "event_id": f"lb-evt-{enrollment_id}",
            "learnbite_enrollment_id": enrollment_id,
            "candidate_id": enrollment["candidate_id"],
            "module_key": enrollment["module_key"],
            "completed_at": enrollment["completed_at"],
        }
        if faults.is_active("learnbite", "completion_without_webhook"):
            pass  # the webhook is lost; the poll fallback must catch completion
        elif faults.is_active("learnbite", "late_completion_webhook"):
            store.pending_events.append(event)
        else:
            webhooks.emit(
                webhooks.LEARNBITE_WEBHOOK_URL,
                webhooks.DEFAULT_LEARNBITE_TARGET,
                event,
            )
    return enrollment


@router.post("/internal/fail-enrollment")
def fail_enrollment(payload: FailEnrollment) -> dict[str, Any]:
    """Test helper: mark an enrollment failed so the candidate re-enrolls."""

    enrollment = _get(payload.enrollment_id)
    enrollment["status"] = "failed"
    return enrollment


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(SeedData(restaurants=[], managers=[], open_shifts=[], candidates=[]))
    return {"status": "reset"}
