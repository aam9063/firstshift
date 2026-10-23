# Feature: F12 integration-hardening

## Header

- **Objective:** make FirstShift production-shaped inside Lumbre's environment: adapters that survive the client systems' real failure modes, contract tests, fault injection, observability and degraded-mode behaviour, plus the integration guide that lists every write.
- **Status:** in progress
- **Branch:** feature/integration-hardening, from dev (05ebc18).

## Specs

Source of truth: `specs/06-integration-rollout.md` sections 1 and 2, `design/integration-contracts.md`. Governing requirements:

- S1 (§1): per system, handle the listed failure modes: HireDesk duplicates/out-of-order/merged candidate/requisition closed; Nómina360 60 req/min token bucket, HTTP 200 with error body, partial creation, nightly CSV reconciliation that detects drift and opens a task for People Ops; ShiftGrid open shift filled manually (optimistic check), Thursday rota cycle, timezone/DST; LearnBite late completion webhooks, re-enrollment, completion without webhook (poll fallback); M365 manager without calendar slots (fall back to WhatsApp buttons); WhatsApp 24h window, templates, receipts, media, opt-out.
- S2 (§1): each adapter has contract tests that run against the mock and are written so they could run against a client sandbox later.
- S3 (§1): `docs/integration-guide.md` documents endpoints, auth, scopes and why, rate limits, retry policy, idempotency keys, reconciliation jobs and the exact list of writes per system.
- S4 (§2): outbox with exponential backoff and a dead-letter queue that is replayable; every candidate journey carries a trace id across messages, transitions and integration calls; health checks per adapter; a degraded adapter pauses only the flows that need it and candidates get a holding message instead of silence; alerts documented; SLOs stated (first contact under 5 minutes for 95% of applicants between 08:00 and 23:00, no message lost).

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1,S2 | Fault injection in the mocks and the adapters that handle every listed failure mode, with contract tests | pending |
| T2 | S4 | Health checks per adapter, degraded-mode gating and holding messages, trace propagation, DLQ replay path | pending |
| T3 | S3 | docs/integration-guide.md with every write per system | pending |
| T4 | - | Verify (suite, ruff, mypy), close, PR | pending |

## Constraints

- Adapters implement the ports in `app/ports/`; mocks implement the same contract; swapping a mock for a real adapter stays configuration.
- No web/ changes (console work belongs to the console session).
- Every failure mode starts as a failing test (spec 06 §1 and AGENTS.md section 3).
- Deterministic: fault injection is toggled per test, never ambient.

## Open questions

- The 24h WhatsApp window and templates need Twilio content templates in the real account; the adapter implements the contract and the mock simulates the window, while template registration stays a client-side setup step documented in the guide.

## Log

- L1 (user, verbatim): "vamos con F12. Y una pregunta, cuando podremos empezar a conectar el backend y el agente al front para que deje de mostrar datos mockeados?"
- L2: Answer given: the console endpoints from specs/04b §2 are not implemented yet; a follow-up `console-api` feature implements them so the console can switch MSW off and point VITE_API_URL at the backend. F12 proceeds first as asked.
