# 03 · Solution design: think wide, then commit

**Goal:** generate genuinely different ways to hit the north star, choose one with explicit reasoning, and design it so it plugs into the client's existing systems and routines.

**Outputs (in `design/`):** `options.md`, `decision-matrix.md`, `concept.md`, `agents.md`, `state-machine.md`, `architecture.md`, `data-model.md`, `integration-contracts.md`, `guardrails.md`, `adr/ADR-00X-*.md` (one per significant decision).

---

## 1. Diverge: at least 8 options before choosing

Write `options.md` with at least 8 options. Each gets: one-line idea, which hypothesis (Phase 2) it attacks, rough effort, risk, and what would have to be true. Include the obvious options so the choice is visibly reasoned, and push for non-obvious ones. Required in the list (add more):

1. **Faster screening bot** (the literal ask): conversational screening on WhatsApp, ranked shortlist for the talent team.
2. **Hire for shifts, not positions:** the candidate is matched to concrete open shifts from ShiftGrid (for example "Fri and Sat 19:00 to 01:00, Benidorm Playa") instead of a generic "availability" field. Rejections for "availability" disappear because the question becomes "which of these shifts can you take".
3. **Demand-triggered requisitions:** use the TillCloud forecast plus ShiftGrid coverage plus known attrition to open hiring before the manager notices the gap. The pipeline starts weeks earlier for coastal units before summer.
4. **The always-warm bench:** formalize Yolanda's "maybes" list. Silver-medal candidates, ex-employees eligible for rehire and crew referrals stay in a consented, per-restaurant talent pool that the agent re-engages when a gap appears.
5. **Pre-boarding in parallel:** with candidate consent, start document collection and the LearnBite food hygiene module while the hiring decision is pending, so "offer accepted" and "ready for the rota" collapse into the same day. Clearly mark that completing pre-boarding never implies a hiring commitment.
6. **First-shift commitment engine:** day-before confirmation with logistics (address, entrance, uniform, who to ask for), day-0 check-in, and an automatic backup from the bench if the confirmation does not arrive by a cutoff.
7. **Manager in the loop, in WhatsApp:** every decision a manager owns (interview slot, offer approval, first-shift slot) arrives as one message with a summary and two or three buttons. No dashboard.
8. **Early-life check-ins:** day 3 and day 10 short conversations to detect rota conflicts and expectation mismatch, routed to the manager with a suggested action.
9. **Crew referral loop:** current crew can forward a personal link; referred candidates get fast-tracked and the referrer gets notified when the friend starts.
10. **Voice interview option** (v2 candidate): for candidates who prefer to talk, a short voice screening call.

## 2. Converge: decision matrix

Score each option 1 to 5 on: impact on TTFPS, impact on day-1 show rate, evidence strength from discovery, integration effort (inverse), compliance risk (inverse), manager behavior change required (inverse), demo-ability in 5 days. Weight impact and evidence highest. Show the weighted total and write a short paragraph on why the winner wins and what was consciously left out.

Expected outcome, to be confirmed by the matrix: a **combined concept** built on options 2, 4, 5, 6, 7 and 8, with option 1 as a component, option 3 as a phase-2 extension and option 10 as v2.

## 3. The concept: FirstShift

Write `concept.md` as a one-page narrative and a sequence diagram. The concept must be explainable in one sentence:

> FirstShift fills a specific open shift with a person who is ready to work it, by running recruiting, pre-boarding, scheduling and the first week as one conversation, with managers deciding from WhatsApp and every client system kept as the source of truth.

Key design moves:
- **The unit of work is the open shift, not the requisition.** A requisition in HireDesk is still created (Talent keeps control and reporting), but matching happens against ShiftGrid open shifts.
- **One continuous candidate conversation** across recruit, pre-board, first shift and first week, so the candidate never repeats information and never waits for a handoff.
- **Three agent roles on one shared candidate record** (see `agents.md`), mirroring how frontline HR agent products split recruiting, onboarding and engagement, but sharing state.
- **The bench closes the loop:** no candidate is "rejected into the void". With consent, good candidates who did not fit this shift go back to the restaurant bench for the next gap.
- **Signals flow back:** day-30 retention and the manager's week-2 rating are written back against the screening answers, so screening criteria can be revised with evidence (by humans, see guardrails).

## 4. Agents

Write `agents.md`. Each agent has: purpose, triggers, tools it can call, states it can act in, what it must never do, escalation rules, tone and language rules, and the prompt file it uses.

| Agent | Scope | Tools (examples) |
|---|---|---|
| **Recruit** | First contact in under 5 minutes, consent and AI disclosure, eligibility facts (right to work, minimum age, distance and transport), shift matching, language skills, interview booking in the manager's slots | `get_open_shifts`, `propose_shifts`, `book_interview_slot`, `save_screening_answers`, `request_manager_decision`, `add_to_bench` |
| **Onboard** | Pre-boarding (documents by upload link, LearnBite enrollment), offer delivery after manager approval, first-shift scheduling, day-before confirmation, day-0 check-in, backup activation | `request_documents`, `check_document_status`, `enroll_training`, `check_training_status`, `schedule_first_shift`, `send_first_shift_brief`, `activate_backup` |
| **Pulse** | Day-3 and day-10 check-ins, rota conflict detection, swap requests routed to the manager, week-2 manager rating, day-30 retention signal | `get_employee_rota`, `report_issue_to_manager`, `request_swap`, `record_manager_rating` |

