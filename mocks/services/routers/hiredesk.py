"""HireDesk mock (ATS): requisitions, candidates, applications, stages.

Mock API per design/integration-contracts.md section 1, plus the test-only
POST /internal/fire-new-application that creates an application and emits the
"new application" webhook to FirstShift (specs/04 section 1, step 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


class StageUpdate(BaseModel):
    stage: str
    rejection_reason: str | None = None
    decision_id: str


class FireNewApplication(BaseModel):
    restaurant_id: str
    candidate_id: str | None = None


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
            return {"candidate_id": candidate.candidate_id}
    raise HTTPException(status_code=404, detail="candidate not found")


@router.post("/requisitions")
def create_requisition(payload: RequisitionCreate) -> dict[str, Any]:
    if payload.restaurant_id not in store.restaurants:
        raise HTTPException(status_code=404, detail="unknown restaurant")
    store._req_seq += 1
    requisition = {
        "requisition_id": _next_id("hd-req", store._req_seq),
        **payload.model_dump(),
        "created_at": _utcnow_iso(),
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
        "stage": "new",
        "created_at": _utcnow_iso(),
    }
    store.applications.append(application)
    return application


@router.patch("/applications/{application_id}/stage")
def update_stage(application_id: str, payload: StageUpdate) -> dict[str, Any]:
    for application in store.applications:
        if application["application_id"] == application_id:
            application["stage"] = payload.stage
            application["rejection_reason"] = payload.rejection_reason
            application["decision_id"] = payload.decision_id
            return application
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
        "stage": "new",
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
    delivery = webhooks.emit(
        webhooks.HIRESHIFT_WEBHOOK_URL,
        webhooks.DEFAULT_HIRESHIFT_TARGET,
        event,
    )
    return {**application, "webhook_delivery": delivery}


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
