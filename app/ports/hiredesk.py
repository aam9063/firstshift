"""HireDeskPort: the ATS (integration-contracts §1).

FirstShift's own record is authoritative; HireDesk is mirrored for Talent
reporting. Outbound writes go through the outbox and the relay worker (S5);
writes are idempotent on the C-T5 key, and the adapter never retries a
successful write because HireDesk duplicates are the system's own disease
(T-jordi-16). Inbound "new application" webhooks are deduplicated on the
event id either way (delivery semantics unconfirmed, T-hugo).

Failure modes the adapter must handle (specs/06 §1): duplicate webhooks,
out-of-order stage events, a candidate merged in the ATS, and a requisition
closed while the candidate is mid-flow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.ports.errors import PortValidationError


class HireDeskCandidateMergedError(PortValidationError):
    """The ATS merged this candidate's record into another one; the write is
    reconciled manually against the mirror, never silently dropped."""

    def __init__(self, application_id: str, merged_into: str) -> None:
        self.application_id = application_id
        self.merged_into = merged_into
        super().__init__(
            f"application {application_id} merged upstream into {merged_into}"
        )


class HireDeskRequisitionClosedError(PortValidationError):
    """The requisition was closed while the candidate was mid-flow; the
    stage update stops and a human reconciles the mirror."""

    def __init__(self, requisition_id: str) -> None:
        self.requisition_id = requisition_id
        super().__init__(f"requisition {requisition_id} is closed")


class RequisitionCreate(BaseModel):
    restaurant_id: str
    role: str
    target_open_shift_ids: list[str] = []  # ADR-002: mirrors shift reality
    opened_by: str  # human owner on record


class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    restaurant_id: str


class ApplicationCreate(BaseModel):
    candidate_id: str
    restaurant_id: str
    requisition_id: str | None = None


class StageUpdate(BaseModel):
    """Stage write back to HireDesk, linked to a human Decision record (C-L6)."""

    hiredesk_application_id: str
    stage: Literal["screening", "interview", "offer", "hired", "rejected"]
    rejection_reason: str | None = None  # rejections stop disappearing [T-jordi-18]
    decision_id: str


class StageEvent(BaseModel):
    """One recorded stage transition in the HireDesk event stream.

    Events carry a monotonic ``seq`` per application so the adapter can
    reconstruct the real order when the stream arrives out of order.
    """

    seq: int
    stage: str
    rejection_reason: str | None = None
    decision_id: str
    recorded_at: str


class HireDeskPort(Protocol):
    """Contract for the ATS adapter."""

    def create_requisition(
        self, payload: RequisitionCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        """Open a requisition mirroring the shift reality (ADR-002)."""
        ...

    def create_candidate(
        self, payload: CandidateCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        """Mirror a FirstShift candidate into the ATS for Talent reporting."""
        ...

    def create_application(
        self, payload: ApplicationCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        """Create the in-flight application record."""
        ...

    def update_stage(self, payload: StageUpdate) -> None:
        """Mirror a stage change (outbox-relayed, S5)."""
        ...

    def stage_events(self, application_id: str) -> list[StageEvent]:
        """The raw stage event stream (may be out of order upstream)."""
        ...

    def handle_application_webhook(self, event: Mapping[str, Any]) -> dict[str, str]:
        """Deduplicate the "new application" webhook on its event id.

        Returns ``{"status": "applied"}`` or ``{"status": "duplicate"}``.
        """
        ...


__all__ = [
    "ApplicationCreate",
    "CandidateCreate",
    "HireDeskCandidateMergedError",
    "HireDeskPort",
    "HireDeskRequisitionClosedError",
    "RequisitionCreate",
    "StageEvent",
    "StageUpdate",
]
