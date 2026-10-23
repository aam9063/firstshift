"""Response models for the console API (S1).

Every model mirrors one TypeScript interface from web/src/api/types.ts
(read-only, owned by the console session) one to one: field names serialize
as camelCase aliases, enums are Literal types with the exact contract
strings. The candidates list row is derived from the contract file because
the console's candidates feature does not exist yet (open question in
odd/tasks/console-api.md); any field the backend cannot fill yet is an
explicit empty value, never fabricated data.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Serializes every field with its camelCase contract alias."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ActorType / senderType
ActorType = Literal["agent", "candidate", "human", "system"]
SenderType = ActorType | Literal["candidate"]  # candidate is already an ActorType
MetricStatus = Literal["on_target", "below_target"]
AttentionKind = Literal["sla_breach", "first_shift", "human_needed", "dlq", "eval"]
JourneyStateId = Literal[
    "new", "contacted", "consent", "screening", "matched", "interview_booked"
]
RecordStatus = Literal["ok", "pending", "not_requested"]
Cohort = Literal["pilot", "control"]
SlaRisk = Literal["ok", "at_risk", "breached"]


class CandidateListItem(CamelModel):
    id: str
    first_name: str
    initials: str
    state: str
    state_label: str
    restaurant: str
    restaurant_code: str
    cohort: Cohort
    languages: list[str]
    agent_version: str  # "" until the LLM agent loop lands (scripted backend)
    agent_in_control: bool
    sla_risk: SlaRisk
    last_activity_at: str  # ISO timestamp, "" when nothing is recorded yet
    matched_shift_label: str  # "" when no shift is matched
    phone_masked: str
    elapsed_label: str


class CandidateListResponse(CamelModel):
    items: list[CandidateListItem]
    total: int
    page: int
    page_size: int


class JourneyStep(CamelModel):
    id: JourneyStateId
    label: str
    at: str
    actor_label: str
    actor_type: ActorType
    note: str | None = None
    current: bool = False


class ToolCallMarker(CamelModel):
    tool: str
    args_summary: str
    latency_ms: float | None = None
    result_summary: str | None = None


class ThreadMessage(CamelModel):
    id: str
    at: str
    sender_type: SenderType
    sender_label: str | None = None
    agent_version: str | None = None
    text: str
    tool_calls: list[ToolCallMarker] = Field(default_factory=list)


class MatchedShift(CamelModel):
    label: str
    restaurant: str
    detail: str
    shift_ids: list[str]
    held: str  # "" : shift holds are not tracked by the backend yet


class RecordRow(CamelModel):
    label: str
    value: str
    status: RecordStatus | None = None


class IntegrationWrite(CamelModel):
    id: str
    status_code: int  # 0 when the write has no confirmed HTTP outcome yet
    target: str
    operation: str
    idempotency_key: str


class CandidateDetail(CamelModel):
    id: str
    first_name: str
    last_name: str  # "" : FirstShift stores no surname (data minimization)
    initials: str
    state_label: str
    restaurant: str
    languages: list[str]
    agent_version: str
    agent_in_control: bool
    elapsed_label: str
    phone_masked: str
    journey: list[JourneyStep]
    candidate_thread: list[ThreadMessage]
    manager_thread: list[ThreadMessage]
    matched_shift: MatchedShift
    summary_rows: list[RecordRow]
    summary_note: str
    consent_row: RecordRow
    pre_boarding: list[RecordRow]
    writes: list[IntegrationWrite]


class RestaurantRow(CamelModel):
    id: str
    code: str
    name: str
    city: str
    cohort: Cohort
    open_shifts: int
    covered_pct: float
    bench: int
    open_candidates: int
    manager_median_reply: str  # "" when no manager decision is recorded
    paused: bool


class ShiftRow(CamelModel):
    id: str
    label: str
    starts_at: str
    ends_at: str
    role: str
    requires_food_hygiene: bool
    status: str
    matched_candidate_id: str | None
    matched_candidate_name: str | None


class RestaurantShiftsResponse(CamelModel):
    restaurant: RestaurantRow
    shifts: list[ShiftRow]


class FunnelStage(CamelModel):
    id: str
    label: str
    pilot_pct: float
    control_pct: float


class FunnelSummary(CamelModel):
    pilot_candidates: int
    control_candidates: int
    stages: list[FunnelStage]
    insight: str


class KpiCard(CamelModel):
    id: str
    label: str
    value: str  # "" when the metric has no observed data yet
    unit: str
    status: MetricStatus
    control: str  # "" when the control arm has no data
    baseline: str  # "" when the metric tree records no baseline
    target: str
    source: str
    trend: list[float]  # empty when there is no multi-day history


class AttentionItem(CamelModel):
    id: str
    kind: AttentionKind
    title: str
    detail: str
    ago: str


class AuditRow(CamelModel):
    id: str
    at: str
    actor_type: ActorType
    actor_label: str
    event_type: str
    state_from: str | None
    state_to: str | None
    summary: str
    payload: dict[str, Any]


class AuditResponse(CamelModel):
    items: list[AuditRow]
    total: int
    limit: int
    offset: int


class EvalSummaryRow(CamelModel):
    version: str
    label: str
    generated_at: str
    task_success_rate: float | None
    cost_per_hire_usd: float | None


class TakeoverResponse(CamelModel):
    candidate_id: str
    agent_in_control: bool
    taken_over_by: str


class ReleaseResponse(CamelModel):
    candidate_id: str
    agent_in_control: bool
    released_by: str


class HumanMessageBody(CamelModel):
    text: str = Field(min_length=1)


class MessageResponse(CamelModel):
    id: str
    candidate_id: str
    sender_type: SenderType
    text: str
    at: str


class PauseBody(CamelModel):
    resume: bool = False


class PauseResponse(CamelModel):
    restaurant_id: str
    code: str
    paused: bool


class ReplayResponse(CamelModel):
    id: str
    status: str
    attempts: int


class ErasureBody(CamelModel):
    candidate_id: UUID
    reason: str | None = None


class ErasureResponse(CamelModel):
    id: str
    candidate_id: str
    status: str
    requested_at: str


class ActivityItem(CamelModel):
    id: str
    at: str
    actor_type: ActorType
    actor_label: str
    event_type: str
    summary: str
    detail_tag: str | None = None  # short chip label, omitted when none


class CoverageRow(CamelModel):
    id: str
    restaurant: str
    cohort: Cohort
    open_shifts: int
    covered_pct: float
    bench: int
    manager_reply: str  # "" when no manager decision is recorded


class OverviewResponse(CamelModel):
    sim_clock: str  # "" when no simulator run is loaded
    pilot_day: int  # 0 when no simulator run is loaded
    pilot_days_total: int  # 0 when no simulator run is loaded
    kpis: list[KpiCard]
    funnel: FunnelSummary
    attention: list[AttentionItem]
    activity: list[ActivityItem]
    coverage: list[CoverageRow]


class LiveHealth(CamelModel):
    window_label: str
    p95_reply_latency: str  # "" when the window has no agent turns
    schema_reasks: str  # count as text; "" when the window has no agent turns
    llm_errors: str  # count as text; "" when the window has no agent turns
    outbox_in_dlq: int
    cost_per_hire: str  # "" when the window has no agent turns or no hires


class GuardrailItem(CamelModel):
    id: str
    ok: bool
    label: str


class AgentInfo(CamelModel):
    id: str
    label: str
    version: str


class LiveFeedResponse(CamelModel):
    health: LiveHealth
    guardrails: list[GuardrailItem]
    agents: list[AgentInfo]
