"""SSE event stream, GET /api/events/stream (F07, T3; S4).

Every typed event persisted in the events table (app/db/events.py) is
published here the moment it happens; the console's live feed, simulator
timeline and candidate journey all read from this one stream.

Implementation choices (documented per the feature task):

- **Polling, not LISTEN/NOTIFY.** The stream polls the persisted events
  table every 0.5 s (POLL_SECONDS). LISTEN/NOTIFY would need a dedicated
  connection outside SQLAlchemy's pool and a trigger or dual write for
  notifications; the simulator demo does not need sub-second delivery, and
  polling the source of truth can never miss a committed event.
- **Event ids = stream position.** The events table has no sequence column,
  so each frame's id is the event's total stream position:
  ``<occurred_at isoformat>|<event uuid>``. The (occurred_at, id) tuple
  order is total and stable, so Last-Event-ID reconnect replays exactly the
  missed events: neither skipped nor duplicated. The cursor is also accepted
  as the ``last_event_id`` query parameter, because EventSource cannot send
  headers.
- **Heartbeats** every 15 s (HEARTBEAT_SECONDS) as SSE comment lines, so
  proxies keep the connection open and the console can detect liveness.
- **Filters:** ``candidate_id`` and ``type`` (comma-separated EventType
  values) apply to both the initial replay and live events.
- Without a Last-Event-ID, a fresh connection replays the whole persisted
  (filtered) history; demo-scale data keeps this cheap.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.db.events import Event

router = APIRouter(tags=["events"])

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15.0
REPLAY_BATCH = 200

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/api/events/stream")
def event_stream(
    request: Request,
    session: SessionDep,
    candidate_id: UUID | None = None,
    type: str | None = None,
    last_event_id: str | None = Query(default=None),
    # EventSource cannot set headers, so the cursor also arrives as the
    # standard Last-Event-ID header (case-insensitive) or the query param.
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Stream persisted typed events as they happen (SSE)."""
    engine = session.get_bind()
    cursor = last_event_id_header or last_event_id
    types = _parse_types(type)
    generator = _stream(
        engine,
        request,
        cursor=cursor,
        candidate_id=candidate_id,
        types=types,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream(
    engine: Any,
    request: Request,
    *,
    cursor: str | None,
    candidate_id: UUID | None,
    types: tuple[str, ...],
) -> Iterator[str]:
    cursor_row = _parse_cursor(cursor)
    last_output = time.monotonic()
    while True:
        rows = _fetch(engine, cursor_row, candidate_id, types)
        for row in rows:
            yield _format_sse(row)
            cursor_row = (row.occurred_at, row.id)
            last_output = time.monotonic()
        if time.monotonic() - last_output >= HEARTBEAT_SECONDS:
            yield ": ping\n\n"
            last_output = time.monotonic()
        time.sleep(POLL_SECONDS)


def _fetch(
    engine: Any,
    cursor: tuple[datetime, UUID] | None,
    candidate_id: UUID | None,
    types: tuple[str, ...],
) -> list[Event]:
    from sqlalchemy.orm import Session

    statement = select(Event).order_by(Event.occurred_at, Event.id)
    if cursor is not None:
        from sqlalchemy import tuple_

        statement = statement.where(tuple_(Event.occurred_at, Event.id) > cursor)
    if candidate_id is not None:
        statement = statement.where(Event.candidate_id == candidate_id)
    if types:
        statement = statement.where(Event.type.in_(types))
    with Session(engine) as session:
        return list(session.scalars(statement.limit(REPLAY_BATCH)).all())


def _parse_types(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _parse_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    """``<occurred_at isoformat>|<event uuid>``; unparseable means replay all."""
    if not cursor:
        return None
    occurred_raw, _, event_id_raw = cursor.partition("|")
    try:
        return datetime.fromisoformat(occurred_raw), UUID(event_id_raw)
    except ValueError:
        return None


def _format_sse(row: Event) -> str:
    data = {
        "event_id": str(row.id),
        "type": row.type,
        "occurred_at": row.occurred_at.isoformat(),
        "candidate_id": str(row.candidate_id) if row.candidate_id else None,
        "trace_id": row.trace_id,
        "payload": row.payload,
    }
    return (
        f"id: {row.occurred_at.isoformat()}|{row.id}\n"
        f"event: {row.type}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )
