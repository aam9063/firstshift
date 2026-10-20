# State machine: crew hiring pilot

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 5, S4).
- **Inputs:** `design/concept.md` (approved concept), `design/agents.md`, `design/constraints.md`, `discovery/insights.md`.
- The core (`app/core/`) implements this state machine in plain Python with no I/O and no LLM. The state covers one candidate against one open shift (the unit of work); a candidate can have several concurrent applications, one per shift or restaurant gap.

## Diagram

```mermaid
stateDiagram-v2
    direction TB

    [*] --> new: HireDesk application webhook received

    new --> contacted: first message sent, AI disclosure and notice version included
    contacted --> consented: candidate accepts consent on this channel
    contacted --> withdrawn: candidate opts out
    contacted --> benched: no-reply timer exhausted (nudges at 2 h and 24 h already sent)

    consented --> screening: structured screening starts
    screening --> matched: eligibility facts pass and at least one open shift fits
    screening --> benched: no fit now and the candidate consents to the bench
    screening --> not_selected: a named human records the rejection

    matched --> interview_booked: candidate books a slot from the manager's open slots
    interview_booked --> interviewed: candidate attends
    interview_booked --> interview_booked: first no-show, manager re-offers a slot (once)
    interview_booked --> no_show: second missed interview

    interviewed --> pending_manager_decision: Recruit sends the summary and requests the decision
    pending_manager_decision --> offer_sent: manager approves (recorded with who, when, facts seen)
    pending_manager_decision --> offer_sent: area HRBP approves after the 8 h escalation (recorded)
    pending_manager_decision --> not_selected: manager declines

    offer_sent --> offer_accepted: candidate accepts within the 7-day window
    offer_sent --> withdrawn: candidate declines or the 7-day window expires

    offer_accepted --> preboarding: hired-to-rota tracker opens (O11)

    state preboarding {
        [*] --> trk_documents
        trk_documents --> trk_nomina: documents complete, creation requested through People Ops
        trk_nomina --> trk_csv: creation sent, response validated by body (C-T3)
        trk_csv --> [*]: nightly CSV shows the employee (C-T4)
        trk_csv --> trk_nomina: O12 mismatch: write downgraded, IT and People Ops alerted
        trk_documents: documents pending (bank certificate, SS number, hygiene certificate)
        trk_nomina: Nómina360 creation in flight, day N of 3 to 6
        trk_csv: awaiting CSV confirmation, up to one day
    }

    preboarding --> ready_for_rota: tracker complete (documents in and creation CSV-confirmed)
    ready_for_rota --> preboarding: reconciliation revokes a previously confirmed creation (rare)

    ready_for_rota --> first_shift_scheduled: manager picks the first-shift slot
    first_shift_scheduled --> first_shift_confirmed: candidate confirms the day before
    first_shift_scheduled --> first_shift_worked: day 0 arrives and the candidate works (backup stood down)
    first_shift_confirmed --> first_shift_worked: candidate works the shift
    first_shift_confirmed --> no_show: day-0 no-show
    first_shift_scheduled --> no_show: cutoff passed unconfirmed and day-0 no-show

    first_shift_worked --> active_week1: day 1 begins, day-3 and day-10 check-ins armed
    active_week1 --> withdrawn: the hire quits in week 1 (operational cause recorded)
    active_week1 --> active_day30: 30 days retained, week-2 rating and day-30 signal recorded

    benched --> contacted: new gap at the bench's restaurant, re-engagement consent valid

    note right of erased: reachable from every state on a verified erasure request
    note right of benched: consented, per-restaurant pool (O4); retention and erasure apply like any record
```

## Transition table

Actor types: `candidate`, `manager`, `system`, `timer`. Agent actions are recorded in the audit log as system actions with the agent role and prompt version named, because accountability sits with the system, not the model.