Agents call tools; tools call the deterministic core; the core decides. An agent never calls a client system directly.

## 5. State machine

Write `state-machine.md` with a Mermaid `stateDiagram-v2` and a transition table (from, event, guard, to, side effects, who triggered it: candidate, manager, system, timer).

Required states: `new`, `contacted`, `consented`, `screening`, `matched`, `interview_booked`, `interviewed`, `pending_manager_decision`, `offer_sent`, `offer_accepted`, `preboarding`, `ready_for_rota`, `first_shift_scheduled`, `first_shift_confirmed`, `first_shift_worked`, `active_week1`, `active_day30`. Terminal or side states: `benched`, `withdrawn`, `not_selected` (only by a human), `no_show`, `erased` (GDPR erasure).

Required timers: no reply after first contact (nudge at 2 h and 24 h, then bench), interview reminder (24 h and 2 h before), manager decision SLA (remind at 2 h, escalate to area HRBP at 8 h), first-shift confirmation cutoff (activate backup at T minus 18 h if unconfirmed).

Invariants the core enforces (write them as property tests later):
- Cannot reach `offer_sent` without a recorded manager approval.
- Cannot reach `not_selected` without a human actor.
- Cannot reach `first_shift_scheduled` unless documents are complete in Nómina360 **or** People Ops has recorded an explicit exception.
- Food-handling first shifts require the hygiene module completed in LearnBite; otherwise the first shift is scheduled as till or front-of-house and the trainer is told.
- Every transition is appended to an immutable audit log.

## 6. Architecture

Write `architecture.md` with a component diagram (Mermaid) and a short explanation of each box:

- **Channel gateway:** inbound and outbound messages (simulator adapter, Twilio WhatsApp adapter), webhook verification, idempotency.
- **Conversation layer:** the three agents, prompt files, tool definitions, schema validation of LLM outputs, language detection.
- **Core:** state machine, policies (matching, timers, guards), pure and fully unit-tested.
- **Integration layer:** ports for HireDesk, Nómina360, ShiftGrid, TillCloud, LearnBite, M365 calendar; adapters (mocks now, real later); outbox and relay worker; nightly reconciliation job for Nómina360 CSV.
- **Workers:** timers, nudges, outbox relay, reconciliation.
- **Event stream:** every agent turn, tool call, state transition and integration write is persisted as a typed event and streamed over SSE. This is what makes the system observable and auditable.
- **FirstShift Console (React + TypeScript + Tailwind on Vite) for HQ only:** live agent activity, candidate journeys, human takeover, metrics, escalations, evals, compliance and the demo simulator, for the Talent team, the DPO and Ops leadership. Managers never need it. Full spec: `specs/04b-console.md`. Include it in the architecture diagram as a separate deployable that talks only to the FirstShift API.
- **Data:** Postgres (candidate record, conversation log, audit log, outbox, bench), with retention policies.

Write ADRs for at least: deterministic core vs LLM-driven flow; open shift as unit of work; outbox pattern for client writes; WhatsApp buttons for manager decisions instead of a dashboard; how the bench handles consent and retention.

## 7. Data model and integration contracts

`data-model.md`: entities (Restaurant, OpenShift, Candidate, Application, Consent, ScreeningAnswer, Decision, Document (reference only), TrainingEnrollment, FirstShift, CheckIn, BenchEntry, AuditEvent, OutboxMessage) with fields, owner system and retention.

`integration-contracts.md`: for each port, the methods, payloads (Pydantic models), error semantics, retry policy, idempotency key, and the mapping to the mock API. Include the Nómina360 quirk (HTTP 200 with error body) and how the adapter turns it into a typed error.

## 8. Guardrails

`guardrails.md`, mapped one to one to the constraints in `design/constraints.md`:
- AI disclosure in the first message, in the candidate's language.
- Consent captured with notice version; no processing before consent except replying to the first message.
- The agent does not ask about protected characteristics (age beyond the legal minimum check, nationality beyond right to work, health, family, religion) and refuses to record them if volunteered.
- Free-text answers are summarized for the manager, never scored into a hidden ranking.
- Off-topic, abusive or distressed messages escalate to a human with a canned, kind response.
- Prompt injection inside candidate messages cannot trigger tools outside the current state's allowed set.
- Criteria changes from the feedback loop are proposals for humans, never automatic.

## Exit criteria

- [ ] At least 8 options and a weighted decision matrix with written rationale.
- [ ] Concept explainable in one sentence, with a sequence diagram from "shift gap appears" to "day 10 check-in".
- [ ] State machine diagram and full transition table, including timers and invariants.
- [ ] Architecture diagram and at least 5 ADRs.
- [ ] Every constraint from Phase 2 maps to at least one guardrail or invariant.
