# FirstShift runbook: the seven operations

For the people who operate FirstShift day to day: Talent, Ops and IT at Lumbre Burger Group, plus the vendor FDE team on call during the pilot. Source requirement: `specs/06-integration-rollout.md` section 5.

Conventions used in every section:

- Console calls carry the operator role in the `X-Actor-Role` header (`talent`, `dpo`, `ops`, `admin`; the outbox endpoints default to `ops`). Every action is audited: who, what, when and why.
- The console reads through the FirstShift API only. It never calls client systems or mocks directly.
- The live ops surfaces are the console `/ops` view (dead-letter queue, escalations, audit search) and `GET /health/adapters` (per-system health).
- The four documented alerts (not yet wired to a pager, see `docs/reliability.md`): DLQ not empty for more than 15 minutes, Nómina360 reconciliation drift, manager decision SLA breaches above threshold, LLM error rate above 2%.

---

## 1. Pause the agent for one restaurant

Use when a restaurant manager asks to stop hiring activity (temporary freeze, incident at the unit, audit in progress). One restaurant at a time; nothing else is affected.

1. Find the restaurant id in the console **Restaurants** view (or from the candidate's detail view, which names its restaurant).
2. Call `POST /api/restaurants/{restaurant_id}/pause` with your `X-Actor-Role` header. An empty body pauses; to resume later, call the same endpoint with the body `{"resume": true}`.
3. Check the response: `{"restaurant_id": "...", "code": "...", "paused": true}`.
4. Verify in the console **Restaurants** view that the target row shows paused and the other restaurants do not.
5. Verify the audit trail: an `restaurant.paused` audit row exists with the restaurant code and your role (and `restaurant.resumed` after resuming).

**Known limitation in the current build:** the pause is recorded, audited and visible, but the dispatch path does not yet consult the pause flag before sending outbound messages (`restaurant_paused` is only read by the console views today). Until that gate ships, pair the pause with a human takeover of the restaurant's open conversations (operation 2) so nothing is sent while the unit is frozen.

## 2. Take over a conversation

Use when a candidate needs a human: an escalation was raised (abusive or distressed classification, protected-data refusal), or the conversation needs judgment the agent must not apply. The agent never rejects a candidate; a human decides.

1. Open the candidate's conversation in the console **Live** view and take the candidate id from the journey panel.
2. Call `POST /api/candidates/{candidate_id}/takeover` with your `X-Actor-Role` header. The response confirms `agent_in_control: false` and the role that took over.
3. Send your messages: `POST /api/candidates/{candidate_id}/messages` with body `{"text": "..."}`. Each message is recorded as a `message.out` event with `sender_type: "human"` and delivered through the candidate's channel. Sending without an active takeover returns `409` ("the agent is in control").
4. Verify the candidate sees your messages (the journey trace shows them in the conversation thread) and the audit rows `human_action.takeover` and `human_action.message` carry your role.
5. When the conversation is back on rails, call `POST /api/candidates/{candidate_id}/release`. Verify `agent_in_control: true` and the `human_action.release` audit row.

The takeover state is derived from the append-only audit log: the latest takeover or release row wins, so the state is always explainable after the fact.

## 3. Replay a stuck outbox message

Use when a write to a client system exhausted its retries (5 attempts, exponential backoff 1 s, 4 s, 16 s, 60 s) and sits dead-lettered. The DLQ-not-empty alert (15 minutes) points here.

1. List the dead letters: `GET /api/outbox?status=failed` (the console `/ops` dead-letter view shows the same rows). Only `failed` rows can be replayed.
2. Read the row before acting: `port`, `operation`, `attempts` (5 after the retry policy), `last_error` and the `idempotency_key` that identifies the logical write. If the error looks like a bad payload (rejected by the port schema), do not replay: fix the cause first, a poisoned write will fail again.
3. Replay: `POST /api/outbox/{id}/replay`. The row returns to `pending` with `attempts: 0` and the same idempotency key, so the next relay pass delivers it as the same logical write and can never double-apply.
4. Verify delivery: the row appears under `GET /api/outbox?status=api_confirmed`, and an `integration.write` event exists with `outcome: "delivered"` and the row's idempotency key.
5. Verify the audit: `outbox.replay_requested` records who replayed, the row, and the previous status, attempts and error.

Replaying a row that is not `failed` returns `409` with the current status. In this milestone only failed HireDesk rows are replayable (the relay's async-port set); WhatsApp rows deliver synchronously and confirm themselves.

## 4. Handle a Nómina360 outage

Nómina360 (HRIS/payroll) being down does not stop hiring: it stops exactly the flows that need it, and candidates never get silence (spec 06 section 2, degraded mode).

**Detect.**

1. `GET /health/adapters` shows `nomina360` with status `degraded` (the health probe failed or timed out; the probe budget is 2 seconds) plus a `failure_reason`. Check the other systems' statuses in the same response.

**What happens automatically.**

2. Only the flow that requires Nómina360 pauses (`tracker_completion`, the tracker gate on CSV truth). WhatsApp first contact, reminders and ShiftGrid matching keep running. A status of `unknown` never pauses anything: it is a visibility gap surfaced to a human, never a silent stop.
3. Every candidate whose event hits a paused flow receives the holding message from the versioned catalog, in their language, instead of silence: "Estamos teniendo un problema tecnico con uno de nuestros sistemas: tu solicitud sigue abierta y te escribimos en cuanto podamos continuar. Gracias por tu paciencia."
4. Each pause is recorded: audit rows `flow.paused` (actor `firstshift.degraded_mode`, with the flow and the required system), an escalation event the console shows, and the holding message as a confirmed `message.out` event. The application state is never touched by the pause.

**Verify during the outage.**

5. No new `tracker_completed` dispatches land in Nómina360 (the outbox shows no new `nomina360` writes failing).
6. Holding messages appear in the affected candidates' journeys; nothing else about their state changed.

**Recover.**

7. When the probe reports `ok` again, paused flows resume on their next event; no manual restart is needed. Confirm new `tracker_completed` events dispatch normally.
8. Read the nightly CSV reconciliation report (O12): every pending write is matched against the Nómina360 CSV, which is the truth. Writes the CSV confirms become `csv_confirmed`; writes missing from the CSV are downgraded and a `ReconciliationTask` opens, assigned to People Ops (record fix) while IT investigates the gateway. CSV rows with no FirstShift write are reported as `unexpected_in_csv` for People Ops to classify.
9. Close each reconciliation task with the compensating action below.

### Nómina360 create employee: compensating action

For a registration the agent wrote but Nómina360 never recorded (`missing_in_csv`), and which the nightly reconciliation downgraded:

1. People Ops creates the employee manually in Nómina360 from the candidate's complete document pack (the pack the agent already pre-collected).
2. Record the returned employee reference against the candidate in FirstShift and close the `ReconciliationTask` with it. Do not replay the original write if the employee may already exist: partial creation is a documented Nómina360 failure mode, and the idempotent replay reports success on the existing employee.
3. Verify on the next nightly run: the CSV shows the row and the reconciliation report moves the write from downgraded to confirmed.

## 5. Process an erasure request

A candidate (or their representative) asks FirstShift to delete their personal data. Laura Cebrián (DPO) owns the erasure procedure; the system records and enforces the safe path.

1. Record the request: `POST /api/erasure-requests` with body `{"candidate_id": "...", "reason": "..."}` and the `dpo` role. The endpoint never deletes data by itself: it records the `erasure.requested` audit row with who asked, when and why, status `requested`.
2. Confirm processing is stopped for that candidate: no further outbound messages or core transitions (a candidate's own withdrawal or erasure message already stops processing and starts the retention clock; scenario D7 pins this behavior).
3. The DPO executes the erasure per the retention policy in `docs/security-and-compliance.md`: delete or anonymize the candidate's personal data within the consented period, and keep every record the law requires.
4. Verify the audit trail survives intact: personal documents are referenced by id and never logged, so the erasure never needs to rewrite audit content.
5. **Known gap:** the pseudonymized audit tombstone (design row 32) is designed but not implemented yet. Until it lands, the erasure output is the deleted data plus the retained, already-pseudonymous audit trail.

## 6. Roll back a prompt version

Prompts live as versioned files in `app/prompts/<agent>.vN.md` (`recruit`, `onboard`, `pulse`; all at `v1` today). No prompt goes live without a passing eval report attached. The runner loads the file once at startup and stamps every `agent.turn` event with its `prompt_version`, so a regression is always attributable.

1. Identify the failing version from the `agent.turn` events (Langfuse trace or the console evals view) and the latest eval report in `evals/reports/`.
2. Pick the rollback target: the last version with a passing eval report.
3. Restore it: `git revert` the prompt change (or redeploy from the previous tag) so the file `app/prompts/<agent>.vN.md` matches the target version again. Note that `prompt_version` is fixed at deployment time (the `AgentRunner` constructor, default `v1`); there is no runtime switch, so a rollback is a redeploy of the previous file.
4. Restart or redeploy the agent service so the runner loads the restored file.
5. Verify: new `agent.turn` events carry the restored `prompt_version`, and a spot-check conversation behaves per the restored prompt.
6. Record the incident and open a fix task. The fix ships as a new version file (`vN+1`) with a passing eval report attached, never as an in-place edit of a version that has served live traffic.

## 7. Who to call for what

| Topic | Call | Why them |
| --- | --- | --- |
| GDPR, DPIA, erasure requests, retention, candidate notices | Laura Cebrián (DPO) | Owns the DPIA, written approval before any candidate contact, and the deletion rules |
| Client-system write paths, monitoring, alerts, secrets, Nómina360 gateway lead time | Hugo Andrade (IT) | Approves every write path and receives monitoring and alerts on each write |
| Nómina360 registrations, document packs, payroll hand-off | Sofía Marques (People Ops) | Owns Nómina360 registration and validates the document pack flow |
| Restaurant units, managers, coverage metric, rota escalations | Raúl Sempere (Area Ops) | Named the 12 + 3 units, commits managers, co-owns the coverage metric |
| Screening recommendations, human-signed rejects, decision queue staffing | Jordi Puig (TA) | Validates screening; every reject stays human-signed |
| Business sign-off, go/no-go, board reporting | Marta Ibáñez (CPO) | Owns the pilot's business decision |
| Agent behavior, integrations, evals, runbook gaps, on-call during the pilot | Vendor FDE team | Builds and operates the agent layer; reports weekly |
| Manager decision unresolved after the 8 h SLA | Area HRBP | The decision escalation timer hands the decision to the HRBP (state machine T3) |
| LearnBite hygiene module not completed before day 1 | Unit trainer | The trainer owns module completion and the snapshot flag |

Escalation rule of thumb: anything that touches a candidate's data or a consequential decision goes to the DPO or the human decision owner, never resolved by the agent; anything that touches a write to a client system goes to IT plus the vendor on-call; anything that blocks candidates (degraded mode holding, DLQ) goes to the vendor on-call with Ops informed.
