"""M365 mock (email and calendar through Graph).

Mock API per design/integration-contracts.md section 6: manager calendars,
interview event writes and the People Ops document request email. Manager
calendars are used inconsistently at Lumbre, so the calendar read is best
effort; when it holds no slots the agent proposes slots over WhatsApp.

Fault injection (mocks/faults.py, F12 T1): no_calendar_slots empties the
named manager's calendar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mocks.faults import faults
from mocks.services.seed import SeedData, build_seed

router = APIRouter(prefix="/m365", tags=["m365"])

CALENDAR_TIMEZONE = "Europe/Madrid"
# Fixed, deterministic slot base: Tuesday 2026-04-07 10:00 and 11:00 Madrid.
_SLOT_BASE = datetime(2026, 4, 7, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
_SLOT_LENGTH = timedelta(minutes=30)


class InterviewEvent(BaseModel):
    manager_id: str
    candidate_ref: str
    starts_at: datetime
    location: str


class DocumentRequestEmail(BaseModel):
    to_person_ops: str
    document_types: list[str]
    upload_link: str


class Store:
    """Module-level in-memory store, reset from the seed for tests."""

    def __init__(self) -> None:
        self.calendars: dict[str, list[dict[str, Any]]] = {}
        self.events: list[dict[str, Any]] = []
        self.mail: list[dict[str, Any]] = []
        self._seq = 0

    def reset(self, seed: SeedData) -> None:
        self.calendars = {
            manager.manager_id: _seed_slots() for manager in seed.managers
        }
        self.events = []
        self.mail = []
        self._seq = 0


def _seed_slots() -> list[dict[str, Any]]:
    return [
        {
            "starts_at": (_SLOT_BASE + offset * timedelta(hours=1)).isoformat(),
            "ends_at": (
                _SLOT_BASE + offset * timedelta(hours=1) + _SLOT_LENGTH
            ).isoformat(),
        }
        for offset in range(2)
    ]


store = Store()


@router.get("/calendars/{manager_id}")
def get_calendar(manager_id: str) -> dict[str, Any]:
    if manager_id not in store.calendars:
        raise HTTPException(status_code=404, detail="unknown manager")

    empty = faults.params("m365", "no_calendar_slots")
    if empty.get("manager_id") == manager_id:
        return {"manager_id": manager_id, "timezone": CALENDAR_TIMEZONE, "slots": []}

    return {
        "manager_id": manager_id,
        "timezone": CALENDAR_TIMEZONE,
        "slots": store.calendars[manager_id],
    }


@router.post("/events")
def create_event(payload: InterviewEvent) -> dict[str, Any]:
    if payload.manager_id not in store.calendars:
        raise HTTPException(status_code=404, detail="unknown manager")

    store._seq += 1
    event = {
        "event_id": f"m365-evt-{store._seq:04d}",
        **payload.model_dump(mode="json"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    store.events.append(event)
    return event


@router.post("/mail")
def send_mail(payload: DocumentRequestEmail) -> dict[str, Any]:
    message = {**payload.model_dump(), "sent_at": datetime.now(UTC).isoformat()}
    store.mail.append(message)
    return {"status": "ok"}


@router.post("/reset")
def reset() -> dict[str, str]:
    store.reset(build_seed())
    return {"status": "reset"}
