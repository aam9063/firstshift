# Integration contracts: FirstShift ports

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 7, S4).
- **Rule (spec, verbatim):** "for each port, the methods, payloads (Pydantic models), error semantics, retry policy, idempotency key, and the mapping to the mock API. Include the Nómina360 quirk (HTTP 200 with error body) and how the adapter turns it into a typed error."
- **Evidence basis:** the per-system rows in `discovery/systems-and-data.md` (capabilities, quirks, write approvers) are referenced here, not duplicated. Unstated facts (auth details, undocumented limits) are marked as build-time confirmations, never guessed.

## Shared conventions

- **No direct database access, ever (C-T1):** every port talks only to the documented API surface ([T-hugo-22]).
- **All writes go through the outbox** (`OutboxMessage`, ADR-003); agents and the core never call a client system inline. The relay worker delivers with retries and records every attempt so IT can query one person's write history by idempotency key (C-T6, [T-hugo-22, T-hugo-30]).
- **Idempotency key scheme (C-T5, [T-hugo-24]):** a key IT controls, generated once when the message enters the outbox and stable across retries:

  ```text
  fs/{system}/{operation}/{restaurant_id}/{object_id}/{outbox_message_id}
  # example: fs/nomina360/create_employee/ben-playa/cand_9f31/ob_5c02
  ```

  `object_id` is the FirstShift entity id (candidate, application, shift), so the same logical operation replayed always derives the same key; `outbox_message_id` is embedded so any log line maps back to one message.
- **Error taxonomy (every port raises one of these, never a raw HTTP error):**

  | Type | Meaning | Default handling |
  |---|---|---|
  | `PortTransientError` | timeout, 5xx, network | retry with backoff |
  | `PortRateLimitedError` | explicit throttle signal | wait per the signal, then retry |
  | `PortValidationError` | the system rejected the payload | never retried; task for a human with the field errors |
  | `PortProtocolError` | a response that does not match the documentation | no retry; alert IT (C-T2) |
  | `PortAuthError` | credentials or gateway rejected the call | no retry; page IT |

- **Default retry policy:** 5 attempts, exponential backoff 1s, 4s, 16s, 60s with jitter; after the last attempt the outbox message is `failed`, an AuditEvent records it, and Prometheus fires the alert. Ports override per their evidence below.

---

## 1. HireDeskPort (ATS)

Evidence: `discovery/systems-and-data.md` section 1. Real-time REST plus webhooks on new application; generous rate limits [T-hugo-12]; data hygiene is the known weakness, so FirstShift's own record is authoritative and HireDesk is mirrored for Talent reporting [T-jordi-16 to T-jordi-20].

```python
class RequisitionCreate(BaseModel):
    restaurant_id: str
    role: str
    target_open_shift_ids: list[str]   # ADR-002: the requisition mirrors shift reality
    opened_by: str                     # human owner on record

class StageUpdate(BaseModel):
    hiredesk_application_id: str
    stage: Literal["screening", "interview", "offer", "hired", "rejected"]
    rejection_reason: str | None       # recorded, so rejections stop disappearing [T-jordi-18]
    decision_id: str                   # links the human Decision record (C-L6)
```

Methods: `create_requisition(payload)`, `create_candidate(payload)`, `create_application(payload)`, `update_stage(payload)`, plus inbound `handle_application_webhook(event)`.

- **Error semantics:** standard taxonomy. A rejected stage update (for example an unknown application id) is `PortValidationError` and reconciled manually against the mirror, not silently dropped.
- **Retry policy:** default. Writes are idempotent on the key; HireDesk duplicates are the system's own disease [T-jordi-16], so the mirror never retries a successful write.
- **Webhook delivery semantics:** at-least-once vs at-most-once unconfirmed [T-hugo, interviewer notes]; the gateway deduplicates on the webhook event id either way.
- **Mock API:** `mocks/hiredesk` serves `POST /requisitions`, `POST /candidates`, `POST /applications`, `PATCH /applications/{id}/stage`, and emits `POST /webhooks/new-application` to FirstShift.

