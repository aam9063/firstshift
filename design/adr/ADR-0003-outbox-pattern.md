# ADR-0003: Outbox pattern for every client-system write

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

FirstShift writes to client systems that are slow, rate-limited or silently unreliable: Nómina360 limits writes to 60 requests per minute ("it is not a suggestion" [T-hugo-14]), returns HTTP 200 with an error body on validation failures (the July incident [T-hugo-16, T-hugo-20]), and its truth is only reliable in the nightly CSV [T-hugo-18]. Hugo's non-negotiables: every write idempotent under a key IT controls (C-T5, [T-hugo-22, T-hugo-24]), every write logged with what, when and by whom, queryable by that key (C-T6, [T-hugo-30]), and every write reversible or compensable (C-T7). An agent turn that writes synchronously to a client system would couple conversation latency to integration latency, and a crash between the local state change and the remote write would lose or duplicate work.

## Decision

Every outbound write to a client system goes through an outbox table in the same database transaction as the state change that caused it. A relay worker picks up outbox messages, calls the port adapter with retry and exponential backoff, and records the attempt, result and idempotency key as audit events. Client-facing ports accept an idempotency key on every write; replaying a delivery with the same key updates or no-ops and never duplicates. The relay is the only writer; agent tools and workers enqueue, they never write directly. Inbound webhooks (channel providers, LearnBite completion) carry an idempotency key and are deduplicated at the gateway.

## Consequences

- Exactly-once intent with at-least-once delivery: the idempotency key absorbs redelivery.
- The write history for one person is queryable from one key, which is the test IT will run (C-T6).
- Compensation is designable per write type because every write is a first-class record with state (pending, delivered, failed, compensated), not a fire-and-forget call (C-T7).
- Conversation turns never block on client systems: the agent confirms intent, the relay confirms delivery, and the state machine reflects delivery through events.
- Added latency between decision and remote effect (seconds under normal operation), which the state machine models explicitly rather than hiding.
- The outbox is another Postgres table with retention, so it joins the DPO's erasure scope (C-L5).

## Alternatives considered

- **Synchronous writes from agent tools.** Rejected: couples the conversation to integration latency, makes retries invisible, and a crash mid-call breaks idempotency.
- **Message queue (Redis/Celery task) without a transactional outbox.** Rejected: the classic dual-write problem; the local state change can commit while the enqueue is lost, or vice versa. Celery remains the execution mechanism; the outbox is the source of truth.
- **Writes only from a nightly batch.** Rejected: the promise-to-payroll tracker (O11) and backup activation need same-hour writes, not day-later ones.

## Evidence

- `design/constraints.md`: C-T5, C-T6, C-T7 (idempotency, end-to-end queryability, compensability), C-T2, C-T3 (rate limit, error-body-200), C-L5 (erasure scope).
- Discovery: [T-hugo-14, T-hugo-16, T-hugo-18, T-hugo-20, T-hugo-22, T-hugo-24, T-hugo-30].
- Design: `design/options.md` O5, O11, O12 (all depend on the write path); `design/guardrails.md` INV-8, INV-9.
- Spec: `specs/03-solution-design.md` sections 6 and 7.
