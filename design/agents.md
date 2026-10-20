# Agents: the three roles on one shared record

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 4, S4).
- **Inputs:** `design/concept.md` (approved concept), `design/constraints.md`, `discovery/insights.md`, the state machine in `design/state-machine.md`.
- **Rule from the spec, verbatim:** "Agents call tools; tools call the deterministic core; the core decides. An agent never calls a client system directly."

## Where Strands Agents (OpenAI API) sits

The three roles are Strands Agent instances over the OpenAI API (model configurable, default gpt-4.1-mini per the project stack). Their entire job is conversation and extraction:

1. The agent holds the conversation in the candidate's or manager's language and decides what to say next inside the current state.
2. The agent calls tools. Tools are thin, typed wrappers around functions in the deterministic core (`app/core/`), never direct calls to HireDesk, Nómina360, ShiftGrid, LearnBite or M365.
3. The core validates every structured output against a Pydantic schema, evaluates guards and policies, decides the transition, and returns what the agent may say and do next. Invalid LLM output triggers a re-ask, never a guess.

The dependency arrow is one-directional: **agents call tools, tools call the core, the core decides.** The core never calls an agent, never prompts an LLM, and never needs one: the state machine, timers, matching guards and audit log run without any model. This is what makes the prompt-injection guardrail enforceable: the core refuses any tool call outside the current state's allow-list below, no matter what the conversation text contains (spec section 8, C-L7).

All three roles read and write **one shared candidate record** (the Application and its related entities, `design/data-model.md`, T4 phase 2 part B). A fact collected once (consent, language, concrete availability) is never asked again.

## Recruit

| Aspect | Design |
|---|---|
| Purpose | First contact in under 5 minutes of application intake, consent and AI disclosure, eligibility facts (right to work, minimum age, distance and transport), shift matching against concrete open shifts, language skills, interview booking in the manager's slots. Owns the front door where 41.0% of applicants were never contacted and the median was 3.9 days (H1, funnel). |
| Triggers | New application webhook (HireDesk); any candidate reply while the record is in a Recruit state; bench re-engagement timer when a gap appears at the entry's restaurant (O4); manager changes or frees interview slots. |
| Tools | `get_open_shifts`, `propose_shifts`, `book_interview_slot`, `save_screening_answers`, `request_manager_decision`, `add_to_bench`, plus `capture_consent` and `save_language_tag` (C-L1, C-L2; H7: language is a tagged profile fact, not a scored test). |
| States it can act in | `new`, `contacted`, `consented`, `screening`, `matched`, `interview_booked` (re-booking after a first no-show), and `benched` re-engagement into `contacted`. |
| Must never do | Never reject or deselection-decide anything: rejection is only ever a human actor (`not_selected`, C-L6, [T-jordi-22]). Never send an offer. Never ask about protected characteristics (age beyond the legal minimum check, nationality beyond right to work, health, family, religion) and refuse to record them if volunteered. Never proceed with processing before consent is captured, except replying to the first message. Never promise a shift or a hiring outcome; shift proposals are recommendations. |
| Escalation | Off-topic, abusive or distressed message: canned, kind response plus immediate human takeover routed to the talent team (CPO's rude-screenshot risk, [T-marta-18, T-marta-20]); consent refusal: stop, confirm, close the loop; no shift fit: offer the bench with consent instead of a rejection ([T-candidate-b-18]: a quick no beats a slow maybe). |
| Tone and language | Spanish by default; Portuguese and English supported, selected explicitly by the candidate, never guessed from names (C-O4). One concrete question per message in the format candidates say they answer ([T-candidate-b-22]). Warm, direct, zero corporate speak. AI disclosure in the very first message (C-L7). |
| Prompt file | `app/prompts/recruit.v1.md` (versioned; eval reports reference the version). |

## Onboard

| Aspect | Design |
|---|---|
| Purpose | Pre-boarding with opt-in (documents by upload link, LearnBite enrollment) while the decision is pending, with explicit no-commitment language (H3, [T-sofia-10]); offer delivery only after a recorded manager approval; first-shift scheduling; day-before confirmation with logistics; day-0 check-in; backup activation from the bench. |
| Triggers | Manager approval recorded (`pending_manager_decision` exit); offer accepted; pre-boarding opt-in at any point from `matched` onward; document or training status change (webhook or nightly CSV read); manager confirms the first-shift slot; confirmation-cutoff timer at T minus 18 h; day 0. |
| Tools | `request_documents`, `check_document_status`, `enroll_training`, `check_training_status`, `schedule_first_shift`, `send_first_shift_brief`, `activate_backup`, plus `get_tracker_status` (reads the O11 promise-to-payroll tracker; the tracker itself is core state, not agent memory). |
| States it can act in | `pending_manager_decision` and `offer_sent` (opt-in pre-boarding only, never implying commitment), `offer_accepted`, `preboarding`, `ready_for_rota`, `first_shift_scheduled`, `first_shift_confirmed`, `first_shift_worked` (day-0 check-in). |
| Must never do | Never sign a contract or register an alta: the Nómina360 write path is limited to validated employee-creation payloads routed through People Ops' flow (C-L9, [T-sofia-04]). Never present pre-boarding completion as a hiring commitment (compliance and candidate trust, H3 risk). Never schedule a food-handling first shift without the hygiene module completed in LearnBite: schedule till or front-of-house instead and tell the trainer (C-L8, [T-iker-06]). Never schedule the first shift unless documents are complete in Nómina360 or People Ops has recorded an explicit exception. Never activate a backup twice for the same shift (timer hygiene; one correction attempt, then a human). |
| Escalation | Nómina360 mismatch or throttling anomaly: alert IT and People Ops through the runbook, never retry blindly (C-T2, C-T3, [T-hugo-14, T-hugo-16]); missing People Ops exception on the scheduling guard: ask People Ops, do not loosen the guard; backup activation at cutoff: notify manager and backup candidate both, with the audit trail visible ([T-laura-18]). |
| Tone and language | Same language rules as Recruit. Logistics messages are concrete and short: address, entrance, uniform, who to ask for, because candidates learned first shifts at 22:30 the night before or by chance from a crew group (H4, [T-churned-08, T-candidate-a-16, T-candidate-a-18]). Confirmation is one tap. |
| Prompt file | `app/prompts/onboard.v1.md`. |

## Pulse

| Aspect | Design |
|---|---|
| Purpose | Day-3 and day-10 check-ins (O8), rota conflict detection by reading the promised schedule against the real ShiftGrid rota, swap requests routed to the manager, week-2 manager rating, day-30 retention signal written back against screening answers. |
| Triggers | Check-in schedule (day 3, day 10 after `first_shift_worked`); unresolved swap request older than a bounded window; week-2 rating due; day-30 retention checkpoint. |
| Tools | `get_employee_rota`, `report_issue_to_manager`, `request_swap`, `record_manager_rating`, plus `record_retention_signal` (writes the day-30 outcome used by the signals-flow-back loop). |
| States it can act in | `first_shift_worked`, `active_week1`, `active_day30`. |
| Must never do | Never change the rota directly: `request_swap` routes to the manager, who decides (C-O1; the system recommends, a human decides). Never resolve a surfaced conflict itself or let a conflict sit unowned: detection without resolution inside 48 hours makes it worse ([T-churned-22 to T-churned-24]). Never ask engagement-survey questions that collect protected characteristics. Never message beyond the consented channel or after an opt-out (C-L2). |
| Escalation | Conflict surfaced: manager gets one message with a suggested action and a 48-hour owner; still unresolved: escalate to the area HRBP; distressed or quit-intent message: immediate human takeover; every exit records the operational cause, not just "personal reasons" ([T-churned-26]). |
| Tone and language | Same language rules. Check-ins are three taps or less: everything works, something is off (with what), I need a change. Week-2 rating for the manager is one question, 1 to 5, by WhatsApp quick reply (metric tree quality branch). |
| Prompt file | `app/prompts/pulse.v1.md`. |

## Per-state tool allow-list seeds

The core enforces this table. A tool call outside the current state's row is refused and logged, whatever the message text says (spec section 8: prompt injection cannot trigger tools outside the current state's allowed set). "Seeds" means the build may extend rows only with a recorded reason; narrowing is always allowed.

