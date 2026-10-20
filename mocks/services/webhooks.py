"""Outbound webhook emission from the mocks to FirstShift.

HireDesk fires "new application" webhooks and LearnBite fires completion
webhooks (design/integration-contracts.md sections 1 and 5). Delivery targets
come from environment variables so tests can point them anywhere; failed
deliveries are recorded, never raised, because the mock must keep serving
even when FirstShift is not running.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HIRESHIFT_WEBHOOK_URL = "FIRSTSHIFT_WEBHOOK_URL"
LEARNBITE_WEBHOOK_URL = "FIRSTSHIFT_LEARNBITE_WEBHOOK_URL"

DEFAULT_HIRESHIFT_TARGET = "http://localhost:8000/webhooks/hiredesk"
DEFAULT_LEARNBITE_TARGET = "http://localhost:8000/webhooks/learnbite"

# Every emission attempt, oldest first: {"target", "payload", "delivered",
# "status_code" | "error"}. Tests assert against this record.
ATTEMPTS: list[dict] = []


def _post_json(target: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        target,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            return {"delivered": True, "status_code": response.status}
    except urllib.error.HTTPError as exc:
        return {"delivered": False, "status_code": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"delivered": False, "error": str(exc)}


def emit(target_env: str, default_target: str, payload: dict) -> dict:
    """POST the payload to the configured target and record the attempt."""

    target = os.environ.get(target_env, default_target)
    result = _post_json(target, payload)
    ATTEMPTS.append({"target": target, "payload": payload, **result})
    return result
