# Systems and data inventory: crew hiring and onboarding

- **Scope:** every system a crew hire touches from application to first shift, plus the channels that carry the real process.
- **Evidence:** the integration surface table in `specs/00-client-brief.md` section 3, the transcript citations shown inline, and `discovery/ride-along-benidorm.md` for observed copy-paste behavior. Anything not stated in evidence is marked as unknown for Phase 2, not guessed.
- **Read/write capability legend:** Read = the system can serve data out. Write = the system can accept data in. API = documented interface exists.

---

## 1. HireDesk (ATS)

- **Owner:** Talent Acquisition (Jordi Puig). `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Requisition, candidate, application, stage, notes, rejection reason. [T-hugo-04]; [T-laura-04] "requisitions, CVs, stages, notes" |
| Source of truth for | Requisition and application intake in theory. In practice unreliable: stages are not closed, candidates are duplicated, rejections are not recorded, and managers log shadow hires after the fact, so the funnel data is, in the Head of TA's own words, garbage. Only the application date and the phone number are trusted. [T-jordi-16, T-jordi-18, T-jordi-20]; [T-yolanda-18] |
| Read | REST API (requisitions, candidates, stages). `specs/00-client-brief.md` section 3 |
| Write | REST API, plus webhooks on new application. `specs/00-client-brief.md` section 3 |
| Latency | Real-time API. Webhook delivery semantics (at-least-once vs at-most-once) were not confirmed in interview; flagged as an IT open question [T-hugo, interviewer notes] |
| Rate limits | "Generous rate limits, real webhooks, no problem." [T-hugo-12] |
| Auth | "That at least has access controls." [T-laura-04]. SSO and token details: not stated in evidence, confirm in Phase 2 |
| Known quirks | (1) Data hygiene: unclosed stages, duplicates, post-hoc entries [T-jordi-16, T-jordi-18, T-jordi-20]. (2) Retention: candidate records are kept forever by default, nobody configured deletion and nobody owns the job [T-laura-08, T-laura-10]. (3) Nobody maintains the vacancies: requisitions are published by the HRBP or on manager request, sometimes with the old salary [T-jordi-26] |
| Write access approver | Jordi Puig (system owner), Hugo Andrade (integration), Laura Cebrián (DPIA signature before any candidate data is processed [T-laura-28]) |

## 2. Nómina360 (HRIS and payroll)

- **Owner:** People Ops / Payroll (Sofía Marques). `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Employee record, contract registration, alta (social security registration), payroll data. [T-hugo-04]; [T-sofia-04, T-sofia-06] |
| Source of truth for | Employment: "until payroll creates them, I cannot schedule them, full stop." [T-yolanda-20] |
| Read | Nightly CSV export. This is the only reliable read: "what is in the file is what is actually in the system." [T-hugo-06, T-hugo-18] |
| Write | REST API for employee creation only. No webhooks at all. [T-hugo-06] |
| Latency | Write: real-time API call. Read: nightly batch. Anything written during the day is not verifiable until the next CSV [T-hugo-18] |
| Rate limits | 60 requests per minute, "and it is not a suggestion." Throttling behavior does not match the documentation. [T-hugo-14] |
| Auth | On-premise behind the network, every call goes through a self-maintained gateway [T-hugo-10]. EU data residency is non negotiable [T-hugo-22] |
| Known quirks | (1) **Returns HTTP 200 with an error body on validation failures**, so a client that checks only the status code believes the write succeeded while the employee does not exist [T-hugo-16]. (2) Documented incident: a contractor script created employees, checked the 200s, reported success; three weeks later payroll found dozens of people missing and rebuilt records from the CSV by hand [T-hugo-20]. (3) Employee creation takes 3 to 6 days end to end in practice [T-yolanda-20]. (4) Any vendor write must be idempotent (a key IT controls, retry updates or no-ops) and logged, queryable by that key, or IT says no [T-hugo-22, T-hugo-24] |
| Write access approver | Hugo Andrade (integration, idempotency and logging [T-hugo-22]), Sofía Marques (payroll owner), Laura Cebrián (EU residency and audit trail [T-laura-18, T-laura-22]) |