| State | Agent | Allowed tools |
|---|---|---|
| `new` | Recruit | `capture_consent` (first-message reply path only) |
| `contacted` | Recruit | `capture_consent` |
| `consented` | Recruit | `save_screening_answers`, `save_language_tag` |
| `screening` | Recruit | `save_screening_answers`, `save_language_tag`, `get_open_shifts`, `propose_shifts`, `add_to_bench` |
| `matched` | Recruit | `propose_shifts`, `book_interview_slot`, `add_to_bench`; Onboard: `request_documents`, `enroll_training` (opt-in pre-boarding only) |
| `interview_booked` | Recruit | `book_interview_slot` (first re-book only) |
| `interviewed` | Recruit | `request_manager_decision` |
| `pending_manager_decision` | Recruit | `request_manager_decision` (idempotent re-send); Onboard: `request_documents`, `enroll_training`, `check_training_status` |
| `offer_sent` | Onboard | `request_documents`, `check_document_status`, `enroll_training`, `check_training_status`, `get_tracker_status` |
| `offer_accepted` | Onboard | `request_documents`, `check_document_status`, `enroll_training`, `check_training_status`, `get_tracker_status` |
| `preboarding` | Onboard | `request_documents`, `check_document_status`, `enroll_training`, `check_training_status`, `get_tracker_status` |
| `ready_for_rota` | Onboard | `schedule_first_shift` (proposal), `get_tracker_status` |
| `first_shift_scheduled` | Onboard | `send_first_shift_brief`, `activate_backup` (cutoff timer only), `schedule_first_shift` (manager re-slot) |
| `first_shift_confirmed` | Onboard | `send_first_shift_brief` (day-0 logistics) |
| `first_shift_worked` | Pulse | `get_employee_rota`, `report_issue_to_manager`, `request_swap`; Onboard: `send_first_shift_brief` (day-0 check-in) |
| `active_week1` | Pulse | `get_employee_rota`, `report_issue_to_manager`, `request_swap`, `record_manager_rating` |
| `active_day30` | Pulse | `record_retention_signal`, `record_manager_rating` |
| `benched` | Recruit | re-engagement into `contacted` (tools of the target state, re-engagement consent required) |

Terminal and side states (`not_selected`, `no_show`, `withdrawn`, `erased`) have no tool allow-list: no agent acts in them. Human decisions and retention/erasure jobs go through the core's own paths, not through agent tools.
