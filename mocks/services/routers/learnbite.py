"""LearnBite mock (LMS): enrollment API plus completion webhooks.

Mock API per design/integration-contracts.md section 5. The food hygiene
module is the binary gate for food contact on day 1; completion is emitted
to FirstShift as a webhook, deduplicated upstream on the event id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mocks.services import webhooks
from mocks.services.seed import SeedData

router = APIRouter(prefix="/learnbite", tags=["learnbite"])


class EnrollmentCreate(BaseModel):
    candidate_id: str
    module_key: Literal["food_hygiene"]
    consent_id: str


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.enrollments: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self, seed: SeedData) -> None:
        self.enrollments = {}
        self._seq = 0


store = Store()


@router.post("/enrollments")
def enroll(payload: EnrollmentCreate) -> dict[str, Any]:
    for enrollment in store.enrollments.values():
        if (
            enrollment["candidate_id"] == payload.candidate_id
            and enrollment["module_key"] == payload.module_key
        ):
            return enrollment

    store._seq += 1
    enrollment = {
        "learnbite_enrollment_id": f"lb-{store._seq:04d}",
        "candidate_id": payload.candidate_id,
        "module_key": payload.module_key,
        "consent_id": payload.consent_id,
        "status": "enrolled",
        "completed_at": None,
    }
    store.enrollments[enrollment["learnbite_enrollment_id"]] = enrollment
    return enrollment


@router.get("/enrollments/{enrollment_id}")
def get_enrollment(enrollment_id: str) -> dict[str, Any]:
    enrollment = store.enrollments.get(enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="enrollment not found")
    return enrollment


@router.post("/enrollments/{enrollment_id}/complete")
def complete(enrollment_id: str) -> dict[str, Any]:
    enrollment = store.enrollments.get(enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="enrollment not found")

    if enrollment["status"] != "completed":
        enrollment["status"] = "completed"
        enrollment["completed_at"] = datetime.now(UTC).isoformat()
        webhooks.emit(
            webhooks.LEARNBITE_WEBHOOK_URL,
            webhooks.DEFAULT_LEARNBITE_TARGET,
            {
                "event": "enrollment_completed",
                "event_id": f"lb-evt-{enrollment_id}",
                "learnbite_enrollment_id": enrollment_id,
                "candidate_id": enrollment["candidate_id"],
                "module_key": enrollment["module_key"],
                "completed_at": enrollment["completed_at"],
            },
        )
    return enrollment


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(SeedData(restaurants=[], managers=[], open_shifts=[], candidates=[]))
    return {"status": "reset"}