## 2. Nomina360Port (HRIS and payroll)

Evidence: `discovery/systems-and-data.md` section 2. Employee-creation REST only, no webhooks, on-premise behind a self-maintained gateway [T-hugo-10]. The write path is limited to validated employee-creation payloads routed through People Ops' flow; no contract signing, no alta registration capability in FirstShift (C-L9, [T-sofia-04]).

```python
class EmployeeCreate(BaseModel):
    candidate_id: str                  # becomes the external ref for idempotency
    first_name: str
    last_name: str                     # required only here: Nómina360 registration needs it
    document_refs: list[str]           # Document.ids; contents never leave storage (architecture rule 5)
    contract_ref: str                  # signed by People Ops, referenced not carried
    requested_by: str                  # People Ops actor; FirstShift never requests a creation on its own
```

**The quirk (C-T3, [T-hugo-16, T-hugo-20]):** validation failures return **HTTP 200 with an error body**. The adapter validates every response by body, never by status code:

```python
class Nomina360Body(BaseModel):
    status: Literal["ok", "error"]
    error_code: str | None
    message: str | None
    field_errors: list[str] = []

def parse_response(http_status: int, body: bytes) -> dict:
    parsed = Nomina360Body.model_validate_json(body)   # malformed body = PortProtocolError
    if parsed.status != "ok":
        raise Nomina360ValidationError(                # subclass of PortValidationError
            code=parsed.error_code, fields=parsed.field_errors)
    if http_status != 200:                             # documented code with a success body: still odd
        raise PortProtocolError(f"nomina360 returned {http_status} with a success body")
    return parsed.model_dump()
```

An injected error-body-200 fixture is detected as `Nomina360ValidationError`, retried never, recorded never as success; this is the exact July incident made impossible [T-hugo-20].

- **Rate limit (C-T2, [T-hugo-14]):** 60 requests/min enforced by a client-side token bucket, so the limit is never tested; throttling behavior is undocumented, so any non-conforming throttle response is `PortProtocolError`: no retry against unknown behavior, alert IT.
- **Retry policy:** transient errors retried on the default schedule; the token bucket serializes bursts (registration waves in June/July [T-sofia-24]).
- **Confirmation semantics:** `api_confirmed` is a **weak** signal; the write is not counted as confirmed until the next nightly CSV shows it (C-T4, [T-hugo-18]). Until then the O11 tracker holds the write as pending and `ready_for_rota` stays unsignaled.
- **Read path:** there is no trusted API read; the port exposes `fetch_nightly_csv(date) -> CsvSnapshot` used by reconciliation.
- **Mock API:** `mocks/nomina360` serves `POST /employees` (programmable to return the 200-with-error-body fixture), and `GET /exports/employees.csv` (nightly file with a controllable lag).

## 3. ShiftGridPort (workforce management)

Evidence: `discovery/systems-and-data.md` section 3. REST for rotas and open shifts; the rota locks Thursdays, so anything wanting tomorrow's rota is out of luck [T-hugo-12]; a person cannot be added until they exist in Nómina360, which is why managers leave "TBC" rows [T-yolanda-20].

```python
class OpenShiftRead(BaseModel):
    shiftgrid_shift_id: str
    restaurant_id: str
    starts_at: datetime
    ends_at: datetime
    role: Literal["kitchen", "till", "foh", "drive_thru"]

class ShiftAssign(BaseModel):
    shiftgrid_shift_id: str
    nomina360_employee_ref: str        # guard: assignment only after csv_confirmed alta (O12)
    or_people_ops_exception_id: str | None
```

Methods: `list_open_shifts(restaurant_id, window)`, `get_rota(employee_ref, window)`, `assign_shift(payload)`, `release_shift(payload)`.

