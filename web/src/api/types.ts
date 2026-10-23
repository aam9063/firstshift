/* FirstShift API contract types, hand written while the backend is built in
   parallel (user decision recorded in odd/tasks/console-ui.md, L3).
   When the FastAPI schema is live these are replaced by the output of
   `pnpm gen:api` (src/api/schema.d.ts) and this file is deleted. */

/* Overview */

export type MetricStatus = "on_target" | "below_target";

export interface KpiCard {
  id: string;
  label: string;
  value: string;
  unit: string;
  status: MetricStatus;
  control: string;
  baseline: string;
  target: string;
  /** Source endpoint and metric key shown in the tooltip, e.g. "/metrics/kpis - ttfps". */
  source: string;
  /** Sparkline points, oldest to newest. */
  trend: number[];
}

export interface FunnelStage {
  id: string;
  label: string;
  pilotPct: number;
  controlPct: number;
}

export interface FunnelSummary {
  pilotCandidates: number;
  controlCandidates: number;
  stages: FunnelStage[];
  insight: string;
}

export type AttentionKind =
  | "sla_breach"
  | "first_shift"
  | "human_needed"
  | "dlq"
  | "eval";

export interface AttentionItem {
  id: string;
  kind: AttentionKind;
  title: string;
  detail: string;
  ago: string;
}

export type ActorType = "agent" | "candidate" | "human" | "system";

export interface ActivityItem {
  id: string;
  at: string;
  actorType: ActorType;
  actorLabel: string;
  eventType: string;
  summary: string;
  detailTag?: string;
}

export interface CoverageRow {
  id: string;
  restaurant: string;
  cohort: "pilot" | "control";
  openShifts: number;
  coveredPct: number;
  bench: number;
  managerReply: string;
}

export interface OverviewResponse {
  simClock: string;
  pilotDay: number;
  pilotDaysTotal: number;
  kpis: KpiCard[];
  funnel: FunnelSummary;
  attention: AttentionItem[];
  activity: ActivityItem[];
  coverage: CoverageRow[];
}

/* Live feed */

export type EventKind =
  | "agent_turn"
  | "tool_call"
  | "state_change"
  | "integration"
  | "human_action";

export interface ToolCallDetail {
  tool: string;
  argumentsJson: string;
  resultJson: string;
}

export interface LiveEvent {
  id: string;
  kind: EventKind;
  actorType: ActorType;
  actorLabel: string;
  /** Prompt version for agent turns, e.g. "recruit@v7". */
  agentVersion?: string;
  summary: string;
  at: string;
  latencyMs?: number;
  model?: string;
  state?: string;
  tokensIn?: number;
  tokensOut?: number;
  /** Schema validation note, e.g. "ShiftProposal / schema v3". */
  validation?: string;
  traceId?: string;
  toolCall?: ToolCallDetail;
}

export interface LiveHealth {
  windowLabel: string;
  p95ReplyLatency: string;
  schemaReasks: string;
  llmErrors: string;
  outboxInDlq: number;
  costPerHire: string;
}

export interface GuardrailItem {
  id: string;
  ok: boolean;
  label: string;
}

export interface LiveFeedResponse {
  health: LiveHealth;
  guardrails: GuardrailItem[];
  agents: { id: string; label: string; version: string }[];
}

/* Candidate list (GET /api/candidates, app/api/console/schemas.py) */

export type SlaRisk = "ok" | "at_risk" | "breached";

export interface CandidateListItem {
  id: string;
  firstName: string;
  initials: string;
  state: string;
  stateLabel: string;
  restaurant: string;
  restaurantCode: string;
  cohort: "pilot" | "control";
  languages: string[];
  /** "" until the LLM agent loop has run for this candidate. */
  agentVersion: string;
  agentInControl: boolean;
  slaRisk: SlaRisk;
  /** ISO timestamp, "" when nothing is recorded yet. */
  lastActivityAt: string;
  /** "" when no shift is matched. */
  matchedShiftLabel: string;
  phoneMasked: string;
  elapsedLabel: string;
}

