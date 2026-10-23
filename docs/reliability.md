# Reliability: alerts, SLOs and degraded mode (F12, T2)

Source of truth: `specs/06-integration-rollout.md` section 2. This document
names what to wire, what each signal means and how the system behaves when a
client system degrades. Where a control exists only as a documented intent
and is not yet connected to a real pager, that is stated plainly next to it.

## Alerts to wire

| Alert | Condition | Why it matters | Wired? |
|---|---|---|---|
| DLQ not empty | Any outbox row with status `failed` stays failed for more than 15 minutes | A dead-lettered write is a lost write to a client system (stage update, shift assignment) until a human replays it through `POST /api/outbox/{id}/replay` | **Documented, not wired to a real pager.** The signal is queryable: `GET /api/outbox?status=failed` lists every dead-lettered write with id, port, operation, attempts, last_error and idempotency_key, and the relay already emits the dead-letter audit row (`integration.write.dead_letter`). A cron or Prometheus alert on outbox depth by status still needs to be configured in the Grafana stack. |
| Nómina360 reconciliation drift | The nightly CSV reconciliation (O12) finds an API-confirmed creation the CSV does not show, or a creation the CSV revoked | Payroll truth diverges from FirstShift: nobody works unregistered (C-T4, row 20/22 of the state machine) | **Documented, not wired to a real pager.** The reconciliation worker already opens the task and the alert event for IT and People Ops; routing that event to a human page is pending. |
| Manager decision SLA breaches above threshold | More than an agreed share of manager decisions pass the 8 h escalation (timer T3) in a week | Hiring throughput stalls silently when managers do not answer; the HRBP escalation path exists but nobody watches the rate | **Documented, not wired to a real pager.** The SLA timers fire and every escalation is audited; the weekly rate metric needs a dashboard panel and a threshold alert. |
| LLM error rate above 2% | More than 2% of agent turns end in provider or schema-validation errors over a rolling window | The conversation layer degrades before candidates notice: re-asks increase, latency grows, evals fail | **Documented, not wired to a real pager.** Errors are captured (Sentry, Langfuse traces); the aggregate error-rate metric and its alert rule are pending. |

Every alert above is *observable today* from persisted, typed data (outbox
status counts, reconciliation audit events, timer audit events, agent turn
events). What is missing is only the pager plumbing, and that is deliberate:
the spec says the alerts are "documented, not wired to a real pager" for the
pilot.

## SLOs

From `specs/06-integration-rollout.md` section 2, verbatim:

> SLOs: first contact under 5 minutes for 95% of applicants during 08:00 to
> 23:00; no message lost.

How the system is built to meet them:

- **First contact under 5 minutes (95%, 08:00 to 23:00).** The HireDesk
  webhook handler sends the first message synchronously in the request that
  creates the candidate, with the AI disclosure and notice version. There is
  no queue between the webhook and the first message.
- **No message lost.** Every outbound write enters the outbox table first
  (architecture rule 4, ADR-003). The relay retries with exponential backoff
  (1s, 4s, 16s, 60s, five attempts) and dead-letters after the last attempt
  instead of dropping; the dead-letter queue is visible and replayable. The
  messaging channel confirms delivery (simulator inline, Twilio receipts) so
  an outbox row is never marked done on a guess.

Measurement of the first-contact SLO is not wired yet either: the webhook
stores the first-contact timestamp, and a metric over it needs the Grafana
panel named above.

## Degraded-mode behavior

Health is checked per adapter. `GET /health/adapters` returns one entry per
registered client system (hiredesk, nomina360, shiftgrid, learnbite, m365,
whatsapp) with `status` ok, degraded or unknown, the last check time and the
failure reason. Adapters are discovered defensively: a missing adapter
reports `unknown` and the endpoint never crashes. `GET /health` remains the
process liveness check.

When an adapter reports `degraded`:

1. **Only the flows that need that system pause.** The mapping is pure and
   deterministic (`app/core/degraded.py`):

   | Flow | Required system |
   |---|---|
   | First contact and every reminder lane | WhatsApp channel |
   | Tracker completion (O11, ready for rota) | Nómina360 |
   | Shift matching (fit read and first-shift write) | ShiftGrid |
   | Training enrollment | LearnBite |

   A reminder still goes out when Nómina360 is down; a tracker completion
   still processes when the channel is down. Status `ok` and `unknown` never
   pause a flow: unknown is a visibility gap, and silently silencing
   candidates is the one failure the spec forbids.

2. **The candidate gets a holding message instead of silence.** When a flow
   pauses, the candidate receives the `holding` template from the versioned
   catalog in their language (es, pt and en): their application stays open
   and FirstShift will write back when the system recovers. The pause is
   explained by an audit record (`flow.paused`, actor system, with the flow,
   the required system and the reason) and an `escalation.created` event in
   the stream, so the console sees it live.

3. **Recovery is manual and safe.** The relay never loses a message: writes
   wait in the outbox with exponential backoff, and anything that exhausts
   its retries is replayed by a human through the dead-letter endpoint with
   the same idempotency key, so no write is ever applied twice.

## What is documented but not wired

To be plain about the gap between this document and a running pager:

- The four alert rules (DLQ age, reconciliation drift, SLA breach rate, LLM
  error rate) exist as queries over persisted data, not as Grafana or
  Alertmanager rules.
- The first-contact SLO is enforced structurally (synchronous first
  message), but there is no dashboard computing the 95th percentile over
  08:00 to 23:00.
- The Twilio delivery-receipt feedback loop into outbox status is the
  channel adapter's contract; the receipt-driven status transitions for the
  governed channel are part of the adapters workstream.

Everything else described here (health endpoint, degraded-mode gate,
holding messages, dead-letter listing and replay, trace propagation) is
implemented and covered by `tests/test_health_adapters.py`,
`tests/test_degraded_mode.py` and `tests/test_dlq_replay.py`.
