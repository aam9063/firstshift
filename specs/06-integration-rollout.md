# 06 · Integration and rollout: from prototype to part of the client's workflow

**Goal:** make FirstShift production-shaped inside Lumbre's environment: real adapter contracts, reliability under messy client systems, security and compliance evidence, and a rollout plan that changes how managers and HR actually work, not just what software exists.

**Outputs:** adapters in `app/adapters/`, `docs/integration-guide.md`, `docs/security-and-compliance.md`, `docs/rollout-plan.md`, `docs/runbook.md`, `docs/training/manager-quickstart.md`, `docs/pilot-sim-day90.md`.

---

## 1. Integration hardening

For each port, implement the adapter against the mock API **as if it were the real one**, including its failure modes. Add mock fault injection (`mocks/faults.py`) toggled per test.

| System | Must handle |
|---|---|
| HireDesk | Duplicate webhooks, out-of-order events, candidate merged in ATS, requisition closed while candidate is mid-flow |
| Nómina360 | 60 req/min rate limit (token bucket), HTTP 200 with error body, partial creation, nightly CSV reconciliation that detects drift and opens a task for People Ops |
| ShiftGrid | Open shift filled by the manager manually while the agent is offering it (optimistic check before confirming), rota published on Thursdays (respect the cycle), timezone and DST |
| LearnBite | Late completion webhooks, re-enrollment, completion without webhook (poll fallback) |
| M365 calendar | Manager without calendar slots: fall back to proposing slots via WhatsApp buttons |
| WhatsApp channel | 24-hour customer service window and pre-approved templates for messages outside it, delivery and read receipts, media uploads, opt-out keywords |

Each adapter has contract tests that run against the mock and are written so they could run against a client sandbox later. Document in `docs/integration-guide.md`: endpoints, auth, scopes requested and why, rate limits, retry policy, idempotency keys, reconciliation jobs and the exact list of writes FirstShift performs in each system.

## 2. Reliability and observability

- Outbox with exponential backoff and a dead-letter queue visible and replayable in the console (`/ops`).
- Every candidate journey has a trace ID across messages, core transitions and integration calls.
- Health checks per adapter; a degraded adapter pauses only the flows that need it, and candidates get a holding message instead of silence.
- Alerts (documented, not wired to a real pager): DLQ not empty for 15 min, Nómina360 reconciliation drift, manager decision SLA breaches above threshold, LLM error rate above 2%.
- SLOs: first contact under 5 minutes for 95% of applicants during 08:00 to 23:00; no message lost.

## 3. Security and compliance pack

`docs/security-and-compliance.md` is written for Hugo (IT) and Laura (DPO):
- Data flow diagram with every personal data field, where it is stored, for how long and who can read it.
- Record of processing activity draft for the pilot; legal basis per purpose; candidate notice text (ES, PT, EN).
- Retention: rejected and benched candidates deleted or anonymized after the consented period; erasure procedure and its audit.
- AI transparency and human oversight: where the candidate is told they are talking to an AI, who reviews what, how a human can take over any conversation.
- Access control: replace the console's prototype role picker with SSO (the client's Microsoft 365 identity) and role-based access (Talent, DPO, Ops, Admin), least privilege per view and per action (takeover, pause, replay, erasure), secrets management, encryption in transit and at rest, EU hosting.
- A DPIA outline with risks and mitigations (the DPO owns the final DPIA).
- Model and prompt change management: no prompt goes live without a passing eval report attached.

## 4. Rollout plan (the human side)

`docs/rollout-plan.md`:

| Wave | Scope | Entry criteria | Exit criteria |
|---|---|---|---|
| 0. Shadow | 2 restaurants; agent runs, humans see suggestions, nothing is sent to candidates | Security pack signed by IT and DPO | Suggestion quality reviewed by Talent on 50 cases |
| 1. Assisted | Same 2 restaurants; agent talks to candidates, every manager decision explicit | Wave 0 exit; managers trained | 2 weeks, guardrails green, manager NPS collected |
| 2. Pilot | All 12 pilot restaurants | Wave 1 exit; weekly ops review in place | Day-30 go/no-go against pilot charter |
| 3. Expand | Remaining Costa Blanca units, then Algarve (Portuguese) | Day-90 results meet targets | Steering approval |

Change management, concretely:
- **Champion:** Raúl presents the day-30 numbers to other area directors, not the vendor.
- **Managers:** 10-minute in-restaurant onboarding (`docs/training/manager-quickstart.md`, one page, mostly screenshots of the WhatsApp messages they will receive). Yolanda's "maybes" are imported into the bench with consent, so the tool starts by doing what she already does.
- **Talent team:** they move from screening CVs to supervising conversations, handling escalations and tuning criteria with evidence. Define their new weekly routine.
- **Payroll:** receives complete document packs with a "ready" flag instead of chasing emails.
- **Feedback channel:** a WhatsApp keyword for managers ("FEEDBACK ...") that lands in the weekly review.

## 5. Runbook

`docs/runbook.md` for the people who operate it: how to pause the agent for one restaurant, how to take over a conversation, how to replay a stuck outbox message, how to handle a Nómina360 outage, how to process an erasure request, how to roll back a prompt version, who to call for what.

## 6. Day-90 simulated report

Extend the simulated pilot to 90 days and write `docs/pilot-sim-day90.md` as a steering committee readout: results vs the pilot charter, cost per hire vs baseline (with formula), what we learned, what we would change, and a go/no-go recommendation with the conditions for expansion. Keep the "simulation, not real-world proof" caveat visible.

## Exit criteria

- [ ] All adapters have contract tests and pass with fault injection enabled.
- [ ] Integration guide lists every write per system.
- [ ] Security and compliance pack complete enough for an IT and DPO review meeting.
- [ ] Rollout plan with waves, entry and exit criteria, and named owners.
- [ ] Runbook covers at least the 7 operations listed.
- [ ] Day-90 simulated steering readout written.
