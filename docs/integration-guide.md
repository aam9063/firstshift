# FirstShift integration guide

For IT (Hugo) and the system owners. This document lists, for every client
system: the endpoints FirstShift calls, the authentication and the scopes it
needs and why, the rate limits, the retry policy, the idempotency key scheme,
the reconciliation jobs, and the exact list of writes FirstShift performs.

Everything here is implemented in `app/adapters/` against the ports in
`app/ports/` and verified by the contract suites in
`tests/test_adapter_contracts.py` (runnable against a client sandbox by
pointing them at the sandbox base URL) and the failure-mode tests in
`tests/test_adapter_failures.py`. The mock client systems in `mocks/`
implement the same contracts, with deterministic fault injection
(`mocks/faults.py`) reproducing every failure mode listed in
`specs/06-integration-rollout.md` section 1.

## 0. Shared conventions

### Error taxonomy

Every adapter raises one of these typed errors, never a raw HTTP error
(`app/ports/errors.py`):

| Error | Meaning | Default handling |
|---|---|---|
| `PortTransientError` | timeout, 5xx, network | retry with backoff |
| `PortRateLimitedError` | explicit throttle signal | wait per the signal, then retry |
| `PortValidationError` | the system rejected the payload | never retried; task for a human |
| `PortProtocolError` | response does not match the documentation | no retry; alert IT |
| `PortAuthError` | credentials or gateway rejected the call | no retry; page IT |

### Retry policy

Default: 5 attempts, exponential backoff of 1s, 4s, 16s, 60s with jitter.
After the last attempt the outbox message is `failed`, an AuditEvent records
it, and Prometheus fires the alert. Per-system overrides are stated in each
section. All writes travel through the outbox (`OutboxMessage`, ADR-003) and
are delivered by the relay worker, so no agent or core code calls a client
system inline.

### Idempotency key scheme

A key IT controls, generated once when the message enters the outbox and
stable across retries (C-T5):

```text
fs/{system}/{operation}/{restaurant_id}/{object_id}/{outbox_message_id}
# example: fs/nomina360/create_employee/ben-playa/cand_9f31/ob_5c02
```

`object_id` is the FirstShift entity id (candidate, application, shift), so
the same logical operation replayed always derives the same key;
`outbox_message_id` is embedded so any log line maps back to one message.
IT can query one person's full write history by idempotency key. Outbound
HTTP carries the key in the `Idempotency-Key` header.

---

## 1. HireDesk (ATS)

- **Role:** mirror only. FirstShift's own record is authoritative; HireDesk
  is mirrored for Talent reporting (T-jordi-16 to T-jordi-20).
- **Endpoints:** `POST /requisitions`, `POST /candidates`,
  `POST /applications`, `PATCH /applications/{id}/stage`; inbound webhook
  `POST /webhooks/hiredesk` (FirstShift side) for `new_application` events.
- **Auth:** service account token on the gateway. Scope needed: read/write
  applications and requisitions for the pilot restaurants only. Reason: the
  mirror must read the inbound application events and write stage updates;
  nothing else. (Token details: build-time confirmation, see open items.)
- **Rate limits:** generous (T-hugo-12); no client-side limiter.
- **Writes FirstShift performs:**
  1. Create a requisition when a forecast or a manager opens hiring
     (`fs/hiredesk/create_requisition/...`).
  2. Create the mirrored candidate record
     (`fs/hiredesk/create_candidate/...`).
  3. Create the in-flight application
     (`fs/hiredesk/create_application/...`).
  4. Update the application stage after every human decision
     (`fs/hiredesk/update_stage/...`), carrying the `decision_id` of the
     human Decision record (C-L6) and the rejection reason, so rejections
     stop disappearing (T-jordi-18).
- **Inbound webhooks:** `new_application` events are deduplicated on the
  webhook event id; the gateways delivery is at-least-once at best
  (T-hugo), so duplicates are expected and handled.
