# Feature: F06 walking-skeleton

## Header

- **Objective:** Milestone A of specs/04-prototype.md: the thinnest path with no LLM, proving wiring. One candidate flows from webhook to first_shift_scheduled using only mocks, visible in the audit log.
- **Status:** closed, awaiting human review (PR open)
- **Next step:** F07 agents-and-simulator after human review.
- **Branch:** feature/walking-skeleton, in worktree backend-infra (separate from the console-ui session).

## Specs

Source of truth: specs/04-prototype.md section 1 (Milestone A), design/state-machine.md, design/data-model.md, design/integration-contracts.md, AGENTS.md section 5. Governing quotes:

- S1 (04 §1.1): docker compose with Postgres and Redis; FastAPI app boots; Alembic migration creates core tables.
- S2 (04 §1.2): mock services in mocks/ (one FastAPI app with routers per system) seeded from mocks/seed/: 12 pilot + 3 control restaurants, managers, open shifts for the next 3 weeks, 200 historical candidates.
- S3 (04 §1.3): HireDesk mock fires a webhook "new application" > POST /webhooks/hiredesk > candidate created in new > channel gateway sends the first message to the simulator.
- S4 (04 §1.4): core state machine implemented for the happy path with unit tests, including the invariants of specs/03 §5 as tests (RED first).
- S5 (04 §1.5): outbox table and relay worker writing a stage update back to HireDesk mock, idempotent (test: relay the same message twice, one write).
- S6 (04 §1, PROMPTS.md F06): design the typed event model now (state.transition, integration.write, message.in, message.out; agent events come in F07) because the console will stream it.
- S7 (acceptance): uv run pytest green; a scripted candidate reaches first_shift_scheduled in an integration test using only mocks; the audit log shows every transition with actor.

## Constraints

- Deterministic core: plain Python, no I/O, no LLM (agents arrive in F07; scripted replies here).
- Ports and adapters: client systems behind ports (app/ports/), mocks implement the same contract.
- Idempotency everywhere: webhook dedup key; outbox relay dedup (S5 test).
- This branch touches app/, mocks/, tests/, alembic/, docker-compose.yml only. No web/.
- TDD: RED before each implementation step (backend runner uv run pytest).

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | DB models + Alembic migration + compose checks | done |
| T2 | S2 | Mock services app with routers per system, seeded | done |
| T3 | S4 | Core state machine happy path + invariant tests (RED first) | done |
| T4 | S6 | Typed event model + audit log append | done |
| T5 | S3 | Webhook endpoint + channel gateway first message to simulator | done |
| T6 | S5 | Outbox + idempotent relay worker | done |
| T7 | S7 | Integration test: scripted candidate reaches first_shift_scheduled; close | done |

## Open questions

- None blocking. The scripted first message (no LLM) is a canned template per S6 scope.

## Log

- L1 (user, verbatim): "Ok. La otra sesion me ha sugerido que hagas tu propio worktree para que no os solapeis y no haya conflictos de si esta ha pusheado tal cosa y la otra tambien"
- L2: Worktree backend-infra created via Orca; main tree left on dev for the console session.
- L3: Evidence per unit (commit: tests): T1/T4 aebec03 (13 db+events tests, migration 751da69ac6df + 8c41f2b09d73, dev DB migrated and seeded: 15 restaurants, 630 shifts); T2 e6131c0 (18 tests, mocks boot on :8010, Nómina360 200-error-body quirk); T3 3e30031 (55 tests: happy path walk, INV-1..5 property+behavioral, all timers); T5 43d66f8 (5 webhook tests: dedup replay no-op, 422, persisted effects); T6 aad91c9 (5 relay tests incl. the S5 named idempotency test, backoff, dead-letter, skip-locked); T7 3c264d4 (3 integration tests: 12-transition chain new > first_shift_scheduled, audit completeness with actors, relay exactly-once). Final: uv run pytest 111 passed, ruff clean, mypy clean (explicit_package_bases added).
- L4: Decisions and fixes recorded: outbox_port enum extended with whatsapp (schema gap found by T5 worker, parent applied option A); relay rewritten over ORM Session (Connection.scalars on entity selects yields the first column, a real SQLAlchemy 2 gotcha); MockHireDeskAdapter in tests uses TestClient without context manager (httpx.Client cannot drive ASGITransport sync; entering the context would reseed the store); ScriptedJourney caches core guard facts in memory (no DB columns yet; F07 supersedes); trainer.notify and bench.reserve_backup outbox kinds map to the whatsapp port, shiftgrid.write stays pending until the relay claims that port (F12 scope); FirstShift row for the scheduled shift deferred (outbox + state.transition evidence stand in).
- L5: Slice note: 11037 authored lines across the feature; six work-unit commits, one per unit, each with tests; review per commit is feasible.
