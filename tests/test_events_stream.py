"""T3 (S4): the SSE event stream, GET /api/events/stream.

specs/04-prototype.md section 2 (event stream) and specs/04b-console.md
section 2: every agent turn, tool call, state transition and integration
write is persisted as a typed event and published on the stream, with
Last-Event-ID reconnect and candidate/type filters.

Stream design (documented in app/api/events_stream.py): the endpoint polls
the persisted events table every 0.5 s (LISTEN/NOTIFY would need a dedicated
connection and the simulator demo does not), heartbeats every 15 s, and the
SSE id is the event's stream position "(occurred_at isoformat)|(event id)",
which is total and stable, so Last-Event-ID reconnect replays exactly the
missed events.

Tests read the stream from a background thread with bounded waits, so a
broken stream fails with a timeout instead of hanging the suite.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from tests.test_sim_common import (
    fresh_sim_engine,
    load_scenario,
    make_sim_client,
)


@pytest.fixture(scope="function")
def sim_engine() -> Iterator[Engine]:
    yield from fresh_sim_engine()


@pytest.fixture()
def sim_client(sim_engine: Engine) -> Iterator[TestClient]:
    yield from make_sim_client(sim_engine)


@pytest.fixture()
def streamed(
    sim_client: TestClient,
) -> Iterator[tuple[queue.Queue[dict[str, Any]], TestClient]]:
    """Open the stream in a background thread; parsed SSE events queue up.

    The returned extra TestClient lets the test act (webhook, simulator) from
    the main thread while the stream is open.
    """
    frames: queue.Queue[dict[str, Any]] = queue.Queue()
    poster = TestClient(sim_client.app)
    with sim_client as stream_client:

        def consume() -> None:
            with stream_client.stream("GET", "/api/events/stream") as response:
                assert response.status_code == 200
                event: dict[str, Any] = {}
                for line in response.iter_lines():
                    if line.startswith(":"):
                        continue
                    if line == "":
                        if event:
                            frames.put(event)
                            event = {}
                        continue
                    field, _, value = line.partition(": ")
                    if field == "id":
                        event["id"] = value
                    elif field == "event":
                        event["type"] = value
                    elif field == "data":
                        event["data"] = json.loads(value)

        thread = threading.Thread(target=consume, daemon=True)
        thread.start()
        yield frames, poster
    thread.join(timeout=5)


def _collect(
    frames: queue.Queue[dict[str, Any]], n: int, timeout: float = 10.0
) -> list[dict[str, Any]]:
    events = []
    for _ in range(n):
        try:
            events.append(frames.get(timeout=timeout))
        except queue.Empty:  # pragma: no cover - failure message aid
            pytest.fail(f"stream produced only {len(events)} of {n} expected events")
    return events


def test_stream_replays_persisted_events(
    sim_client: TestClient, sim_engine: Engine, streamed: tuple[Any, Any]
) -> None:
    frames, poster = streamed
    load_scenario(poster, "D1")

    events = _collect(frames, 3)
    # The webhook's three events share one microsecond, so their stored
    # order is the stable uuid tiebreak; the replayed set is exact.
    assert sorted(event["type"] for event in events) == [
        "message.in",
        "message.out",
        "state.transition",
    ]
    first = events[0]
    assert first["data"]["type"] in {"message.in", "message.out", "state.transition"}
    assert first["data"]["trace_id"].startswith("sim-d1-")
    assert first["id"], "every frame carries an id for Last-Event-ID reconnect"


def test_stream_replays_missed_events_after_last_event_id(
    sim_client: TestClient, sim_engine: Engine
) -> None:
    load_scenario(sim_client, "D1")

    # Full replay first, to capture the cursor of the first event.
    with TestClient(sim_client.app) as replay_client, replay_client.stream(
        "GET", "/api/events/stream"
    ) as response:
        lines = _read_lines(response, 3)
    all_events = _parse_events(lines)
    first_event = all_events[0]

    # A reconnect with that id replays exactly the events after it: the
    # full replay minus everything up to and including the cursor event.
    # The webhook's events share one microsecond, so which one is first is
    # the stable uuid tiebreak; the boundary itself (which events are
    # replayed) is exact in every run.
    with TestClient(sim_client.app) as reconnect, reconnect.stream(
        "GET",
        "/api/events/stream",
        headers={"Last-Event-ID": first_event["id"]},
    ) as response:
        lines = _read_lines(response, len(all_events) - 1)
    missed = _parse_events(lines)
    assert sorted(event["type"] for event in missed) == sorted(
        event["type"] for event in all_events[1:]
    )

    # Sim-generated events carry deterministic microsecond increments, so
    # their replay order is exact: the inbound message precedes the
    # transition it caused.
    load_scenario(sim_client, "D1")
    sim_client.post(
        "/api/sim/messages",
        json={
            "role": "candidate",
            "text": "Sí, doy mi consentimiento",
            "event": "candidate_consents",
            "payload": {"channel": "whatsapp", "language": "es"},
        },
    )
    with TestClient(sim_client.app) as deterministic, deterministic.stream(
        "GET", "/api/events/stream"
    ) as response:
        lines = _read_lines(response, 8)  # 3 + 3 load events, then the consent pair
    events = _parse_events(lines)
    tail = [event["type"] for event in events[-2:]]
    assert tail == ["message.in", "state.transition"]
    assert "consentimiento" in events[-2]["data"]["payload"]["text"]
    assert missed[0]["id"] != first_event["id"]


def test_stream_filters_by_candidate_and_type(
    sim_client: TestClient, sim_engine: Engine
) -> None:
    first_run = load_scenario(sim_client, "D1")
    second_run = load_scenario(sim_client, "D2")

    with TestClient(sim_client.app) as scoped, scoped.stream(
        "GET", "/api/events/stream", params={"candidate_id": first_run["candidate_id"]}
    ) as response:
        lines = _read_lines(response, 3)
    events = _parse_events(lines)
    assert len(events) == 3
    assert all(event["data"]["candidate_id"] == first_run["candidate_id"] for event in events)
    assert all(
        event["data"]["trace_id"] != second_run["trace_id"] for event in events
    )

    with TestClient(sim_client.app) as scoped, scoped.stream(
        "GET", "/api/events/stream", params={"type": "state.transition"}
    ) as response:
        lines = _read_lines(response, 2)
    events = _parse_events(lines)
    assert [event["type"] for event in events] == ["state.transition", "state.transition"]


def test_stream_delivers_new_events_live(
    sim_client: TestClient, sim_engine: Engine, streamed: tuple[Any, Any]
) -> None:
    frames, poster = streamed
    # Drain the (empty) initial replay, then act: the event must arrive live.
    load_scenario(poster, "D1")
    events = _collect(frames, 3)
    # Same-microsecond webhook events arrive in the stable uuid tiebreak
    # order; the set is what the live-delivery guarantee is about.
    assert sorted(event["type"] for event in events) == [
        "message.in",
        "message.out",
        "state.transition",
    ]


# ------------------------------------------------------------------ helpers


def _read_lines(response: Any, count: int) -> list[str]:
    """Read raw lines until `count` complete SSE events (blank-line ended)."""
    lines: list[str] = []
    completed = 0
    for line in response.iter_lines():
        lines.append(line)
        if line == "":
            completed += 1
            if completed >= count:
                break
    assert completed >= count, "stream ended before the expected events arrived"
    return lines


def _parse_events(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    event: dict[str, Any] = {}
    for line in lines:
        if line.startswith(":"):
            continue
        if line == "":
            if event:
                events.append(event)
                event = {}
            continue
        field, _, value = line.partition(": ")
        if field == "id":
            event["id"] = value
        elif field == "event":
            event["type"] = value
        elif field == "data":
            event["data"] = json.loads(value)
    return events