export interface CandidatesListResponse {
  items: CandidateListItem[];
  total: number;
  page: number;
  pageSize: number;
}

/* Candidate journey */

export type JourneyStateId =
  | "new"
  | "contacted"
  | "consent"
  | "screening"
  | "matched"
  | "interview_booked";

export interface JourneyStep {
  id: JourneyStateId;
  label: string;
  at: string;
  actorLabel: string;
  actorType: ActorType;
  note?: string;
  current?: boolean;
}

export interface ThreadMessage {
  id: string;
  at: string;
  /** "candidate" messages come from the person, "agent" from FirstShift, "human" from staff. */
  senderType: ActorType | "candidate";
  senderLabel?: string;
  agentVersion?: string;
  text: string;
  /** Inline tool call markers shown as chips between messages. */
  toolCalls?: ToolCallMarker[];
}

export interface ToolCallMarker {
  tool: string;
  argsSummary: string;
  latencyMs?: number;
  resultSummary?: string;
}

export interface MatchedShift {
  label: string;
  restaurant: string;
  detail: string;
  shiftIds: string[];
  held: string;
}

export interface RecordRow {
  label: string;
  value: string;
  status?: "ok" | "pending" | "not_requested";
}

export interface IntegrationWrite {
  id: string;
  statusCode: number;
  target: string;
  operation: string;
  idempotencyKey: string;
}

/* Restaurant list and detail (GET /api/restaurants, app/api/console/schemas.py
   RestaurantRow / ShiftRow / RestaurantShiftsResponse) */

export type Cohort = "pilot" | "control";

export interface RestaurantRow {
  id: string;
  code: string;
  name: string;
  city: string;
  cohort: Cohort;
  openShifts: number;
  /** 0..100, covered shifts / open shifts. */
  coveredPct: number;
  bench: number;
  openCandidates: number;
  /** "" when no manager decision is recorded. */
  managerMedianReply: string;
  paused: boolean;
}

export interface ShiftRow {
  id: string;
  label: string;
  startsAt: string;
  endsAt: string;
  role: string;
  requiresFoodHygiene: boolean;
  status: string;
  matchedCandidateId: string | null;
  matchedCandidateName: string | null;
}

export interface RestaurantShiftsResponse {
  restaurant: RestaurantRow;
  shifts: ShiftRow[];
}

/* Operations queues (GET /api/escalations returns AttentionItem[], see above;
   GET /health/adapters; GET /api/outbox?status=failed) */

export interface AdapterHealth {
  system: string;
  status: "ok" | "degraded" | "unknown";
  lastCheckedAt: string;
  failureReason: string | null;
}

export interface AdaptersHealthResponse {
  adapters: AdapterHealth[];
}

export interface OutboxMessageRow {
  id: string;
  port: string;
  operation: string;
  status: string;
  attempts: number;
  lastError: string | null;
  idempotencyKey: string;
}

export interface OutboxListResponse {
  status: string;
  messages: OutboxMessageRow[];
}

export interface PauseResponse {
  restaurantId: string;
  code: string;
  paused: boolean;
}

export interface ReplayResponse {
  id: string;
  status: string;
  attempts: number;
}

/* Audit log (GET /api/audit) */

export interface AuditRow {
  id: string;
  at: string;
  actorType: ActorType;
  actorLabel: string;
  eventType: string;
  stateFrom: string | null;
  stateTo: string | null;
  summary: string;
  payload: Record<string, unknown>;
}

export interface AuditResponse {
  items: AuditRow[];
  total: number;
  limit: number;
  offset: number;
}

/* Evals (GET /api/evals is camelCase; GET /api/evals/{version} returns the
   runner report JSON verbatim, so its fields stay snake_case) */

export interface EvalSummaryRow {
  version: string;
  label: string;
  generatedAt: string;
  taskSuccessRate: number | null;
  costPerHireUsd: number | null;
}

export interface EvalMeta {
  suite: string;
  seed: number;
  label: string;
  generated_at: string;
  persona_count?: number;
  judge_model?: string;
  elapsed_seconds?: number;
}