- **Failure modes handled (specs/06 §1):**
  - Duplicate webhook delivery: deduplicated on `event_id`; a replay
    returns `{"status": "duplicate"}` and changes nothing.
  - Out-of-order stage events: the event stream is reconstructed by the
    monotonic per-application sequence (`effective_stage`); arrival order
    never decides the stage.
  - Candidate merged upstream: a 409 with code `candidate_merged` raises
    `HireDeskCandidateMergedError` carrying the surviving application id;
    the mirror write is reconciled manually, never silently dropped.
  - Requisition closed mid-flow: a 409 with code `requisition_closed`
    raises `HireDeskRequisitionClosedError`; the stage update stops and a
    human reconciles the mirror.

## 2. Nómina360 (HRIS and payroll)

- **Role:** one write only: employee creation for validated, consented
  candidates, requested by People Ops (C-L9, T-sofia-04). No contract
  signing, no alta registration capability in FirstShift.
- **Endpoints:** `POST /employees` (creation), `GET /exports/employees.csv`
  (nightly export, the only trusted read path). On-premise, reached through
  the self-maintained gateway (T-hugo-10); EU data residency non negotiable
  (T-hugo-22).
- **Auth:** gateway service token. Scope needed: create employees and read
  the nightly export. Reason: that is the entire write path; FirstShift
  never reads or writes payroll data beyond it. Personal document contents
  never travel to Nómina360: the payload references document ids only
  (architecture rule 5).
- **Rate limit:** 60 requests/min, enforced by a client-side token bucket in
  the adapter (`TokenBucket`) so the gateway limit is never tested; the
  bucket serializes the June/July registration waves (T-sofia-24). A gateway
  429 maps to `PortRateLimitedError`. Throttling behavior beyond that is
  undocumented, so any non-conforming throttle response is
  `PortProtocolError`: no retry against unknown behavior, alert IT.
- **The quirk (C-T3):** validation failures return **HTTP 200 with an error
  body**. The adapter validates every response by body, never by status
  code (`parse_response`): a non-ok body raises `Nomina360ValidationError`
  (never retried, never recorded as success), a malformed body raises
  `PortProtocolError`, and a success body with an odd HTTP status is also a
  `PortProtocolError`. This makes the July incident impossible (T-hugo-20).
- **Writes FirstShift performs:**
  1. Create the employee after People Ops approves the pack
     (`fs/nomina360/create_employee/...`). Idempotent on the candidate id:
     a replay returns the same `employee_ref` and creates no duplicate.
- **Partial creation:** the employee row can exist while the call returned
  an error body. The typed error surfaces, and the idempotent replay then
  reports success with the same ref; the nightly CSV is the final word.
- **Reconciliation job (O12, nightly):** the CSV is truth (C-T4, T-hugo-18):
  "what is in the file is what is actually in the system". Each night the
  worker parses the CSV snapshot and matches every outbox message in
  `api_confirmed` on `nomina360_employee_ref`:
  - Found: the message becomes `csv_confirmed` and the O11 tracker may
    signal `ready_for_rota`.
  - Absent: the message is downgraded, a `ReconciliationTask` opens for
    People Ops (the record fix) with the runbook compensating action, and
    IT gets the alert for the gateway side. The task stays open until
    resolved and `ready_for_rota` stays unsignaled meanwhile.
  - CSV rows with no FirstShift write are reported as `unexpected_in_csv`
    for People Ops to classify.
  The reconciliation helper is `app/adapters/nomina360.py::reconcile`; the
  ownership split (record fix to People Ops, gateway investigation to IT)
  mirrors the write-approver rows in `discovery/systems-and-data.md`.
- **Confirmation semantics:** `api_confirmed` is a weak signal. The write is
  not counted as confirmed until the next nightly CSV shows it, so the
  commitment engine books confirmation time, not API time, near the
  Thursday rota lock.

## 3. ShiftGrid (workforce management)

- **Role:** read open shifts, read rotas, assign and release shifts for
  people who already exist in Nómina360 (the core guards this, T-sofia-20).
