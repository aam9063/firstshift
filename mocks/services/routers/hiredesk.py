"""HireDesk mock (ATS): requisitions, candidates, applications, stages.

Mock API per design/integration-contracts.md section 1, plus the test-only
POST /internal/fire-new-application that creates an application and emits the
"new application" webhook to FirstShift (specs/04 section 1, step 3).

Fault injection (mocks/faults.py, F12 T1): duplicate_webhook_delivery emits
the same webhook event twice, out_of_order_stage_event serves the stage event
stream shuffled, candidate_merged and requisition_closed make stage writes
fail with the typed 409 the real gateway would produce.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mocks.faults import faults
from mocks.services import webhooks
from mocks.services.seed import Candidate, SeedData, build_seed

router = APIRouter(prefix="/hiredesk", tags=["hiredesk"])

WEBHOOK_EVENT_NAME = "new_application"


class RequisitionCreate(BaseModel):
    restaurant_id: str
    role: str
    target_open_shift_ids: list[str] = Field(default_factory=list)
    opened_by: str


class ApplicationCreate(BaseModel):
    candidate_id: str
    restaurant_id: str
    requisition_id: str | None = None


class StageUpdate(BaseModel):
    stage: str
    rejection_reason: str | None = None
    decision_id: str


class FireNewApplication(BaseModel):
    restaurant_id: str
    candidate_id: str | None = None
    requisition_id: str | None = None


class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    restaurant_id: str


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.restaurants: set[str] = set()
        self.candidates: list[Candidate] = []
        self.requisitions: list[dict[str, Any]] = []
        self.applications: list[dict[str, Any]] = []
        self._req_seq = 0
        self._app_seq = 0

    def reset(self, seed: SeedData) -> None:
        self.restaurants = {r.restaurant_id for r in seed.restaurants}
        self.candidates = list(seed.candidates)
        self.requisitions = []
        self.applications = []
        self._req_seq = 0
        self._app_seq = 0


store = Store()


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _next_id(prefix: str, seq: int) -> str:
    return f"{prefix}-{seq:06d}"


def _create_candidate(restaurant_id: str) -> Candidate:
    from mocks.services.seed import FIRST_NAMES, LAST_NAMES

    candidate = Candidate(
        candidate_id=f"hdc-live-{uuid4().hex[:10]}",
        first_name=FIRST_NAMES[len(store.applications) % len(FIRST_NAMES)],
        last_name=LAST_NAMES[len(store.applications) % len(LAST_NAMES)],
        phone="+34 600 000 000",
        restaurant_id=restaurant_id,
        stage="new",
        source="qr_poster",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    store.candidates.append(candidate)
    return candidate


@router.get("/candidates")
def list_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": c.candidate_id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "phone": c.phone,
            "restaurant_id": c.restaurant_id,
            "stage": c.stage,
            "source": c.source,
            "created_at": c.created_at.isoformat(),
        }
        for c in store.candidates
    ]


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict[str, Any]:
    for candidate in store.candidates:
        if candidate.candidate_id == candidate_id:
            return {"candidate_id": candidate_id}
    raise HTTPException(status_code=404, detail="candidate not found")


@router.post("/candidates")
def create_candidate(payload: CandidateCreate) -> dict[str, Any]:
    from mocks.services.seed import FIRST_NAMES, LAST_NAMES

    candidate = Candidate(
        candidate_id=f"hdc-live-{uuid4().hex[:10]}",
        first_name=payload.first_name or FIRST_NAMES[0],
        last_name=payload.last_name or LAST_NAMES[0],
        phone=payload.phone,
        restaurant_id=payload.restaurant_id,
        stage="new",
        source="qr_poster",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    store.candidates.append(candidate)
    return {"candidate_id": candidate.candidate_id}


@router.post("/requisitions")
def create_requisition(payload: RequisitionCreate) -> dict[str, Any]:
    if payload.restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    store._req_seq += 1
    requisition = {
        "requisition_id": _next_id("hd-req", store._req_seq),
        **payload.model_dump(),
        "created_at": _utcnow_iso(),
        "closed": False,
    }
    store.requisitions.append(requisition)
    return requisition


@router.get("/requisitions")
def list_requisitions() -> list[dict[str, Any]]:
    return store.requisitions


@router.post("/applications")
def create_application(payload: ApplicationCreate) -> dict[str, Any]:
    store._app_seq += 1
    application = {
        "application_id": _next_id("hd-app", store._app_seq),
        "candidate_id": payload.candidate_id,
        "restaurant_id": payload.restaurant_id,
        "requisition_id": payload.requisition_id,
        "stage": "new",
        "stage_events": [],
        "created_at": _utcnow_iso(),
    }
    store.applications.append(application)
    return application


@router.get("/applications/{application_id}")
def get_application(application_id: str) -> dict[str, Any]:
    for application in store.applications:
        if application["application_id"] == application_id:
            return {
                "application_id": application["application_id"],
                "candidate_id": application["candidate_id"],
                "restaurant_id": application["restaurant_id"],
                "requisition_id": application["requisition_id"],
                "stage": application["stage"],
                "created_at": application["created_at"],
            }
    raise HTTPException(status_code=404, detail="application not found")


@router.patch("/applications/{application_id}/stage")
def update_stage(application_id: str, payload: StageUpdate) -> dict[str, Any]:
    merged = faults.params("hiredesk", "candidate_merged")
    if merged.get("application_id") == application_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "candidate_merged",
                "merged_into": merged.get("merged_into", "unknown"),
            },
        )
    closed = faults.params("hiredesk", "requisition_closed")
    if closed.get("requisition_id"):
        for application in store.applications:
            if (
                application["application_id"] == application_id
                and application["requisition_id"] == closed["requisition_id"]
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "requisition_closed",
                        "requisition_id": closed["requisition_id"],
                    },
                )

    for application in store.applications:
        if application["application_id"] == application_id:
            application["stage"] = payload.stage
            application["rejection_reason"] = payload.rejection_reason
            application["decision_id"] = payload.decision_id
            application["stage_events"].append(
                {
                    "seq": len(application["stage_events"]) + 1,
                    "stage": payload.stage,
                    "rejection_reason": payload.rejection_reason,
                    "decision_id": payload.decision_id,
                    "recorded_at": _utcnow_iso(),
                }
            )
            return application
    raise HTTPException(status_code=404, detail="application not found")


@router.get("/applications/{application_id}/stage-events")
def get_stage_events(application_id: str) -> list[dict[str, Any]]:
    """The raw stage event stream; the upstream gateway may deliver it out
    of order, which the out_of_order_stage_event fault reproduces."""

    for application in store.applications:
        if application["application_id"] == application_id:
            events = list(application["stage_events"])
            if faults.is_active("hiredesk", "out_of_order_stage_event"):
                events.reverse()  # deterministic shuffle: exact reverse order
            return events
    raise HTTPException(status_code=404, detail="application not found")


@router.post("/internal/fire-new-application")
def fire_new_application(payload: FireNewApplication) -> dict[str, Any]:
    """Test helper: create an application and emit the FirstShift webhook."""

    if payload.restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")

    candidate_id = payload.candidate_id or _create_candidate(
        payload.restaurant_id
    ).candidate_id
    store._app_seq += 1
    application_id = _next_id("hd-app", store._app_seq)
    applied_at = datetime.now(UTC).replace(tzinfo=None)
    application = {
        "application_id": application_id,
        "candidate_id": candidate_id,
        "restaurant_id": payload.restaurant_id,
        "requisition_id": payload.requisition_id,
        "stage": "new",
        "stage_events": [],
        "created_at": applied_at.isoformat(),
    }
    store.applications.append(application)

    event = {
        "event": WEBHOOK_EVENT_NAME,
        "event_id": f"hd-evt-{application_id}",
        "application_id": application_id,
        "candidate_id": candidate_id,
        "restaurant_id": payload.restaurant_id,
        "applied_at": applied_at.isoformat(),
    }
    first = webhooks.emit(
        webhooks.HIRESHIFT_WEBHOOK_URL,
        webhooks.DEFAULT_HIRESHIFT_TARGET,
        event,
    )
    deliveries = [first]
    if faults.is_active("hiredesk", "duplicate_webhook_delivery"):
        # The real gateway is at-least-once at best: same event id, twice.
        deliveries.append(
            webhooks.emit(
                webhooks.HIRESHIFT_WEBHOOK_URL,
                webhooks.DEFAULT_HIRESHIFT_TARGET,
                event,
            )
        )
    return {
        **application,
        "stage_events": 0,
        "webhook_deliveries": len(deliveries),
        "webhook_delivery": deliveries[0],
    }


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
