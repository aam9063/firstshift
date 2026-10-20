"""Per-agent structured output schemas (S1).

Every model reply is validated against ``AgentOutput`` before anything feeds
the core; invalid output triggers a re-ask, never a guess (architecture rule
1: deterministic core, LLM at the edge).

G3 (data minimization, protected characteristics): no field in this module
can carry health, family situation, religion, nationality beyond the right to
work, or age beyond the legal minimum-age check. If a candidate volunteers a
protected characteristic, the prompt instructs the agent to omit the value
entirely; the refusal to record it is the required behavior.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Language = Literal["es", "pt", "en"]


class SendMessage(BaseModel):
    """The outbound message body plus the language it is written in (C-O4)."""

    body: str = Field(min_length=1, max_length=600)  # WhatsApp-sized
    language: Language


class ToolCall(BaseModel):
    """One tool the agent wants applied; the dispatcher still enforces G6."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExtractedFacts(BaseModel):
    """Named-use facts only (C-L3): every field maps to a screening or
    consent purpose. There is deliberately no field for any protected
    characteristic."""

    consent_granted: bool | None = None
    language: Language | None = None
    right_to_work: bool | None = None
    minimum_age_confirmed: bool | None = None
    distance_ok: bool | None = None
    transport: str | None = None
    availability: list[str] | None = None
    languages_spoken: list[str] | None = None
    bench_consent: bool | None = None


class AgentOutput(BaseModel):
    """The one schema every agent reply is validated against (S1)."""

    message: SendMessage | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    extracted_facts: ExtractedFacts | None = None