- **Endpoints:** `GET /restaurants/{id}/open-shifts`, `GET /shifts/{id}`,
  `GET /rotas?week=YYYY-MM-DD`, `POST /shifts/{id}/assign`,
  `POST /shifts/{id}/release`.
- **Auth:** service account token. Scope needed: read rotas and open
  shifts, write assignments. Reason: the agent offers open shifts and the
  relay writes the accepted assignment; nothing else. (Auth details:
  build-time confirmation.)
- **Rate limits:** standard; assignments are idempotent on the key so a
  retry never double books (T-raul-18).
- **Writes FirstShift performs:**
  1. Assign a shift to a confirmed employee
     (`fs/shiftgrid/assign_shift/...`).
  2. Release a shift the person cannot work
     (`fs/shiftgrid/release_shift/...`).
- **Optimistic check:** before confirming an assignment the adapter reads
  the shift; if the manager filled it manually meanwhile (a 409
  `shift_filled`), the adapter re-checks and raises
  `ShiftGridShiftFilledError` carrying who took it. A lost race is never
  retried; the agent offers another shift.
- **Rota publication cycle:** the rota locks Thursdays; the following
  week's rota publishes on the Thursday before its Monday. `get_rota`
  returns the publication state so callers respect the cycle instead of
  discovering it at write time.
- **Timezones and DST:** ShiftGrid sends shift times as naive local ISO
  strings plus the `local_timezone`. The adapter converts with the zone's
  rules (fold=0 for the spring-forward gap) and every datetime leaving the
  adapter is aware UTC. Spain (Europe/Madrid) and Portugal (Europe/Lisbon)
  are the zones in the pilot.

## 4. TillCloud (POS, read-only)

- **Role:** 15-minute sales slices and the derived labor forecast that
  drive forecast-driven requisitions (O3, phase 2). Read-only by design: no
  write methods exist on the port.
- **Endpoints:** `GET /restaurants/{id}/sales?granularity=15m`,
  `GET /restaurants/{id}/forecast`.
- **Auth:** read-only API key. Scope needed: read sales and forecast for
  the pilot restaurants. Reason: reads only, so the key cannot mutate
  anything.
- **Writes FirstShift performs:** none.

## 5. LearnBite (LMS)

- **Role:** enroll consented candidates in the food hygiene module and
  track completion; the module is the binary gate for food contact on day
  1, never for hiring or an offer (T-iker-06, C-L8).
- **Endpoints:** `POST /enrollments`, `GET /enrollments/{id}`,
  `GET /enrollments?candidate_id=...`; inbound webhook
  `POST /webhooks/learnbite` (FirstShift side) for `enrollment_completed`.
- **Auth:** service account token. Scope needed: create enrollments and
  read enrollment status. Reason: enrollment and completion tracking is the
  whole integration; FirstShift never touches course content. (Auth
  details: build-time confirmation.)
- **Rate limits:** default ("small stuff", T-hugo-12).
- **Writes FirstShift performs:**
  1. Enroll a consented candidate in `food_hygiene`
     (`fs/learnbite/enroll/...`), carrying the consent id (O5).
- **Failure modes handled (specs/06 §1):**
  - Late completion webhooks: completion events are deduplicated on the
    event id, and a webhook that arrives after polling already learned the
    completion changes nothing.
  - Re-enrollment: a failed module re-enrolls into a fresh enrollment; the
    adapter resolves the authoritative status with `latest_status_for`.
  - Completion without webhook: `get_enrollment_status` polls the
    enrollment API as the fallback, so a lost webhook delays nothing.
- **Downstream effect:** completion flips the core guard that either clears
  `requires_food_hygiene` shifts or schedules day 1 as till/FOH and tells
  the trainer in advance (T-iker-06, T-iker-20).

## 6. M365 (email and calendar, Graph API)

- **Role:** best-effort interview scheduling and the People Ops document
  request email. Manager calendars are used inconsistently today, so
  interview slots come from the manager's WhatsApp replies first.
