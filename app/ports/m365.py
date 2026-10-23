"""M365Port: email and calendar through Graph API (integration-contracts §6).

Manager calendars are used inconsistently today, so interview slots come
from the manager's WhatsApp replies first, with calendar reads and writes as
best effort. Calendar conflicts surface as PortValidationError and the agent
re-asks the manager in WhatsApp.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class CalendarSlot(BaseModel):
    """One free slot on a manager's calendar; aware datetime."""

    starts_at: datetime  # aware UTC once through the adapter
    ends_at: datetime


class ManagerCalendar(BaseModel):
    manager_id: str
    timezone: str = "Europe/Madrid"
    slots: list[CalendarSlot] = []


class InterviewEvent(BaseModel):
    manager_id: str
    candidate_ref: str  # first name only; documents never travel here again
    starts_at: datetime
    location: str


class DocumentRequestEmail(BaseModel):
    to_person_ops: str  # the template chase is replaced by the agent (T-sofia-16)
    document_types: list[str]
    upload_link: str  # EU-hosted, candidate-direct


class M365Port(Protocol):
    """Contract for the email and calendar adapter."""

    def get_manager_calendar(self, manager_id: str) -> ManagerCalendar:
        """Read the manager's free slots; an empty list means the WhatsApp
        fallback (propose_slots_via_whatsapp)."""
        ...

    def create_interview_event(self, payload: InterviewEvent) -> dict[str, Any]:
        """Best-effort calendar write; conflicts raise PortValidationError."""
        ...

    def send_email(self, payload: DocumentRequestEmail) -> None:
        """Send the document request email to People Ops."""
        ...


__all__ = [
    "CalendarSlot",
    "DocumentRequestEmail",
    "InterviewEvent",
    "M365Port",
    "ManagerCalendar",
]
