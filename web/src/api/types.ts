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