export interface EvalSummary {
  task_success: number;
  task_success_rate: number;
  deterministic_failures: number;
  interview_show_rate: number;
  day1_show_rate: number;
  median_ttfps_hours: number;
  total_cost_usd: number;
  cost_per_hired_usd: number;
  mean_judge_score: number;
}

export interface EvalCheckStat {
  passed: number;
  failed: number;
}

export interface EvalDeterministicChecks {
  failing: number;
  checked_conversations: number;
  per_check: Record<string, EvalCheckStat>;
}

export interface EvalTranscriptLine {
  role: string;
  text: string;
}

export interface EvalConversation {
  persona_id: string;
  label: string;
  conversation_id: string;
  trace_id: string;
  scenario: string;
  final_state: string;
  expected_outcome: string;
  task_success: boolean;
  task_detail: string;
  judge_mean: number;
  judge_scores: Record<string, number>;
  transcript: EvalTranscriptLine[];
}

export interface EvalFairnessRow {
  dimension: string;
  group: string;
  n: number;
  selected: number;
  rate: number;
  ratio: number;
  flagged: boolean;
}

export interface EvalCost {
  conversations: number;
  turns: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_usd: number;
  p95_latency_ms: number;
  hired: number;
  cost_per_hired_usd: number;
  per_conversation: {
    conversation_id: string;
    turns: number;
    input_tokens: number;
    output_tokens: number;
    usd: number;
    p95_latency_ms: number;
  }[];
}

export interface EvalReport {
  meta: EvalMeta;
  summary: EvalSummary;
  deterministic_checks: EvalDeterministicChecks;
  conversations: EvalConversation[];
  worst_5: EvalConversation[];
  funnel: Record<string, number>;
  fairness: EvalFairnessRow[];
  cost: EvalCost;
  comparison: { previous_label: string | null; summary: EvalSummary | null } | null;
  what_changed: string | null;
}

/* Simulator (GET /simulator/messages returns the OutboundMessage port shape;
   POST /api/sim/* return plain dicts from app/api/sim.py and app/sim/runner.py) */

export interface SimulatorMessage {
  recipientRef: string;
  body: string;
  quickReplies: string[];
  correlationId: string;
}

export interface SimScenarioLoadResponse {
  status: string;
  scenarioId: string;
  state: string;
  manager?: { id?: string; name?: string } & Record<string, unknown>;
  [key: string]: unknown;
}

export interface SimClockAdvanceResponse {
  status: string;
  now: string;
  state: string;
  timers_fired: Record<string, unknown>[];
  timers_skipped: { timer: string; reason: string }[];
}

export interface SimClockAdvanceInput {
  minutes?: number;
  hours?: number;
  days?: number;
  next_timer?: boolean;
}

export interface SimMessageResponse {
  status: string;
  role: string;
  event: string | null;
  transitioned: boolean;
  state: string;
  trace_id: string;
}

export interface SimMessageInput {
  role: "candidate" | "manager" | "system";
  text: string;
  event?: string;
  payload?: Record<string, unknown>;
  application_id?: string;
}

/* Compliance (POST /api/erasure-requests, CamelModel response) */

export interface ErasureResponse {
  id: string;
  candidateId: string;
  status: string;
  requestedAt: string;
}

export interface ErasureInput {
  candidateId: string;
  reason?: string;
}

export interface AuditQuery {
  q?: string;
  eventType?: string;
  candidateId?: string;
  limit?: number;
  offset?: number;
}

export interface CandidateDetail {
  id: string;
  firstName: string;
  lastName: string;
  initials: string;
  stateLabel: string;
  restaurant: string;
  languages: string[];
  agentVersion: string;
  agentInControl: boolean;
  elapsedLabel: string;
  phoneMasked: string;
  journey: JourneyStep[];
  candidateThread: ThreadMessage[];
  managerThread: ThreadMessage[];
  matchedShift: MatchedShift;
  summaryRows: RecordRow[];
  summaryNote: string;
  consentRow: RecordRow;
  preBoarding: RecordRow[];
  writes: IntegrationWrite[];
}