## 3. ShiftGrid (workforce management / scheduling)

- **Owner:** Operations (Raúl Sempere's area uses it). `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Shift, rota, open shift, labor forecast. [T-hugo-04, T-hugo-06] |
| Source of truth for | Published rota. Not for coverage reality: managers overwrite the labor forecast "so it does not come out red", and the Area Ops Director trusts phone calls, not the screen [T-raul-18, T-raul-20] |
| Read | REST API for rotas and open shifts. `specs/00-client-brief.md` section 3 |
| Write | REST API for rotas and open shifts. `specs/00-client-brief.md` section 3 |
| Latency | Real-time API, but the rota only locks on Thursdays, so anything that wants tomorrow's rota is out of luck [T-hugo-12] |
| Rate limits | Not stated in evidence; Hugo's assessment is "fine" [T-hugo-12] |
| Auth | Not stated in evidence, confirm in Phase 2 |
| Known quirks | (1) A person cannot be added until they exist in Nómina360, so managers leave new hires as "TBC" in the draft [T-yolanda-20; ride-along, 22:20 row]. (2) Forecast field is manually overwritten by about half the managers, which is why area coverage intelligence lives in phone calls [T-raul-18, T-raul-20]. (3) New hires learn shifts the night before or via crew WhatsApp groups, not from the system [T-churned-08, T-churned-16; T-candidate-a-16, T-candidate-a-18] |
| Write access approver | Raúl Sempere / Operations (rota data), Hugo Andrade (integration) |

## 4. TillCloud (POS)

- **Owner:** Finance / Ops. `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Sales data at 15-minute granularity; derived labor forecast, refreshed weekly. `specs/00-client-brief.md` section 3 |
| Source of truth for | Sales. Not for labor demand in practice: the forecast is overwritten downstream in ShiftGrid [T-raul-18] |
| Read | Read-only sales API at 15-minute granularity. `specs/00-client-brief.md` section 3 |
| Write | None. Read-only by design |
| Latency | 15-minute granularity for sales; weekly for the derived forecast (`specs/00-client-brief.md` section 3) |
| Rate limits | Not stated in evidence |
| Auth | Not stated in evidence, confirm in Phase 2 |
| Known quirks | Not a hiring system, but it decides why hiring happens at all: its sales data feeds the labor forecast [T-hugo-04]. Separately, service degradation when understaffed is measurable: 312 s vs 228 s average drive-thru time (`specs/00-client-brief.md` section 4) |
| Write access approver | N/A, read-only. Read access: Finance / Ops owner plus Hugo Andrade |

## 5. LearnBite (training / LMS)

- **Owner:** Training team. `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Enrollment, completion (per module). [T-hugo-04, T-hugo-06] |
| Source of truth for | Training completion. The food hygiene module completion is the binary gate for food contact on day 1 [T-iker-06] |
| Read | Enrollment API. [T-hugo-06] |
| Write | Enrollment API; completion arrives via webhooks. [T-hugo-06] |
| Latency | Real-time API and webhooks. Completion status reaches the restaurant only on the morning of day 1 in practice, because nobody tells the trainer in advance [T-iker-08] |
| Rate limits | "Small stuff." [T-hugo-12] |
| Auth | Not stated in evidence, confirm in Phase 2 |
| Known quirks | (1) The day-1 constraint is binary: without the hygiene module the new hire cannot touch food, "ni un pan", so they spend day 1 on till or cleaning [T-iker-06, T-iker-08, T-iker-10]. (2) 2 of the last 5 new hires at Benidorm Playa arrived without having started the module [T-iker-08]. (3) The trainer is never told a new hire is coming: "a mí nadie me llama" [T-iker-20] |
| Write access approver | Training team owner (curriculum and enrollments), Hugo Andrade (integration), Laura Cebrián (candidate/employee data) |

## 6. Microsoft 365 (email and calendar)

- **Owner:** IT. `specs/00-client-brief.md` section 3.

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Email with document attachments (contracts, ID scans, bank certificates), manager calendars. [T-sofia-08]; `specs/00-client-brief.md` section 3 |
| Source of truth for | Nothing. It is a transport layer, but today it is the de facto carrier of the document pack |
| Read | Graph API exists. `specs/00-client-brief.md` section 3 |
| Write | Graph API; calendars for managers are used inconsistently. `specs/00-client-brief.md` section 3 |
| Latency | Real-time; human latency dominates (documents sit in inboxes, are scanned in Friday batches, or wait in a drawer for a week [T-sofia-08]) |
| Rate limits | Not stated in evidence |
| Auth | Not stated in evidence, confirm in Phase 2 |
| Known quirks | (1) Documents arrive as sideways or blurred phone photos [T-sofia-08]. (2) The late documents are always the same three: bank account certificate, social security number, food hygiene certificate [T-sofia-10]. (3) The document chase runs through three people: payroll template email, call to the manager, manager to candidate on WhatsApp [T-sofia-16]. (4) A wrong bank account number is caught at payday, not at arrival [T-sofia-30] |
| Write access approver | Hugo Andrade (IT owner), Laura Cebrián (any candidate document processing) |

## 7. WhatsApp (personal numbers and restaurant groups)

- **Owner:** Nobody. Shadow IT. `specs/00-client-brief.md` section 3; [T-hugo-26]

| Aspect | Evidence-based finding |
|---|---|
| Data objects | Candidate and new-hire conversations, the manager's "maybes" pool (~25 names), availability details, shift swaps, first-shift information, photos including ID documents. [T-yolanda-14, T-yolanda-16]; [T-laura-06]; [T-churned-10, T-churned-20] |
| Source of truth for | The real scheduling and gap-covering process, and the fastest hiring channel in the company. Also, informally, availability: candidates state their real hours in chat while the HireDesk dropdown gets a false "completa" [T-candidate-a-20; T-candidate-c-20] |
| Read | None in a governed sense: IT cannot back it up, audit it or turn it off [T-hugo-26] |
| Write | None via API. All writes are humans typing |
| Latency | Minutes, which is exactly why it wins over every official channel [T-candidate-a-10]: applied at 18:00, reply before 19:00, hired over six silent competitors |
| Rate limits | Not applicable (no API surface in evidence) |
| Auth | Personal numbers, personal devices, per-restaurant groups [T-hugo-26, T-laura-06] |
| Known quirks | (1) It holds candidate personal data with zero governance and blocks data subject access and deletion requests: "no puedo borrar lo que no sé que existe" [T-laura-12]. (2) The DPO names it, together with forever-retention, as the biggest compliance exposure, and would treat a governed channel as a compliance improvement, not a risk [T-laura-14, T-laura-24]. (3) Chasing and scheduling depend on whoever answers fastest [T-sofia-16; T-churned-10] |
| Write access approver | N/A for the current channel. A governed replacement: Laura Cebrián (explicit consent with timestamp and notice version [T-laura-26]), Hugo Andrade (EU hosting, logs [T-hugo-28]), and usage acceptance from managers via Raúl Sempere, who will veto any new portal or password [T-raul-26] |

---

## Key finding, tested: no system owns the transition from "hired" to "on the rota"

**Verdict: confirmed.** The evidence chain:

1. **The trigger is verbal and unrecorded.** The hire happens in a conversation (interview, WhatsApp, walk-in). No system object changes state at the moment of "she said yes" [T-yolanda-08, T-yolanda-16]. HireDesk only learns about many hires weeks later, entered manually so the numbers fit [T-yolanda-18; T-jordi-20].
2. **Nómina360 owns employability but not scheduling, and it is slow.** Employee creation takes 3 to 6 days and is the hard gate: "until payroll creates them, I cannot schedule them, full stop" [T-yolanda-20]. Its write path is fragile (HTTP 200 with error body, 60 req/min) and its read path is nightly-only [T-hugo-14, T-hugo-16, T-hugo-18].
3. **ShiftGrid owns the rota but cannot act until Nómina360 finishes.** Managers leave the new hire as "TBC" in the draft rota because the payroll record is still pending [T-yolanda-20; ride-along, 22:20 row]. There is no integration evidence connecting Nómina360 and ShiftGrid; the connection is the manager re-keying data by hand (ride-along, copy-paste events 2 and 4).
4. **People Ops owns registration but not the start date.** Payroll's definition of ready is registration, alta and complete documents; "managers see it differently... ellos quieren a la gente el sábado" [T-sofia-18, T-sofia-20].
5. **The gap is filled informally, with compliance exposure.** Managers sometimes put people on the rota before registration; people have worked a week or two with no alta, requiring retroactive regularization [T-sofia-20, T-sofia-22]. The observed 11-day hired-to-rota case [T-yolanda-10] sits inside the 9-day median from verbal offer to first worked shift (`specs/00-client-brief.md` section 4).

So the transition exists only as a relay of handoffs between four owners (TA, People Ops, payroll system, operations) with no owning system, no shared state, and a 3-to-6-day system-imposed wait in the middle. The one role that bridges it is the restaurant manager, by WhatsApp, overtime and hoping [T-yolanda-22].

## Data object ownership

| Data object | System of record (nominal) | Where it actually lives today | Evidence |
|---|---|---|---|
| Requisition | HireDesk | HireDesk, but unmaintained: published by HRBP or on request, sometimes with stale salary | [T-jordi-26] |
| Candidate | HireDesk | Split: formal record in HireDesk; the hottest candidates live in managers' personal WhatsApp (maybes pool, walk-ins, photos of IDs) | [T-laura-04, T-laura-06]; [T-yolanda-14] |
| Application | HireDesk | HireDesk, unreliable: duplicates, post-hoc entries, silent stack | [T-jordi-16, T-jordi-20] |
| Stage / rejection reason | HireDesk | Not trustworthy: stages unclosed, rejections unrecorded | [T-jordi-16, T-jordi-18] |
| Availability | HireDesk (form dropdown) | In practice: chat conversations and the manager's head; the dropdown gets a false "completa" | [T-candidate-a-20]; [T-candidate-c-20]; [T-churned-14] |
| Interview outcome / offer | Nowhere | Conversation and manager's phone notes | [T-jordi-20] |
| Candidate documents (ID, bank, SS, hygiene cert) | Nómina360 (on registration) | Email attachments, phone photos, drawers, payroll's flag spreadsheet | [T-sofia-08, T-sofia-10, T-sofia-16] |
| Consent | Nowhere | Not captured with timestamp and notice version anywhere in evidence | [T-laura-26] |
| Employee / contract / alta | Nómina360 | Nómina360, reliably, once created (3 to 6 days after signing) | [T-yolanda-20]; [T-sofia-04, T-sofia-06] |
| Shift / rota / open shift | ShiftGrid | ShiftGrid, but new hires are "TBC" until Nómina360 finishes, and shift info reaches people via WhatsApp | [T-hugo-12]; [T-yolanda-20]; [T-candidate-a-16] |
| Labor forecast | TillCloud to ShiftGrid (derived) | Overwritten by managers in ShiftGrid; real coverage intelligence is the area director's memory and phone | [T-raul-18, T-raul-20] |
| Enrollment / module completion | LearnBite | LearnBite, but completion status reaches the trainer on the morning of day 1 | [T-iker-08]; [T-hugo-06] |
| Hiring decision audit trail | Nowhere | No end-to-end record of who decided what and when; flagged as a compliance gap | [T-laura-14, T-laura-18] |
