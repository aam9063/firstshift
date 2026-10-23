"""Console API routers (specs/04b-console.md section 2).

`router` combines the read endpoints (app/api/console/read.py) and the
human action endpoints (app/api/console/actions.py). The SSE stream is not
here: GET /api/events/stream already exists in app/api/events_stream.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.console.actions import router as actions_router
from app.api.console.read import router as read_router

router = APIRouter()
router.include_router(read_router)
router.include_router(actions_router)
