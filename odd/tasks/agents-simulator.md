# Feature: F07 agents-and-simulator

## Header

- **Objective:** add the Recruit, Onboard and Pulse agents on Strands Agents (OpenAI API), the simulator backend with controllable clock and scenario loading, and the typed event stream over SSE. Scenarios D1-D7 as automated tests.
- **Status:** in progress
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
| T2 | S3 | Simulator backend: controllable clock, scenario loading, simulator API, simulator channel adapter persistence | pending |
| T3 | S4 | SSE stream GET /api/events/stream with Last-Event-ID reconnect | pending |
| T4 | S5 | Scenarios D1-D7 as recorded/replayed automated tests | pending |
| T5 | S6 | Close: full suite, evidence, PR | pending |

## Open questions

- D7 erasure path: the skeleton has erasure states designed but not implemented; D7 asserts the designed safe behavior at the level implemented (withdrawn + erasure request recorded), noting the gap.

## Log

- L1 (user, verbatim): "Dale. pero una pregunta. El workspace de backend-infra no hace nada, todo esta en esta pestaña"
- L2: Orca worktree card comment updated to reflect that this session works in the backend-infra directory via cd (the card shows no process because the session was not launched by Orca inside it).
- L3: T1 evidence: 28 agent tests green (allow-list enforcement G6, Pydantic re-ask, scripted Recruit flow, prompt disclosure G1-G3, Langfuse no-op); model port with ScriptedModel (offline tests) and StrandsOpenAIModel (live, never contacted in tests); 21 tools over the core; agent.turn/tool.call event types added (dec9894, 4bdcf56). Known loud-failure: outbox kind backup.activate has no port value yet (D4 will exercise it; handled with T2/T4 or a schema migration).
