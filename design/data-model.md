# Data model: FirstShift

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 7, S4).
- **Rule (spec, verbatim):** entities "with fields, owner system and retention."
- **Companions:** `design/architecture.md` (deployment and event stream), `design/integration-contracts.md` (how entities leave the store), `design/state-machine.md` (what moves `Application.state`).

## Conventions

- **Multi-tenancy (C-O3):** every record carries `brand_id` and `restaurant_id` (where the entity is restaurant-scoped); no query crosses scope without an explicit, logged filter.
- **Data minimization (C-L3):** each field below names its use. Fields without a named use are not collected. The field list is reviewed by the DPO before the DPIA (C-X1, [T-laura-28]).
- **Owner system:** the system of record for the truth. FirstShift's Postgres stores are the system of record only for what no client system owns today (consent, screening answers, decisions, audit trail, outbox, bench, the hired-to-rota window; `discovery/systems-and-data.md` ownership table shows where those live today: mostly nowhere).
- **Retention:** pilot defaults are proposals until Laura Cebrián signs them into the DPIA. Today HireDesk keeps candidate records forever by default and nobody owns deletion [T-laura-08, T-laura-10]; C-L4 requires a schedule that actually executes, run by a worker, not a policy document.
- **Erasure (C-L5):** every entity references the candidate either directly or through `application_id`, so a single erasure request enumerates every trace, including conversation history and event payloads. Erased candidates are pseudonymized (`erased_at` set, identifiers dropped) or hard-deleted per the DPO's instruction.

---

## Restaurant

Scope reference shared by everything else.

| Field | Type | Use (C-L3 named use) |
|---|---|---|
| `id` | uuid | key |
| `brand_id` | enum (lumbre, pollo) | tenancy |
| `name`, `city`, `timezone` | str | shift matching and message copy |
| `bench_enabled` | bool | whether the bench operates here |

- **Owner system:** FirstShift (identity mirrors HireDesk/ShiftGrid site codes).
- **Retention:** life of the client relationship.

## OpenShift

The unit of work (ADR-002): a concrete ShiftGrid shift a candidate can be matched to, not an "availability" dropdown ([T-candidate-a-20, T-churned-14]: the dropdown gets a false "completa" while the real availability is stated in chat).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `restaurant_id` | fk | scope |
| `shiftgrid_shift_id` | str | link to system of record |
| `starts_at`, `ends_at` | datetime | the offer is a specific shift |
| `role` | enum (kitchen, till, foh, drive_thru) | matching and the hygiene gate |
| `requires_food_hygiene` | bool | C-L8: food-contact tasks need the module |
| `status` | enum (open, matched, filled, cancelled) | prevents double-matching |
| `matched_application_id` | fk, nullable | who won it |

- **Owner system:** ShiftGrid (rota); FirstShift caches a read model.
- **Retention:** 90 days after `ends_at` (matching evidence), then delete; ShiftGrid keeps the rota.

## Candidate

| Field | Type | Use / minimization note |
|---|---|---|
| `id` | uuid | key; also the external ref for Nómina360 idempotency (C-T5) |
| `brand_id` | enum | tenancy |
| `first_name` | str | conversation; no surname until Nómina360 registration needs it |
| `phone` | str, channel-scoped | the conversation channel; the one field discovery names as trusted in HireDesk [T-jordi-16] |
| `preferred_language` | enum (es, pt, en) | stated explicitly by the candidate, never inferred from names [T-candidate-c-22, C-O4] |
| `hiredesk_candidate_id` | str, nullable | Talent reporting; created when a requisition exists |
| `nomina360_employee_ref` | str, nullable | only after hire and People Ops registration |
| `state` | enum (state machine states) | current position, mirrored from `Application` |
| `source` | enum (qr, job_board, walk_in, bench, referral) | funnel measurement |
| `consent_status` | derived | processing gate (see Consent) |
| `erased_at` | datetime, nullable | C-L5 erasure marker |

Deliberately absent: CV text (applicants have thin or no CV; screening is conversational), age beyond the legal minimum check, nationality beyond right to work, health, family, religion (guardrails; volunteered answers are refused, not stored).

