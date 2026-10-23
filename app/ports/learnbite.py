"""LearnBitePort: LMS (integration-contracts section 5).

Enrollment API plus completion webhooks. The food hygiene module is the
binary gate for food contact on day 1, never for hiring or an offer
(T-iker-06, C-L8). Completion webhook delivery semantics are unconfirmed, so
the adapter deduplicates on the event id and polling is the fallback when a
webhook never arrives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel


class EnrollmentCreate(BaseModel):
    candidate_id: str
    module_key: Literal["food_hygiene"]
    consent_id: str  # pre-boarding only runs on consented candidates (O5)


class EnrollmentStatus(BaseModel):
    learnbite_enrollment_id: str
    candidate_id: str = ""
    module_key: str = "food_hygiene"
    status: Literal["enrolled", "completed", "failed"]
    enrolled_at: str | None = None
    completed_at: datetime | None = None


class LearnBitePort(Protocol):
    """Contract for the LMS adapter."""

    def enroll(self, payload: EnrollmentCreate, *, idempotency_key: str) -> EnrollmentStatus:
        """Idempotent enrollment keyed by the C-T5 scheme."""
        ...

    def get_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Poll fallback when a completion webhook never arrives (S1)."""
        ...

    def statuses_for(
        self, candidate_id: str, module_key: str = "food_hygiene"
    ) -> list[EnrollmentStatus]:
        """Every enrollment the candidate has for the module (re-enrollment
        creates a fresh record; the latest one is authoritative)."""
        ...

    def latest_status_for(
        self, candidate_id: str, module_key: str = "food_hygiene"
    ) -> EnrollmentStatus:
        """The authoritative status after a re-enrollment."""
        ...


__all__ = ["EnrollmentCreate", "EnrollmentStatus", "LearnBitePort"]
