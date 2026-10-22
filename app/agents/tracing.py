"""Langfuse trace hook (S6): one span per agent turn when keys are configured.

Absent LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY the tracer is a no-op: the
Langfuse SDK is never imported and nothing is sent. With keys set, the tracer
opens an ``agent.turn`` span carrying the prompt version, model, measured
latency and token usage, and closes it even when the turn raises.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.settings import Settings, settings


class NullTracer:
    """No-op tracer: yields a plain attributes dict and records nothing."""

    @contextmanager
    def turn(self, metadata: dict[str, Any]) -> Iterator[dict[str, Any]]:
        attrs: dict[str, Any] = {}
        yield attrs


class LangfuseTracer:
    """Wraps one agent turn in a Langfuse span.

    The real Langfuse client is built lazily on the first turn so importing
    and constructing the tracer never opens a connection. Tests inject a fake
    client instead.
    """

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host or settings.langfuse_host
        self._client: Any | None = client

    def _langfuse(self) -> Any:
        if self._client is None:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self._public_key,
                secret_key=self._secret_key,
                host=self._host,
            )
        return self._client

    @contextmanager
    def turn(self, metadata: dict[str, Any]) -> Iterator[dict[str, Any]]:
        client = self._langfuse()
        span = client.span(name="agent.turn", metadata=dict(metadata))
        attrs: dict[str, Any] = {}
        try:
            yield attrs
        finally:
            payload = {**metadata, **attrs}
            payload.setdefault("status", "error")
            span.update(metadata=payload)
            client.flush()


def build_tracer(config: Settings | None = None) -> NullTracer | LangfuseTracer:
    """Select the tracer from settings; absent keys mean a no-op."""
    cfg = config or settings
    if cfg.langfuse_public_key and cfg.langfuse_secret_key:
        return LangfuseTracer(
            public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key,
            host=cfg.langfuse_host,
        )
    return NullTracer()