| # | From | Event | Guard | To | Side effects | Actor |
|---|---|---|---|---|---|---|
| 1 | (none) | application webhook received | DPIA signed and write paths approved (C-X1) | new | candidate record created with brand and restaurant scope (C-O3); notice staged | system |
| 2 | new | intake processed | first message carries the AI disclosure and notice version | contacted | outbound WhatsApp sent in minutes (H1); first-contact timestamp stored | system |
| 3 | contacted | candidate consents | notice version shown; consent is for this channel (C-L2) | consented | consent row stored with timestamp and notice version; language preference stored | candidate |
| 4 | contacted | candidate opts out | | withdrawn | processing stops; retention clock starts (C-L4) | candidate |
| 5 | contacted | no-reply timer fires | nudges at 2 h and 24 h already sent unanswered | benched | bench entry with re-engagement consent flag (O4); all steps audited | timer |
| 6 | consented | screening starts | | screening | structured answers captured as they arrive (H2, [T-candidate-b-22]) | system |
| 7 | screening | shift-fit recommendation produced | eligibility facts pass (right to work, minimum age, distance and transport) and at least one open shift fits | matched | recommendation plus evidence stored; the agent recommends, never rejects (C-L6) | system |
| 8 | screening | no fit now | candidate consents to the bench | benched | consented, per-restaurant bench entry (O4, [T-yolanda-14, T-yolanda-16]) | system |
| 9 | screening | human records the rejection | actor is a named human (invariant INV-2) | not_selected | decision logged with who, what, when and the facts they saw (C-L6); kind, fast reply to the candidate (H1, [T-candidate-b-18]) | manager |
| 10 | matched | candidate picks a slot | slot is one of the manager's open slots | interview_booked | HireDesk interview stage updated; reminder timers armed (24 h, 2 h) | candidate |
| 11 | interview_booked | first no-show | one re-offer only | interview_booked | manager informed and re-offers a slot; event audited (38.0% interview no-show baseline justifies one recovery, funnel) | manager |
| 12 | interview_booked | second missed interview | | no_show | manager notified; bench offer made if the candidate consents | timer |
| 13 | interviewed | decision requested | | pending_manager_decision | summary plus two or three buttons sent to the manager (O7, C-O2); SLA timers armed (2 h remind, 8 h escalate) | system |
| 14 | pending_manager_decision | approval recorded | recorded approval with who, when and facts seen (invariant INV-1) | offer_sent | approval logged; offer dispatched; 7-day acceptance window armed | manager |
| 15 | pending_manager_decision | approval recorded after escalation | same as row 14; 8 h SLA exceeded first | offer_sent | escalation and approval both logged (H5 kill threshold watches this path) | manager |
| 16 | pending_manager_decision | manager declines | human actor | not_selected | fast, kind no to the candidate; bench offer if consented (O4) | manager |
| 17 | offer_sent | candidate accepts | within the 7-day window | offer_accepted | acceptance timestamp stored (resolves the funnel caveat that conflates acceptance with document collection); pre-boarding activates | candidate |
| 18 | offer_sent | decline or window expiry | | withdrawn | retention clock starts; bench offer if consented ([T-candidate-c-12]: a week of waiting loses the candidate) | candidate, timer |
| 19 | offer_accepted | tracker opens | | preboarding | O11 tracker instantiated; document and module collection continues from the opt-in lane | system |
| 20 | preboarding | nightly reconciliation downgrades an API-confirmed write absent from the CSV | mismatch detected | preboarding | mismatch alert to IT and People Ops (C-T4, [T-hugo-18]); tracker flag set | system |
| 21 | preboarding | tracker completes | documents complete in Nómina360 and creation confirmed by the CSV (C-T4) | ready_for_rota | manager and candidate told; first-shift proposal prepared | system |
| 22 | ready_for_rota | reconciliation revokes a confirmed creation | CSV correction or reversal found | preboarding | alert plus the compensating action named per C-T7 ([T-sofia-20]: nobody works unregistered) | system |
| 23 | ready_for_rota | manager picks the slot | documents complete in Nómina360 or People Ops exception recorded (I3); food-handling first shift only with the hygiene module complete, otherwise till or front-of-house fallback and the trainer told (I4) | first_shift_scheduled | first shift written to ShiftGrid; brief and reminders armed; named backup reserved from the bench (H4) | manager |
| 24 | first_shift_scheduled | candidate confirms | day-before message delivered | first_shift_confirmed | backup stood down; day-0 check-in armed | candidate |
| 25 | first_shift_scheduled | day 0 arrives | candidate shows unconfirmed | first_shift_worked | backup stood down; audit notes the confirmation never came | candidate |
| 26 | first_shift_confirmed | candidate works the shift | | first_shift_worked | shift end recorded; day-3 check-in armed | candidate |
| 27 | first_shift_scheduled or first_shift_confirmed | day-0 no-show | | no_show | manager and backup outcome recorded; operational cause checked against the O12 status before it is labeled motivational | timer |
| 28 | first_shift_worked | day 1 begins | | active_week1 | day-3 and day-10 check-ins scheduled (O8) | system |
| 29 | active_week1 | hire quits | | withdrawn | exit reason records the operational cause, not just "personal reasons" ([T-churned-26]) | candidate |
| 30 | active_week1 | 30 days retained | | active_day30 | week-2 manager rating and day-30 retention written back against the screening answers (signals flow back; C-L6: criteria changes stay human proposals) | system |
| 31 | benched | new gap appears | re-engagement consent valid and unexpired | contacted | bench re-engagement message; application-to-bench link audited | system |
| 32 | any | verified erasure request | identity verified | erased | every trace deleted or exported end to end, conversation history included (C-L5, [T-laura-12]); the audit log keeps a pseudonymized tombstone | candidate, system |

