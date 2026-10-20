"""Celery task wrapper for the outbox relay (production cadence).

Tests call app.outbox.relay.relay_pending directly; this task exists so the
worker container has a runnable entrypoint without Redis in the test path.
"""

from __future__ import annotations

from typing import Any

from app.workers.celery_app import celery_app


@celery_app.task(name="outbox.relay")  # type: ignore[untyped-decorator]
def relay_outbox() -> dict[str, int]:
    """One relay pass over due pending outbox rows."""
    from app.adapters.hiredesk import HireDeskAdapter
    from app.db.base import make_engine
    from app.outbox.relay import relay_pending
    from app.settings import settings

    result = relay_pending(
        make_engine(settings.database_url),
        HireDeskAdapter.from_settings(settings),
    )
    out: dict[str, Any] = {
        "claimed": result.claimed,
        "delivered": result.delivered,
        "retried": result.retried,
        "dead_lettered": result.dead_lettered,
    }
    return out
