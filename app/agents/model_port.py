"""Model port (F07 T1): the LLM behind an interface, selected by settings.

``build_model`` selects by ``settings.llm_mode`` (env ``LLM_MODE``):

- ``scripted`` (default): ``ScriptedModel`` pops recorded/scripted replies and
  computes deterministic token counts. Every test uses this; nothing here can
  touch a network.
- ``live``: ``StrandsOpenAIModel`` wraps the Strands Agents OpenAI provider
  with ``settings.openai_model`` (default gpt-4.1-mini) and the API key from
  the environment. It is never constructed by tests.

Per S6, every generate call is logged with the model name and token usage;
the runner adds prompt version and measured latency to the same log line.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from pydantic import BaseModel

from app.settings import Settings, settings

logger = structlog.get_logger(__name__)


class ScriptedModelExhausted(RuntimeError):
    """A scripted replay ran past its recorded replies: fail loudly."""


class ModelReply(BaseModel):
    """The structured reply payload plus the token usage of the call."""

    payload: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0


class ModelPort(ABC):
    """The one interface the agent layer knows about the LLM."""

    model_name: str

    @abstractmethod
    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        tools: Sequence[Mapping[str, Any]],
    ) -> ModelReply:
        """Return the structured reply for one model call."""


class ScriptedModel(ModelPort):
    """Offline model: returns the next scripted reply, in order.

    Replies are inline scripts in tests (T4 will load them from recorded
    fixtures). Token counts are deterministic length estimates so tests never
    need a network.
    """

    def __init__(self, replies: list[dict[str, Any]] | None = None) -> None:
        self._replies = list(replies or [])
        self.calls = 0
        self.model_name = "scripted"

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        tools: Sequence[Mapping[str, Any]],
    ) -> ModelReply:
        if not self._replies:
            raise ScriptedModelExhausted(
                f"scripted model exhausted after {self.calls} call(s)"
            )
        payload = self._replies.pop(0)
        self.calls += 1
        input_tokens = sum(len(str(message.get("content", ""))) for message in messages) // 4
        output_tokens = len(json.dumps(payload)) // 4
        return ModelReply(
            payload=payload, input_tokens=input_tokens, output_tokens=output_tokens
        )


class StrandsOpenAIModel(ModelPort):
    """Live model over the Strands Agents OpenAI provider.

    Construction is lazy: the OpenAI client is only built on the first
    ``generate`` call, and the class is only instantiated with
    ``LLM_MODE=live``, so importing this module never opens a connection.
    """

    def __init__(
        self,
        *,
        cfg: Settings | None = None,
        model_id: str | None = None,
        api_key: str | None = None,
    ) -> None:
        config = cfg or settings
        self._model_id = model_id or config.openai_model
        self._api_key = api_key or config.openai_api_key
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required for LLM_MODE=live")
        self.model_name = self._model_id
        self._provider: Any = None

    def _openai_model(self) -> Any:
        if self._provider is None:
            from openai import OpenAI
            from strands.models.openai import OpenAIModel

            self._provider = OpenAIModel(
                client=OpenAI(api_key=self._api_key), model_id=self._model_id
            )
        return self._provider

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        tools: Sequence[Mapping[str, Any]],
    ) -> ModelReply:
        from app.agents.schemas import AgentOutput

        started = time.perf_counter()

        async def _collect() -> Any:
            strands_messages = [
                {"role": message["role"], "content": [{"text": message["content"]}]}
                for message in messages
            ]
            last: Any = None
            async for event in self._openai_model().structured_output(
                AgentOutput, strands_messages
            ):
                last = event
            return last

        last_event = asyncio.run(_collect())
        latency_ms = (time.perf_counter() - started) * 1000
        payload = self._payload_from(last_event)
        usage = self._usage_from(last_event)
        logger.info(
            "model.generate",
            model=self.model_name,
            latency_ms=round(latency_ms, 3),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )
        return ModelReply(payload=payload, **usage)

    @staticmethod
    def _payload_from(event: Any) -> dict[str, Any]:
        """Extract the structured output from the final generator event."""
        if isinstance(event, BaseModel):
            return event.model_dump()
        if isinstance(event, Mapping):
            structured = event.get("structuredOutput", event)
            if isinstance(structured, BaseModel):
                return structured.model_dump()
            if isinstance(structured, Mapping):
                return dict(structured)
        raise RuntimeError(f"unexpected structured_output event: {type(event).__name__}")

    @staticmethod
    def _usage_from(event: Any) -> dict[str, int]:
        """Best-effort token usage; strands reports it in the event metadata."""
        if isinstance(event, Mapping):
            raw = event.get("usage") or {}
            if isinstance(raw, Mapping):
                return {
                    "input_tokens": int(raw.get("inputTokens", 0)),
                    "output_tokens": int(raw.get("outputTokens", 0)),
                }
        return {"input_tokens": 0, "output_tokens": 0}


def build_model(cfg: Settings | None = None) -> ModelPort:
    """Factory: select the model implementation from settings (LLM_MODE)."""
    config = cfg or settings
    if config.llm_mode == "scripted":
        return ScriptedModel()
    if config.llm_mode == "live":
        return StrandsOpenAIModel(cfg=config)
    raise ValueError(f"unknown llm_mode: {config.llm_mode!r}")
