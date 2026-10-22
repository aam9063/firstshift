"""T1 (S1): Langfuse trace hook, enabled only with keys configured.

Absent LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY the tracer is a no-op and
nothing is imported or sent. With keys set the tracer wraps one span per
agent turn carrying prompt_version, model, latency and tokens (S6). The fake
client keeps these tests offline: no network anywhere.
"""

from typing import Any

import pytest

from app.agents.tracing import LangfuseTracer, NullTracer, build_tracer
from app.settings import Settings


class FakeSpan:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.metadata = dict(metadata)
        self.updates: list[dict[str, Any]] = []

    def update(self, *, metadata: dict[str, Any]) -> None:
        self.updates.append(dict(metadata))


class FakeLangfuse:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []
        self.flushed = 0

    def span(self, *, name: str, metadata: dict[str, Any]) -> FakeSpan:
        span = FakeSpan(name, metadata)
        self.spans.append(span)
        return span

    def flush(self) -> None:
        self.flushed += 1


# ------------------------------------------------------------- no-op path


def test_build_tracer_without_keys_is_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Explicitly absent keys: ambient .env values must not leak into the test.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    tracer = build_tracer(
        Settings(
            llm_mode="scripted",
            langfuse_public_key=None,
            langfuse_secret_key=None,
        )
    )
    assert isinstance(tracer, NullTracer)


def test_null_tracer_turn_is_inert_and_yields_attributes_dict() -> None:
    tracer = NullTracer()
    with tracer.turn({"agent": "recruit"}) as attrs:
        attrs["latency_ms"] = 12.5
    assert attrs == {"latency_ms": 12.5}


# ------------------------------------------------------------ traced path


def test_build_tracer_with_keys_selects_langfuse_tracer() -> None:
    tracer = build_tracer(
        Settings(
            llm_mode="live",
            langfuse_public_key="pk-test",
            langfuse_secret_key="sk-test",
        )
    )
    assert isinstance(tracer, LangfuseTracer)


def test_langfuse_tracer_creates_span_with_turn_metadata() -> None:
    client = FakeLangfuse()
    tracer = LangfuseTracer(
        public_key="pk-test", secret_key="sk-test", client=client
    )

    with tracer.turn({"agent": "recruit", "prompt_version": "v1", "model": "scripted"}) as attrs:
        attrs.update(latency_ms=42.0, tokens={"input": 10, "output": 5}, status="ok")

    assert client.flushed == 1
    span = client.spans[0]
    assert span.name == "agent.turn"
    assert span.metadata["agent"] == "recruit"
    assert span.metadata["prompt_version"] == "v1"
    assert span.metadata["model"] == "scripted"
    assert span.updates[-1]["latency_ms"] == 42.0
    assert span.updates[-1]["tokens"] == {"input": 10, "output": 5}
    assert span.updates[-1]["status"] == "ok"


def test_langfuse_tracer_still_closes_span_when_turn_raises() -> None:
    client = FakeLangfuse()
    tracer = LangfuseTracer(public_key="pk", secret_key="sk", client=client)

    try:
        with tracer.turn({"agent": "pulse"}):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert client.flushed == 1
    assert client.spans[0].updates[-1]["status"] == "error"