- **Endpoints:** `GET /calendars/{manager_id}`, `POST /events`,
  `POST /mail`.
- **Auth:** Graph app registration (build-time confirmation) with
  `Calendars.ReadWrite` for the service account and `Mail.Send`. Reason:
  read the manager's free slots and write the interview event; the mail
  scope only sends the document request to People Ops, replacing the
  three-person template chase (T-sofia-16). Candidate first names only
  travel here; documents never do.
- **Rate limits:** Graph throttling defaults; a 429 maps to
  `PortRateLimitedError`.
- **Writes FirstShift performs:**
  1. Create the interview event after the manager picks a slot
     (`fs/m365/create_interview_event/...`).
  2. Send the document request email to People Ops
     (`fs/m365/send_email/...`).
- **No calendar slots:** when the manager's calendar holds no slots, the
  agent falls back to proposing slots through WhatsApp quick replies (at
  most 3, C-O2) via `propose_slots_via_whatsapp`; calendar conflicts
  surface as `PortValidationError` and the agent re-asks in WhatsApp.

## 7. WhatsApp channel (Twilio)

- **Role:** the governed conversation channel with candidates and managers,
  replacing the shadow-IT personal phones (T-laura-12, T-hugo-26); gives
  the DPO searchable, erasable, consented conversations.
- **Endpoints (Twilio REST, 2010-04-01):** `POST
  /Accounts/{AccountSid}/Messages.json`; inbound webhooks
  `POST /webhooks/whatsapp` (messages) and the status callback for
  delivery/read receipts, both on the FirstShift side.
- **Auth:** Twilio subaccount with an API key (SK sid + secret) as basic
  auth; the subaccount auth token validates inbound webhook signatures.
  Reason: credentials can be revoked per project without touching the
  parent account, and credits draw from the parent balance. The signature
  check (`X-Twilio-Signature`) runs before any inbound payload is parsed.
- **Rate limits:** Twilio's WhatsApp throughput; the adapter maps 429 and
  5xx to transient errors for the relay, plus a per-recipient cap so a
  broken conversation cannot be spammed.
- **Writes FirstShift performs:**
  1. Send the outbound WhatsApp message
     (`fs/whatsapp/send/{restaurant_id}/{object_id}/{outbox_message_id}`).
  2. (Templates registered in the Twilio account; that registration is a
     client-side setup step, not a FirstShift write.)
- **24h customer service window:** free-form messages are only allowed
  within 24 hours of the recipient's last inbound message. Outside the
  window the send must carry a pre-approved template (ContentSid +
  variables); without one the adapter refuses locally
  (`TwilioChannelWindowClosedError`) instead of failing at the carrier.
- **Templates:** template sends post `ContentSid` and `ContentVariables`.
  The template set for the pilot (interview invitation, offer, document
  reminder, shift confirmation) is registered with Twilio before wave 1.
- **Delivery and read receipts:** status callbacks are recorded per
  provider message sid (`handle_status_callback`, `receipt_status`), so the
  console can show delivered/read state per message.
- **Opt-out keywords:** an inbound `STOP`, `STOPALL`, `UNSUBSCRIBE`,
  `CANCEL`, `END`, `ALTO`, `BAJA` or `DAR DE BAJA` (EN and ES) marks the
  recipient opted out; every further send to that recipient is rejected
  locally and the nudge timers stop.
- **Media:** inbound media messages are accepted and referenced by id;
  candidate documents are uploaded through the EU-hosted, candidate-direct
  link instead of WhatsApp attachments, so documents never live in the
  channel.

## 8. Fault injection (test harness)

The mock client systems reproduce every failure mode above deterministically
(`mocks/faults.py`): a test (or an operator, via `POST /__faults` on a live
mock server) toggles one fault per system with explicit parameters, and the
mock responds exactly as the real system would. The registry holds no
ambient state: faults are off unless injected and cleared on app startup.
The failure-mode tests in `tests/test_adapter_failures.py` cover one test
per row of specs/06 section 1, all offline and deterministic.
