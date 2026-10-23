"""LearnBite adapter: LMS enrollment with poll fallback and event dedup.

Contract: app/ports/learnbite.py LearnBitePort; design/integration-contracts
section 5. Hardened failure modes (specs/06 §1):

- Late completion webhooks: ``handle_completion_webhook`` deduplicates on
  the event id and ignores completions already known, so a late delivery
  changes nothing.
- Re-enrollment: LearnBite holds several enrollments per candidate after a
  failed module; ``latest_status_for`` resolves the authoritative one.
- Completion without webhook: ``get_enrollment_status`` polls the enrollment
  API, the fallback when the webhook never arrives.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.ports.errors import PortRateLimitedError, PortTransientError, PortValidationError
from app.ports.learnbite import EnrollmentCreate, EnrollmentStatus


class LearnBiteAdapter:
    """HTTP adapter against the LearnBite (mock) REST surface."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=10.0, trust_env=False
        )
        self._seen_event_ids: set[str] = set()
        self._completions_known: set[str] = set()

    def _raise(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise PortRateLimitedError("learnbite throttled the request")
        if response.status_code >= 500:
            raise PortTransientError(f"learnbite transient failure: {response.status_code}")
        if response.status_code >= 400:
            raise PortValidationError(
                f"learnbite rejected the request: {response.status_code} {response.text[:200]}"
            )

    def _status_from(self, raw: dict[str, Any]) -> EnrollmentStatus:
        return EnrollmentStatus.model_validate(raw)

    def enroll(self, payload: EnrollmentCreate, *, idempotency_key: str) -> EnrollmentStatus:
        try:
            response = self._client.post(
                "/learnbite/enrollments",
                json=payload.model_dump(),
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"learnbite unreachable: {exc}") from exc
        self._raise(response)
        return self._status_from(response.json())

    def get_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Poll fallback: the authoritative read when a webhook never arrives."""

        try:
            response = self._client.get(f"/learnbite/enrollments/{enrollment_id}")
        except httpx.TransportError as exc:
            raise PortTransientError(f"learnbite unreachable: {exc}") from exc
        self._raise(response)
        status = self._status_from(response.json())
        if status.status == "completed":
            # The poll fallback learned the completion: a late webhook for the
            # same enrollment must not re-apply it.
            self._completions_known.add(status.learnbite_enrollment_id)
        return status

    def statuses_for(
        self, candidate_id: str, module_key: str = "food_hygiene"
    ) -> list[EnrollmentStatus]:
        try:
            response = self._client.get(
                "/learnbite/enrollments",
                params={"candidate_id": candidate_id, "module_key": module_key},
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"learnbite unreachable: {exc}") from exc
        self._raise(response)
        return [self._status_from(raw) for raw in response.json()]

    def latest_status_for(
        self, candidate_id: str, module_key: str = "food_hygiene"
    ) -> EnrollmentStatus:
        """Resolve the authoritative enrollment after a re-enrollment.

        LearnBite creates a fresh enrollment per attempt, so ordering by the
        enrollment timestamp picks the latest attempt's status.
        """

        statuses = self.statuses_for(candidate_id, module_key)
        if not statuses:
            raise PortValidationError(f"no learnbite enrollment for {candidate_id}")

        def sort_key(status: EnrollmentStatus) -> tuple[str, str]:
            return (status.enrolled_at or "", status.learnbite_enrollment_id)

        return max(statuses, key=sort_key)

    def handle_completion_webhook(self, event: Mapping[str, Any]) -> dict[str, str]:
        """Deduplicate a completion webhook on its event id.

        Returns ``{"status": "applied"}`` on first sight or
        ``{"status": "duplicate"}`` when the event was already applied
        (at-least-once delivery must not re-complete or double count).
        """

        event_id = str(event.get("event_id", ""))
        if not event_id:
            raise PortValidationError("learnbite completion event without event_id")
        enrollment_id = str(event.get("learnbite_enrollment_id", ""))
        if event_id in self._seen_event_ids or (
            enrollment_id and enrollment_id in self._completions_known
        ):
            return {"status": "duplicate"}
        self._seen_event_ids.add(event_id)
        return {"status": "applied"}