- **Error semantics:** standard taxonomy. `assign_shift` refuses at the core guard, not at the adapter, when neither CSV confirmation nor a recorded People Ops exception exists (T-sofia's hard line on unregistered people working [T-sofia-20]).
- **Retry policy:** default; idempotent assign on the key prevents double booking on retry [T-raul-18 context: coverage errors are the pain this avoids].
- **Thursday lock:** modeled in core policy (the O11 `rota_unlock_date`), not discovered at write time.
- **Mock API:** `mocks/shiftgrid` serves `GET /restaurants/{id}/open-shifts`, `GET /rotas`, `POST /shifts/{id}/assign`, with a configurable "locks on Thursday" fixture.

## 4. TillCloudPort (POS, read-only)

Evidence: `discovery/systems-and-data.md` section 4. Read-only by design; no write methods exist on the port.

```python
class SalesSlice(BaseModel):
    restaurant_id: str
    interval_start: datetime           # 15-minute granularity
    sales_eur: float
```

Methods: `get_sales(restaurant_id, window)` and `get_labor_forecast(restaurant_id)` (derived weekly).

- **Error semantics / retry:** standard; reads are cacheable, so a failed read never blocks a conversation (forecast-driven requisitions are O3, phase 2).
- **Mock API:** `mocks/tillcloud` serves `GET /restaurants/{id}/sales?granularity=15m` and `GET /restaurants/{id}/forecast`.

## 5. LearnBitePort (LMS)

Evidence: `discovery/systems-and-data.md` section 5. Enrollment API plus completion webhooks; the food hygiene module is the binary gate for food contact on day 1, never for hiring or an offer [T-iker-06, C-L8].

```python
class EnrollmentCreate(BaseModel):
    candidate_id: str
    module_key: Literal["food_hygiene"]
    consent_id: str                    # pre-boarding only runs on consented candidates (O5)

class EnrollmentStatus(BaseModel):
    learnbite_enrollment_id: str
    status: Literal["enrolled", "completed", "failed"]
    completed_at: datetime | None
```

Methods: `enroll(payload)`, `get_enrollment_status(enrollment_id)`, plus inbound `handle_completion_webhook(event)`.

- **Error semantics:** standard taxonomy. A completion webhook is deduplicated on its event id (delivery semantics unconfirmed in evidence).
- **Retry policy:** default ("small stuff" [T-hugo-12]).
- **Downstream effect:** completion flips the core guard that either clears `requires_food_hygiene` shifts or schedules day 1 as till/FOH and tells the trainer in advance [T-iker-06, T-iker-20].
- **Mock API:** `mocks/learnbite` serves `POST /enrollments`, `GET /enrollments/{id}`, and emits `POST /webhooks/completion`.

## 6. M365Port (email and calendar)

Evidence: `discovery/systems-and-data.md` section 6. Graph API; manager calendars are used inconsistently today, so interview slots come from the manager's WhatsApp replies first, with calendar writes as best effort.

```python
class InterviewEvent(BaseModel):
    manager_id: str
    candidate_ref: str                 # first name only; documents never travel here again
    starts_at: datetime
    location: str

class DocumentRequestEmail(BaseModel):
    to_person_ops: str                 # the template chase is replaced by the agent, [T-sofia-16]
    document_types: list[str]
    upload_link: str                   # EU-hosted, candidate-direct, removes the three-person chase
```

Methods: `get_manager_calendar(manager_id)`, `create_interview_event(payload)`, `send_email(payload)`.

- **Error semantics / retry:** default; calendar conflicts surface as `PortValidationError` and the agent re-asks the manager in WhatsApp.
- **Mock API:** `mocks/m365` serves `GET /calendars/{manager_id}`, `POST /events`, `POST /mail`.

## 7. MessagingChannelPort (the conversation channel)

One port, two adapters (architecture rule 2): the **simulator adapter** (default, in `simulator/`, drives the console demo and tests) and the **Twilio WhatsApp adapter** (the governed channel that gives the DPO searchable, erasable, consented conversations over today's shadow IT [T-laura-12, T-laura-14, T-hugo-26]).

```python
class OutboundMessage(BaseModel):
    recipient_ref: str                 # channel-scoped phone
    body: str                          # candidate language, never mixed
    quick_replies: list[str] = []      # at most 3 for manager decisions (C-O2)
    correlation_id: str                # event stream id, visible in the console

class InboundMessage(BaseModel):
    provider_message_id: str           # the inbound idempotency key
    sender_ref: str
    body: str
    received_at: datetime
    quick_reply_id: str | None         # one-tap manager decisions (ADR-004)
```

Methods: `send_message(payload)` (outbox-relayed like every write), `verify_webhook(request)` (Twilio signature check before parsing), `handle_inbound(payload)`.

- **Error semantics:** delivery failures are `PortTransientError` (carrier-level) and retried; a permanently unreachable number raises `PortValidationError` and stops the nudge timer instead of looping.
- **Retry policy:** default, plus a per-recipient cap so a broken conversation cannot be spammed.
- **Idempotency:** inbound on `provider_message_id`; outbound on the standard scheme (`fs/whatsapp/send/...`).
- **Mock/simulator API:** the simulator adapter is in-process (no HTTP); `simulator/` also exposes clock control so timers, cutoffs and the reconciliation job can be demonstrated deterministically.

---

## O12: nightly Nómina360 CSV reconciliation semantics

- **CSV as truth (C-T4):** "what is in the file is what is actually in the system" [T-hugo-18]. The API's own confirmations are never the final word, because HTTP 200 can wrap a validation failure [T-hugo-16, T-hugo-20].
- **Drift detection:** each night the worker parses the CSV snapshot and, for every outbox message in `api_confirmed` awaiting confirmation, matches on `nomina360_employee_ref`. Found: the message becomes `csv_confirmed` and the O11 tracker may signal `ready_for_rota`. Absent: the message is **downgraded** to `downgraded`, a `ReconciliationTask` is created for People Ops with the compensating action from the runbook (C-T7, [T-hugo-20] shows the manual cost of not doing this), and IT gets the alert, not a payday phone call [T-hugo-30]. CSV rows with no corresponding FirstShift write are reported as `unexpected_in_csv` drift for People Ops to classify.
- **Gate behavior:** `ready_for_rota_signaled_at` is set only after `csv_confirmed_at`, or after People Ops records an explicit exception (state-machine guard). The one-day confirmation lag is modeled into the commitment engine's cutoffs, so scheduling near the Thursday lock books confirmation time, not API time (O12 risk, accepted in `design/options.md`).
- **Ownership note:** who owns reconciliation when the CSV disagrees with the day's writes was an open discovery question ([T-hugo, interviewer notes]); this design assigns the record fix to People Ops and the gateway investigation to IT, which is the split their write-approver rows already reflect.

## Mock-to-real mapping

| Port | Mock module | Real adapter swap |
|---|---|---|
| HireDeskPort | `mocks/hiredesk` (REST + webhook emitter) | config: base URL + credentials |
| Nomina360Port | `mocks/nomina360` (error-body-200 fixture, CSV export) | config: gateway route + token bucket on |
| ShiftGridPort | `mocks/shiftgrid` (open shifts, Thursday lock) | config: base URL + credentials |
| TillCloudPort | `mocks/tillcloud` (15m sales) | read-only key |
| LearnBitePort | `mocks/learnbite` (enrollment + completion webhook) | config: base URL + credentials |
| M365Port | `mocks/m365` (calendar, mail) | Graph API app registration |
| MessagingChannelPort | simulator adapter (in-process) | Twilio WhatsApp adapter (env credentials) |

Swapping any mock for its real adapter is configuration, not code (architecture rule 2). Auth details for ShiftGrid, LearnBite, TillCloud and M365 are build-time confirmations flagged as unknown in `discovery/systems-and-data.md`.