- **Owner system:** FirstShift (HireDesk holds a formal record only for reporting; the hottest candidates live in managers' personal WhatsApp today [T-laura-04, T-yolanda-14], which this replaces).
- **Retention:** 12 months after last interaction, then anonymize (C-L4). Bench entries follow their own consent expiry (see BenchEntry).

## Application

One candidate x one open-shift opportunity, carrying the state machine.

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `candidate_id`, `restaurant_id` | fk | scope and links |
| `target_open_shift_ids` | list[fk] | the shifts being filled |
| `requisition_id` | str, nullable | HireDesk requisition (Talent control and reporting, ADR-002) |
| `hiredesk_application_id` | str, nullable | mirror write |
| `state` | enum | the state machine's persisted position |
| `entered_at`, `state_changed_at` | datetime | funnel timing vs the 3.8-day first-contact baseline |

- **Owner system:** FirstShift for the live record; HireDesk nominally for applications but unreliable (duplicates, post-hoc entries [T-jordi-16, T-jordi-20]), so FirstShift's record is authoritative for the pilot and mirrored out.
- **Retention:** with the candidate.

## Consent

The record the DPO has never been able to produce ("not captured with timestamp and notice version anywhere in evidence" [T-laura-26]).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `candidate_id` | fk | whose consent |
| `channel` | enum (whatsapp, email) | C-L2: consent is per channel; sending on a non-consented channel is blocked and logged |
| `purpose` | enum (screening, preboarding, bench_reengagement) | processing basis per purpose |
| `notice_version` | str | version of the notice shown (C-L1) |
| `granted_at`, `revoked_at` | datetime | the timestamps C-L1 requires |
| `evidence_message_id` | fk | the message that carried the consent |

- **Owner system:** FirstShift (no client system owns consent).
- **Retention:** life of the candidate record plus audit reference; never deleted before the candidate.

## ScreeningAnswer

| Field | Type | Use / minimization note |
|---|---|---|
| `id` | uuid | key |
| `application_id` | fk | which application |
| `question_key` | str | versioned question (right to work, minimum age check, concrete shift fit, languages) |
| `answer_structured` | json | validated extraction from free text; the only shape tools consume |
| `free_text` | text | what the candidate actually said, needed for audit and for signals flowing back (spec section 3) |
| `free_text_summary` | text | what the manager sees; free text is summarized for humans, never scored into a hidden ranking (guardrails) |

- **Owner system:** FirstShift.
- **Retention:** with the candidate; day-30 retention and week-2 manager ratings are written back against these answers as human-revisable evidence, not auto-adjusted criteria.

## Decision

Every decision that significantly affects a candidate, with its named human (C-L6: no automated-only decisions, GDPR art. 22).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `application_id` | fk | subject |
| `type` | enum (shortlist, interview_slot, offer, not_selected, first_shift_slot, backup_activation) | what was decided |
| `recommended_by` | str (agent id, model, prompt version) | the agent's recommendation is separate from the decision |
| `decided_by` | str (human actor) | named human, per C-L6 |
| `decided_at` | datetime | when |
| `facts_seen` | fk to event/summary | the facts the human saw |

Guards enforced by the core: `offer` and `not_selected` decisions must reference a human `decided_by` [T-jordi-22].

- **Owner system:** FirstShift (today this trail exists nowhere: "no end-to-end record of who decided what and when" [T-laura-14, T-laura-18]).
- **Retention:** with the candidate record; AuditEvent keeps the immutable trace longer.

## Document (reference only)

Documents are referenced by ID and never stored or logged inline (architecture rule 5). This entity is a pointer, not a store.

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key; the only thing the rest of the system ever sees |
| `candidate_id` | fk | owner |
| `type` | enum (id_nie, ss_number, bank_cert, hygiene_cert, contract) | the pack Nómina360 needs [T-sofia-04]; the three always late are bank, SS, hygiene [T-sofia-10] |
| `external_ref` | str | EU-hosted object storage key (C-T8) |
| `status` | enum (requested, received, checked, rejected_wrong, confirmed_in_nomina) | checked on arrival, not at payday [T-sofia-30] |
| `nomina360_ok` | bool | confirmed against the pack People Ops validated |

- **Owner system:** Nómina360/People Ops for the truth; FirstShift tracks chase status only.
- **Retention:** pointers deleted at candidate erasure; binary objects follow People Ops retention (DPO to confirm the exact term).

## TrainingEnrollment

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `application_id` | fk | whose enrollment |
| `module_key` | str (food_hygiene) | the binary day-1 gate for food contact [T-iker-06, C-L8] |
| `learnbite_enrollment_id` | str | system of record link |
| `status` | enum (enrolled, completed, failed) | completion arrives via webhook |
| `completed_at` | datetime, nullable | feeds the guard and the trainer's advance notice [T-iker-20] |

- **Owner system:** LearnBite; FirstShift caches status.
- **Retention:** with the hire record.

## FirstShift (the scheduled first shift and commitment engine)

Also carries the O11 hired-to-rota tracking fields, because this entity owns the window between verbal yes and first worked shift that no system owns today (`discovery/systems-and-data.md` key finding).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `application_id` | fk | the hire |
| `open_shift_id` | fk | the concrete shift to work |
| `scheduled_at` | datetime | communicated at least 24 h ahead [T-churned-08, T-candidate-a-16] |
| `confirmation_status` | enum (pending, confirmed, unconfirmed) | day-before confirmation (O6) |
| `confirmed_at` | datetime, nullable | cutoff: backup activates at T minus 18 h if unconfirmed |
| `backup_bench_entry_id` | fk, nullable | the warm backup (O4) |
| `backup_activated_at` | datetime, nullable | logged like any decision |
| `trainer_notified_at` | datetime, nullable | fixes "a mí nadie me llama" [T-iker-20] |
| `role_on_day1` | enum | till/foh if hygiene is pending, per C-L8 |

**O11 hired-to-rota tracking fields:**

| Field | Type | Use |
|---|---|---|
| `promise_started_at` | datetime | the verbal yes; today this moment changes no system object [T-yolanda-08] |
| `docs_complete_at` | datetime, nullable | when the pack was checked |
| `nomina360_write_requested_at` | datetime, nullable | when People Ops flow requested creation |
| `nomina360_api_confirmed_at` | datetime, nullable | weak signal only; never trusted alone (C-T3) |
| `csv_confirmed_at` | datetime, nullable | strong signal: the next CSV shows it (C-T4, O12) |
| `rota_unlock_date` | date | next ShiftGrid lock opportunity (Thursday) [T-hugo-12] |
| `current_blocker` | enum (none, docs_missing, nomina_pending, rota_locked, hygiene_pending) | drives the daily WhatsApp status line, one action per state |
| `blocker_since` | datetime, nullable | where it sits in the 3-to-6-day range [T-yolanda-20] |
| `ready_for_rota_signaled_at` | datetime, nullable | only ever set after `csv_confirmed_at` or a recorded People Ops exception (O12 gate) |

- **Owner system:** FirstShift for the commitment and the window; ShiftGrid owns the rota entry, Nómina360 owns employment.
- **Retention:** anonymize 12 months after `scheduled_at`; the window metrics survive as aggregates.

## CheckIn

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `application_id` | fk | the hire |
| `kind` | enum (day_0, day_3, day_10) | the early-life conversation (O8) |
| `scheduled_at`, `completed_at` | datetime | execution |
| `rota_conflict_detected` | bool | promised schedule vs real rota from ShiftGrid |
| `expectation_mismatch` | bool | what was promised vs what is |
| `routed_to_manager_at` | datetime | with a suggested action |
| `resolution_due_at`, `resolved_at` | datetime | 48 h resolution window, else it becomes another unanswered channel [T-churned-22] |

- **Owner system:** FirstShift.
- **Retention:** with the hire; feeds the week-2 rating and day-30 signal.

## BenchEntry

The formalized "maybes" list (O4; ~25 names in Yolanda's personal WhatsApp today [T-yolanda-14]).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `candidate_id`, `restaurant_id` | fk | per-restaurant pool |
| `reason` | enum (silver_medal, rehire_eligible, referral) | why they are here |
| `consent_id` | fk to Consent (purpose `bench_reengagement`) | re-engagement is impossible without it (ADR-005) |
| `added_at`, `expires_at` | datetime | consent expiry; the pool auto-expires (C-L4) |
| `last_contacted_at`, `reengagement_count` | datetime, int | anti-spam and audit |
| `status` | enum (active, engaged, hired, expired, erased) | lifecycle |

- **Owner system:** FirstShift.
- **Retention:** until `expires_at` (pilot default: 6 months per consent cycle), then expire and anonymize; immediate erasure on request (C-L5).

## AuditEvent

Immutable, append-only. Every state transition, agent turn, tool call, integration write and timer firing.

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `occurred_at` | datetime | when |
| `actor_type` | enum (candidate, manager, agent, system, timer) | who triggered it (state-machine table column) |
| `actor_id` | str | which human/agent/timer; manager actions carry their identity for C-L6 |
| `application_id`, `candidate_id` | fk | subject |
| `event_type` | str | typed, enumerated |
| `state_from`, `state_to` | str, nullable | transitions |
| `payload` | json | typed details; never document contents, never raw document data |
| `idempotency_key` | str, nullable | links to OutboxMessage so IT can query one person's writes end to end (C-T6, [T-hugo-24]) |

- **Owner system:** FirstShift.
- **Retention:** the longest of any entity (pilot default: 5 years, pending DPO sign-off); it is the DPIA evidence and the AI Act logging surface (C-L7).

## OutboxMessage

Every outbound write to a client system (architecture rule 4, ADR-003).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `port` | enum (hiredesk, nomina360, shiftgrid, learnbite, m365) | which adapter |
| `operation` | str | e.g. `create_employee`, `assign_shift` |
| `payload` | json | the validated Pydantic payload |
| `idempotency_key` | str | a key IT controls; replay updates or no-ops, never duplicates (C-T5, [T-hugo-24]) |
| `status` | enum (pending, relaying, api_confirmed, csv_confirmed, failed, downgraded) | `api_confirmed` is weak; `csv_confirmed` is strong (O12); `downgraded` = CSV disagreed |
| `attempts`, `next_retry_at`, `last_error` | int, datetime, str | relay retry state |
| `related_entity_id` | uuid | the FirstShift entity the write serves |

- **Owner system:** FirstShift.
- **Retention:** 90 days after terminal status; AuditEvent keeps the queryable trace.

## NominaReconciliationRun (O12)

One row per nightly job execution.

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `run_date` | date | the CSV's date |
| `csv_ref` | str | pointer to the parsed export (C-T4) |
| `rows_parsed` | int | health of the export itself |
| `writes_expected` | int | outbox messages awaiting `csv_confirmed` |
| `matches` | int | writes the CSV confirms |
| `mismatches` | int | API-confirmed writes absent from the file [T-hugo-16, T-hugo-20] |
| `status` | enum (ok, drift_detected, failed) | `failed` alerts IT immediately |

## ReconciliationTask (O12)

The human work item the gate creates; visibility is not velocity, each task drives one action (O11 principle).

| Field | Type | Use |
|---|---|---|
| `id` | uuid | key |
| `reconciliation_run_id` | fk | which run found it |
| `outbox_message_id` | fk | the downgraded write |
| `mismatch_type` | enum (missing_in_csv, unexpected_in_csv) | write missing, or CSV row with no write of ours |
| `assigned_to` | enum (people_ops, it) | Sofía's team fixes the record, IT investigates the gateway [T-hugo-20] |
| `compensating_action_ref` | str | the runbook entry per write type (C-T7) |
| `status` | enum (open, acknowledged, resolved) | until resolved, `ready_for_rota` stays unsignaled |

- **Owner system:** FirstShift.
- **Retention:** 24 months (matches the audit window People Ops works to; DPO to confirm).

---

## Retention summary

| Entity | Retention (pilot default, pending DPO) |
|---|---|
| Candidate, Application, ScreeningAnswer, Decision | anonymize 12 months after last interaction (C-L4) |
| Consent | life of the candidate record |
| Document pointers | deleted at erasure; binaries per People Ops retention |
| TrainingEnrollment, FirstShift, CheckIn | anonymize 12 months after the shift |
| BenchEntry | consent expiry (6 months) or erasure |
| AuditEvent | 5 years |
| OutboxMessage | 90 days after terminal status |
| ReconciliationRun/Task | 24 months |
