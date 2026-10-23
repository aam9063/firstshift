# Feature: console-api

## Header

- **Objective:** implement the console-facing API from `specs/04b-console.md` section 2 so the FirstShift Console can stop using MSW mocks and read real data from the backend by pointing `VITE_API_URL` at it.
- **Status:** closed, awaiting review (PR open)
- **Branch:** feature/console-api, in its own Orca worktree (never touches the backend-infra worktree or the console session's tree).

## Specs

Source of truth: `specs/04b-console.md` section 2 (endpoint table) and section 3 (what each view shows), plus the **response contract** the console already consumes in `web/src/api/types.ts` (read-only; the console session owns that file).

Rules:
- S1: every response must match the TypeScript shapes below exactly (same key names, same value kinds, same enum strings). The console must be able to disable MSW with no component changes.
- S2: the console talks only to this API; it never calls mocks or client systems.
- S3: simulated data is labelled (the SIMULATION badge is driven by field values, for example `pilotDay` and the presence of `simClock`).
- S4: personal data minimized: phone numbers masked, documents shown as status only.
- S5: every human action is audited with the acting role (the console sends `X-Actor-Role`: talent, dpo, ops).

## Endpoints (spec section 2)

| Method and path | Purpose |
|---|---|
| GET /api/candidates | paginated, filterable list (state, restaurant, agent, SLA risk, language, pilot/control) |
| GET /api/candidates/{id} | full journey: profile, state history, conversation, agent turns, tool calls, decisions, documents and training status, audit events |
| GET /api/restaurants and GET /api/restaurants/{id}/shifts | open shifts, coverage, bench size, manager SLA stats |
| GET /api/metrics/funnel and GET /api/metrics/kpis | metric tree from design/metric-tree.md, pilot vs control vs baseline |
| GET /api/escalations | pending manager decisions, SLA breaches, escalated conversations, DLQ items |
| GET /api/audit | searchable audit log |
| GET /api/evals and GET /api/evals/{version} | eval report data as JSON |
| GET /api/events/stream | SSE (already implemented; keep it) |
| POST /api/candidates/{id}/takeover, /release, /messages | human takeover flow |
| POST /api/restaurants/{id}/pause | pause all agents for one restaurant |
| POST /api/outbox/{id}/replay | replay a dead-lettered write (exists under /api/outbox; expose the console path too) |
| POST /api/erasure-requests | start a GDPR erasure |

## Response contract (from web/src/api/types.ts, verbatim)

```ts
type MetricStatus = "on_target" | "below_target";
interface KpiCard { id, label, value, unit, status: MetricStatus, control, baseline, target, source, trend: number[] }
interface FunnelStage { id, label, pilotPct: number, controlPct: number }
interface FunnelSummary { pilotCandidates: number, controlCandidates: number, stages: FunnelStage[], insight }
type AttentionKind = "sla_breach" | "first_shift" | "human_needed" | "dlq" | "eval";
interface AttentionItem { id, kind: AttentionKind, title, detail, ago }
type ActorType = "agent" | "candidate" | "human" | "system";
interface ActivityItem { id, at, actorType: ActorType, actorLabel, eventType, summary, detailTag? }
interface CoverageRow { id, restaurant, cohort: "pilot" | "control", openShifts: number, coveredPct: number, bench: number, managerReply }
interface OverviewResponse { simClock, pilotDay: number, pilotDaysTotal: number, kpis: KpiCard[], funnel: FunnelSummary, attention: AttentionItem[], activity: ActivityItem[], coverage: CoverageRow[] }
type EventKind = "agent_turn" | "tool_call" | "state_change" | "integration" | "human_action";
interface ToolCallDetail { tool, argumentsJson, resultJson }
interface LiveEvent { id, kind: EventKind, actorType: ActorType, actorLabel, agentVersion?, summary, at, latencyMs?, model?, state?, tokensIn?, tokensOut?, validation?, traceId?, toolCall? }
interface LiveHealth { windowLabel, p95ReplyLatency, schemaReasks, llmErrors, outboxInDlq: number, costPerHire }
interface GuardrailItem { id, ok: boolean, label }
interface LiveFeedResponse { health: LiveHealth, guardrails: GuardrailItem[], agents: {id,label,version}[] }
type JourneyStateId = "new" | "contacted" | "consent" | "screening" | "matched" | "interview_booked";
interface JourneyStep { id: JourneyStateId, label, at, actorLabel, actorType: ActorType, note?, current? }
interface ThreadMessage { id, at, senderType: ActorType | "candidate", senderLabel?, agentVersion?, text, toolCalls?: ToolCallMarker[] }
interface ToolCallMarker { tool, argsSummary, latencyMs?, resultSummary? }
interface MatchedShift { label, restaurant, detail, shiftIds: string[], held }
interface RecordRow { label, value, status?: "ok" | "pending" | "not_requested" }
interface IntegrationWrite { id, statusCode: number, target, operation, idempotencyKey }
interface CandidateDetail { id, firstName, lastName, initials, stateLabel, restaurant, languages: string[], agentVersion, agentInControl: boolean, elapsedLabel, phoneMasked, journey: JourneyStep[], candidateThread: ThreadMessage[], managerThread: ThreadMessage[], matchedShift: MatchedShift, summaryRows: RecordRow[], summaryNote, consentRow: RecordRow, preBoarding: RecordRow[], writes: IntegrationWrite[] }
```

The list endpoint shape is defined by the console's table columns (`web/src/features/candidates`); match it as closely as the types file allows and document any field the backend cannot fill yet as an explicit empty value, never a fabricated one.

## Data mapping

- Candidates and applications: `app.db.models` (Candidate, Application) plus `events` and `audit_events` for the journey, threads and writes.
- Restaurants and shifts: Restaurant, OpenShift.
- KPIs and funnel: `evals/metrics.py` formulas over the event log; when a series has no simulated history yet, return the real value with an empty `trend` and say so in `insight`.
- Escalations: AuditEvent `flow.paused`, `inbound_escalation_created`, manager-SLA rows, and dead-lettered outbox rows.
- Evals: read `evals/reports/eval-vN.json`.
- Takeover: a human takeover row that pauses the agent for that candidate (state must be visible in `agentInControl`).

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | Contract tests pinning every response shape against the TypeScript contract (keys and kinds), RED first | done (46 tests) |
| T2 | S1 | Candidates list and detail endpoints | done |
| T3 | S1 | Restaurants, shifts, coverage and manager SLA | done |
| T4 | S1 | Metrics funnel and KPIs, plus the /api/overview and /api/live composites | done |
| T5 | S1 | Escalations, audit, evals | done |
| T6 | S1 | Takeover, release, human messages, restaurant pause, outbox replay path, erasure requests | done |
| T7 | - | Verify, close, PR | done |

## Open questions

- The console's list-row shape lives in `web/src/features/candidates`; read it read-only and match it, documenting any missing field explicitly.

## Log

- L1 (user, verbatim): "ok lanzalo en paralelo cuando acabe. El mock o sea el diseño ha de respetarse, que el trabajo no se pise con este worktree"
- L2: Console session owns `web/`; this branch only adds backend endpoints under `app/api/console/` and tests.

- L3: Evidence (b4e10bd): read endpoints (candidates with pagination and six filters, full detail with journey/threads/writes/consent/pre-boarding, restaurants and shifts, metrics funnel and six KPI cards over the metric-tree formulas, escalations, audit search, evals) and action endpoints (takeover/release with agentInControl derived from the append-only audit, human messages as message.out sender human with a 409 outside takeover, restaurant pause/resume, erasure requests), all role-audited via X-Actor-Role. 46 tests written RED first.
- L4: Single owner for POST /api/outbox/{id}/replay: app/api/outbox.py (F12) owns the path; the console handler was removed and its tests were rewritten to the shared pending/attempts-0 semantics (9bf1b9c). Full suite 533 at that point.
- L5: Evidence (ce81f5b): /api/overview and /api/live match OverviewResponse and LiveFeedResponse exactly, with honest empty states (no sim run, no turns, no DLQ) and real rows for activity/attention/coverage; 11 shape/behaviour tests RED first; full suite 544 passed, ruff and mypy clean.
- L6: Known, documented limits: agentVersion is empty (scripted backend), lastName empty (not stored), matchedShift empty unless shift rows carry the link, statusCode 0 for unconfirmed writes, manager_minutes_per_hire empty (not collected), trends empty under two days of history, consentRow may say none recorded in the sim path. The guardrail computation is reimplemented in the console module because evals/checks is not mypy-strict clean; that duplication is documented.
- L7: How the console switches: set VITE_API_URL to the backend, disable the MSW worker (the console session owns that switch), and regenerate types with pnpm gen:api once the backend runs. No component change is required by this feature.
