"""M365 adapter: email and calendar, with the WhatsApp slot fallback.

Contract: app/ports/m365.py M365Port; design/integration-contracts section 6.
Manager calendars are used inconsistently, so calendar reads are best effort:
when the manager has no calendar slots (fault mode ``no_calendar_slots`` or
reality), the agent proposes interview slots through WhatsApp quick replies
instead (at most 3, C-O2). ``propose_slots_via_whatsapp`` builds that
fallback message so the conversation code never touches Graph directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from app.ports.errors import PortRateLimitedError, PortTransientError, PortValidationError
from app.ports.m365 import CalendarSlot, DocumentRequestEmail, InterviewEvent, ManagerCalendar
from app.ports.messaging import OutboundMessage

MAX_QUICK_REPLIES = 3  # C-O2: at most 3 quick replies for manager decisions


class M365Adapter:
    """HTTP adapter against the M365 (mock) Graph surface."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=10.0, trust_env=False
        )

    def _raise(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise PortRateLimitedError("m365 throttled the request")
        if response.status_code >= 500:
            raise PortTransientError(f"m365 transient failure: {response.status_code}")
        if response.status_code >= 400:
            raise PortValidationError(
                f"m365 rejected the request: {response.status_code} {response.text[:200]}"
            )

    def get_manager_calendar(self, manager_id: str) -> ManagerCalendar:
        try:
            response = self._client.get(f"/m365/calendars/{manager_id}")
        except httpx.TransportError as exc:
            raise PortTransientError(f"m365 unreachable: {exc}") from exc
        self._raise(response)
        body = response.json()
        return ManagerCalendar(
            manager_id=body["manager_id"],
            timezone=body.get("timezone", "Europe/Madrid"),
            slots=[CalendarSlot.model_validate(slot) for slot in body.get("slots", [])],
        )

    def create_interview_event(self, payload: InterviewEvent) -> dict[str, Any]:
        try:
            response = self._client.post("/m365/events", json=payload.model_dump(mode="json"))
        except httpx.TransportError as exc:
            raise PortTransientError(f"m365 unreachable: {exc}") from exc
        self._raise(response)
        result: dict[str, Any] = response.json()
        return result

    def send_email(self, payload: DocumentRequestEmail) -> None:
        try:
            response = self._client.post("/m365/mail", json=payload.model_dump())
        except httpx.TransportError as exc:
            raise PortTransientError(f"m365 unreachable: {exc}") from exc
        self._raise(response)


def propose_slots_via_whatsapp(
    slot_options: Sequence[datetime],
    *,
    recipient_ref: str,
    candidate_ref: str,
    correlation_id: str,
) -> OutboundMessage:
    """Build the WhatsApp fallback when the manager has no calendar slots.

    The message proposes the first options as one-tap quick replies (at most
    MAX_QUICK_REPLIES, C-O2) in the manager's language (Spanish default).
    """

    if not slot_options:
        raise PortValidationError("no slot options to propose over WhatsApp")
    quick_replies = [
        option.astimezone(UTC).strftime("%d/%m %H:%M") for option in slot_options
    ][:MAX_QUICK_REPLIES]
    body = (
        f"Hola: no hay huecos libres en tu calendario para la entrevista de "
        f"{candidate_ref}. Elige una opcion para proponerla:"
    )
    return OutboundMessage(
        recipient_ref=recipient_ref,
        body=body,
        quick_replies=quick_replies,
        correlation_id=correlation_id,
    )
