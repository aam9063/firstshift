"""HireDesk adapter: ATS writes with the documented failure modes handled.

Contract: app/ports/hiredesk.py HireDeskPort; design/integration-contracts
section 1. FirstShift's own record is authoritative (T-jordi-16 to -20), so
every rejection surfaces as a typed error for reconciliation, never a silent
drop. Hardened failure modes (specs/06 §1):

- Duplicate webhooks: ``handle_application_webhook`` deduplicates on the
  event id (the gateway's delivery is at-least-once at best).
- Out-of-order stage events: the raw event stream may arrive shuffled;
  ``effective_stage`` reconstructs the real order by sequence number.
- Candidate merged upstream: a 409 with code ``candidate_merged`` raises
  HireDeskCandidateMergedError carrying the surviving application id.
- Requisition closed mid-flow: a 409 with code ``requisition_closed`` raises
  HireDeskRequisitionClosedError.

The relay owns retry semantics: transport errors and 5xx are transient, 429
is rate limited, other 4xx are validation errors and never retried.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.ports.errors import (
    PortAuthError,
    PortProtocolError,
    PortRateLimitedError,
    PortTransientError,
    PortValidationError,
)
from app.ports.hiredesk import (
    ApplicationCreate,
    CandidateCreate,
    HireDeskCandidateMergedError,
    HireDeskRequisitionClosedError,
    RequisitionCreate,
    StageEvent,
    StageUpdate,
)
from app.settings import Settings


def _error_code(response: httpx.Response) -> str | None:
    """The mock (and the real gateway) put a typed code in the 409 detail."""

    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    if isinstance(detail, dict):
        return str(detail.get("code"))
    return None


class HireDeskAdapter:
    """HTTP adapter against the HireDesk (mock, later real) REST surface."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=10.0, trust_env=False
        )
        self._seen_event_ids: set[str] = set()

    @classmethod
    def from_settings(cls, settings: Settings) -> HireDeskAdapter:
        """Configuration, not code: the mock swaps for the real adapter by
        base URL (architecture rule 2)."""

        return cls(settings.mocks_base_url)

    def _raise(self, response: httpx.Response, application_id: str | None = None) -> None:
        if response.status_code == 429:
            raise PortRateLimitedError("hiredesk throttled the request")
        if response.status_code >= 500:
            raise PortTransientError(f"hiredesk transient failure: {response.status_code}")
        if response.status_code == 401 or response.status_code == 403:
            raise PortAuthError(f"hiredesk rejected the credentials: {response.status_code}")
        if response.status_code < 400:
            return
        code = _error_code(response)
        if code == "candidate_merged" and application_id is not None:
            try:
                merged_into = str(response.json()["detail"]["merged_into"])
            except (ValueError, KeyError):
                merged_into = "unknown"
            raise HireDeskCandidateMergedError(application_id, merged_into)
        if code == "requisition_closed":
            try:
                requisition_id = str(response.json()["detail"]["requisition_id"])
            except (ValueError, KeyError):
                requisition_id = "unknown"
            raise HireDeskRequisitionClosedError(requisition_id)
        raise PortValidationError(
            f"hiredesk rejected the request: {response.status_code} {response.text[:200]}"
        )

    @staticmethod
    def _body(payload: Any) -> dict[str, Any]:
        """Accept the port's pydantic models or plain dicts (the outbox relay
        carries payloads as dicts)."""

        dump = getattr(payload, "model_dump", None)
        return dump() if callable(dump) else dict(payload)

    def _post(self, path: str, payload: Any, idempotency_key: str) -> dict[str, Any]:
        try:
            response = self._client.post(
                path,
                json=self._body(payload),
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"hiredesk unreachable: {exc}") from exc
        self._raise(response)
        if response.status_code != 200:  # documented success code for these writes
            raise PortProtocolError(f"hiredesk returned {response.status_code} on a write")
        result: dict[str, Any] = response.json()
        return result

    def create_requisition(
        self, payload: RequisitionCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        return self._post("/hiredesk/requisitions", payload, idempotency_key)

    def create_candidate(
        self, payload: CandidateCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        return self._post("/hiredesk/candidates", payload, idempotency_key)

    def create_application(
        self, payload: ApplicationCreate, *, idempotency_key: str
    ) -> dict[str, Any]:
        return self._post("/hiredesk/applications", payload, idempotency_key)

    def update_stage(self, payload: StageUpdate) -> None:
        try:
            response = self._client.patch(
                f"/hiredesk/applications/{payload.hiredesk_application_id}/stage",
                json=payload.model_dump(exclude={"hiredesk_application_id"}),
            )
        except httpx.TransportError as exc:
            raise PortTransientError(f"hiredesk unreachable: {exc}") from exc
        self._raise(response, application_id=payload.hiredesk_application_id)

    def stage_events(self, application_id: str) -> list[StageEvent]:
        """The raw stage event stream; order is the upstream's problem."""

        try:
            response = self._client.get(f"/hiredesk/applications/{application_id}/stage-events")
        except httpx.TransportError as exc:
            raise PortTransientError(f"hiredesk unreachable: {exc}") from exc
        self._raise(response)
        return [StageEvent.model_validate(raw) for raw in response.json()]

    def effective_stage(self, events: list[StageEvent]) -> str:
        """Reconstruct the real stage from an out-of-order stream.

        Events carry a monotonic sequence per application; the highest seq
        wins regardless of the order the stream arrived in.
        """

        if not events:
            return "new"
        return max(events, key=lambda event: event.seq).stage

    def handle_application_webhook(self, event: Mapping[str, Any]) -> dict[str, str]:
        """Deduplicate the "new application" webhook on its event id."""

        event_id = str(event.get("event_id", ""))
        if not event_id:
            raise PortValidationError("hiredesk webhook event without event_id")
        if event_id in self._seen_event_ids:
            return {"status": "duplicate"}
        self._seen_event_ids.add(event_id)
        return {"status": "applied"}
