"""HireDesk adapter: writes stage updates to the mock (later: real) API.

Contract: app/ports/hiredesk.py HireDeskPort; one write per idempotency
key (C-T5); the mock rejects stage moves with 4xx and the nightly CSV is
the reconciliation truth (ADR-0007, not this adapter's concern).
"""

from __future__ import annotations

import os

import httpx

from app.ports.hiredesk import HireDeskPort, StageUpdate

DEFAULT_MOCKS_BASE_URL = "http://localhost:8010"


class HireDeskAdapter(HireDeskPort):
    """HTTP adapter against the HireDesk (mock) REST surface."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, timeout=10.0)

    @classmethod
    def from_settings(cls, settings: object) -> HireDeskAdapter:
        base_url = os.environ.get("MOCKS_BASE_URL", DEFAULT_MOCKS_BASE_URL)
        return cls(base_url)

    def update_stage(self, payload: StageUpdate) -> None:
        response = self._client.patch(
            f"/hiredesk/applications/{payload.hiredesk_application_id}/stage",
            json=payload.model_dump(exclude={"hiredesk_application_id"}),
        )
        if response.status_code >= 400:
            # The adapter turns any 4xx/5xx into a typed failure; the relay
            # owns retry and dead-letter semantics (C-T5).
            raise RuntimeError(
                f"hiredesk rejected stage update: {response.status_code} {response.text[:200]}"
            )
