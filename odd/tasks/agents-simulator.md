# Feature: F07 agents-and-simulator

## Header

- **Objective:** add the Recruit, Onboard and Pulse agents on Strands Agents (OpenAI API), the simulator backend with controllable clock and scenario loading, and the typed event stream over SSE. Scenarios D1-D7 as automated tests.
- **Status:** closed, awaiting human review (PR open)
- **Next step:** F08 eval-harness after human review.
- **Branch:** feature/agents-simulator (from dev after F06 merged).
- **Scope split:** backend only; the console UI consumes SSE later (C1, console-ui session).

## Specs

Source of truth: specs/04-prototype.md sections 2 to 4, specs/04b-console.md section 2 (simulator API), design/agents.md, design/guardrails.md, AGENTS.md section 5. Governing quotes:

- S1 (04 §2): Recruit agent: consent and AI disclosure, eligibility facts, shift matching against open shifts, interview booking. Onboard agent: document request, LearnBite enrollment, offer after manager approval, first-shift brief, day-before confirmation. Pulse agent: day-3 check-in. Each agent uses a versioned prompt file and only the tools allowed in the current state. LLM outputs that feed the core are Pydantic-validated.
- S2 (04 §2): manager flow in the simulator: approval as a single message with summary and buttons.
- S3 (04 §2): simulator backend: simulated channel adapter, controllable clock, scenario loading, simulator API per specs/04b §2 (POST /api/sim/scenarios/{id}/load, POST /api/sim/clock/advance, POST /api/sim/messages).
- S4 (04 §2 event stream): every agent turn, tool call, state transition and integration write persisted as a typed event and published on GET /api/events/stream (SSE) with Last-Event-ID reconnect.
- S5 (PROMPTS.md F07): scenarios D1-D7 as automated scenario tests; LLM calls may be recorded and replayed in tests for determinism.
- S6 (04 §4 exit): D1-D7 run in the simulator and as automated tests; every LLM call logs prompt version, model, latency, tokens.

## Constraints

- Agents call tools; tools call the deterministic core; the core decides (one-directional). Agents never call client systems directly.
- Prompt injection cannot trigger tools outside the current state's allow-list (G6).
- AI disclosure + consent before processing beyond the first reply (G1, G2). No protected characteristics (G3).
- Tests run offline: the LLM model is behind a port; a scripted/replay model implementation backs tests. Strands+OpenAI is the production model provider via env (OPENAI_API_KEY, OPENAI_MODEL=gpt-4.1-mini default).
- Langfuse trace hook wraps agent turns (enabled only with keys configured; absent = no-op).
- This branch touches app/, mocks/, tests/, app/prompts/ only. No web/.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | Agent layer: Strands wrapper, model port + scripted/replay impl, tool registry with per-state allow-lists, Pydantic output validation, versioned prompts v1, Langfuse hook | done (ab33af0) |
| T2 | S3 | Simulator backend: controllable clock, scenario loading, simulator API, simulator channel adapter persistence | done (650f7f4) |
| T3 | S4 | SSE stream GET /api/events/stream with Last-Event-ID reconnect | done (650f7f4) |
| T4 | S5 | Scenarios D1-D7 as recorded/replayed automated tests | done (fd362f2) |
| T5 | S6 | Close: full suite, evidence, PR | done |

## Open questions

- D7 erasure path: the skeleton has erasure states designed but not implemented; D7 asserts the designed safe behavior at the level implemented (withdrawn + erasure request recorded), noting the gap.

## Log

- L1 (user, verbatim): "Dale. pero una pregunta. El workspace de backend-infra no hace nada, todo esta en esta pestaña"
- L2: Orca worktree card comment updated to reflect that this session works in the backend-infra directory via cd (the card shows no process because the session was not launched by Orca inside it).
- L3: T1 evidence: 28 agent tests green (allow-list enforcement G6, Pydantic re-ask, scripted Recruit flow, prompt disclosure G1-G3, Langfuse no-op); model port with ScriptedModel (offline tests) and StrandsOpenAIModel (live, never contacted in tests); 21 tools over the core; agent.turn/tool.call event types added (dec9894, 4bdcf56). Known loud-failure resolved: D4 exercised backup.activate through the CHANNEL_KINDS path, no OUTBOX_PORTS extension was needed.
- L4: T2/T3 evidence: 18 sim/SSE tests; SimClock with persisted offset and next-timer jump; D1-D7 JSON scenarios; sim API per specs/04b §2; SSE with cursor reconnect and heartbeats (polling choice documented). Commit 650f7f4.
- L5: T4 evidence: 7 scenario tests with scripted agents in the loop via app/sim/agent_loop.py (SimAgentService seeds/writes the run snapshot); D4 backup.activate routed to manager-sim channel, no OUTBOX_PORTS extension needed (CHANNEL_KINDS path); D6 asserts G6 rejection + INV-1; D7 asserts only implemented behavior (erasure request + withdrawn), tombstone gap documented. Commit fd362f2. Final: 164 passed, ruff+mypy clean.
- L6: Known debt recorded: SimAgentService._apply duplicates ~40 lines of AgentService._apply (only occurred_at differs; fold when surfaces allow); agent turns run through the runner function rather than HTTP (sim API cannot carry scripted replies); every LLM call logs prompt_version/model/latency/tokens per S6 (asserted in agent.turn payloads).