## Required timers

| Timer | Fires | Effect | Source |
|---|---|---|---|
| T1 no-reply after first contact | nudge at 2 h, nudge at 24 h, bench at 48 h unanswered | rows 2 and 5 | spec section 5; H1 |
| T2 interview reminder | 24 h and 2 h before the slot | reminder message to the candidate; also arms the manager if the slot moves | spec section 5 |
| T3 manager decision SLA | remind at 2 h, escalate to the area HRBP at 8 h | rows 13 to 15 | spec section 5; H5 (no approval-latency baseline exists today, so the pilot instruments it) |
| T4 first-shift confirmation cutoff | T minus 18 h if unconfirmed | `activate_backup`: the named bench backup is activated for the shift; the primary candidate stays `first_shift_scheduled` with a backup-active flag so a late confirmation can still stand the backup down | spec section 5; H4 |
| T5 offer acceptance window | 7 days after `offer_sent` | row 18 | metric tree offer-acceptance target (85% within 7 days); [T-candidate-c-12] |
| T6 nightly Nómina360 reconciliation | once per night | rows 20 and 22; O12 CSV-truth gate (C-T4) | O12; [T-hugo-18] |
| T7 check-in schedule | day 3, day 10, week 2, day 30 | rows 28 and 30 | O8, H6 |

The O12 one-day CSV confirmation lag is modeled into the commitment engine's cutoffs: T4 and the first-shift scheduling guidance account for it, so a Thursday-locked rota does not promise a shift the file cannot confirm by day 0 (O12 risk, `design/options.md`).

## The O11 tracker inside the flow

The hired-to-rota tracking **is** the `preboarding` window. The O11 promise-to-payroll tracker is not a separate lifecycle; it is the composite state the record sits in between `offer_accepted` and `ready_for_rota`, with the substates shown in the diagram (`trk_documents`, `trk_nomina`, `trk_csv`). It exists because no system, team or report owns this window today (`discovery/systems-and-data.md` key finding; [T-sofia-18]: the person is "a promise"; [T-yolanda-20]: Nómina360 creation takes 3 to 6 days and gates scheduling). Its rule is one action per state, never display only: chase the missing document, nudge the Nómina360 queue, warn about the Thursday rota lock ([T-sofia-26], [T-hugo-12]). A shadow copy of the tracker runs from the opt-in pre-boarding lane (rows 10 onward) so pre-collection progress is visible before the offer, without implying commitment.

## Where O12 reconciliation can flip a record

- `preboarding` internal, row 20: an API-confirmed employee creation that the nightly CSV does not show is downgraded; the tracker returns to `trk_nomina` and IT and People Ops are alerted. This is the July silent-failure failure mode caught structurally (C-T3, C-T4, [T-hugo-16, T-hugo-18, T-hugo-20]).
- `ready_for_rota` to `preboarding`, row 22: if a later CSV correction or reversal revokes a creation the file previously confirmed, the record is downgraded and no first shift may be scheduled until it is re-confirmed, because an unregistered person working a shift is a hard line ([T-sofia-20]).
- Row 27: before a day-1 absence is labeled a motivational no-show, the O12 status is checked; an alta that silently failed is an operational cause and is recorded as such.

## Invariants the core enforces

Written as stated in `specs/03-solution-design.md` section 5; each becomes a property test in the build phase:

- **INV-1** Cannot reach `offer_sent` without a recorded manager approval.
- **INV-2** Cannot reach `not_selected` without a human actor.
- **INV-3** Cannot reach `first_shift_scheduled` unless documents are complete in Nómina360 **or** People Ops has recorded an explicit exception.
- **INV-4** Food-handling first shifts require the hygiene module completed in LearnBite; otherwise the first shift is scheduled as till or front-of-house and the trainer is told.
- **INV-5** Every transition is appended to an immutable audit log.

System-level invariants INV-6 to INV-11 (multi-tenant scope, ports only, idempotent writes, Nómina360 adapter semantics, EU residency, DPIA send gate) are defined in `design/architecture.md` and `design/integration-contracts.md`; `design/guardrails.md` maps every constraint to guardrails G1-G7 or these invariants.

The audit log records every transition with who, what, when and why; erasure removes personal data while keeping a pseudonymized tombstone so the log stays complete and verifiable (C-L5, C-L6, [T-laura-18, T-laura-22]).
