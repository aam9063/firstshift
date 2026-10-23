# Iteration log (specs/05-iteration-evals.md section 4)

One measured iteration per entry: observe the largest gap, hypothesize, change
one thing, measure with the same seed, decide keep/revert/refine.

## Iteration 1: channel-body guard

- **Date:** 2025-03-03
- **Baseline:** calibration-v1 (evals/reports/calibration-v1-report.md) and
  eval-v1 (seed 42).

### Observe

Reading calibration-v1, the single largest deterministic gap against the
Phase 2 transparency target: `eval-p002` delivers the raw internal
identifier `bench.reserve backup` to the candidate as a message body. Root
cause: `app/sim/dispatch.py::_channel_message` falls back to
`f"Lumbre Burger: {template.replace('_', ' ')}"` whenever a core outbox kind
has no configured body template; the same fallback exists in
`app/services/scripted.py::ScriptedJourney._whatsapp_outbound`. Every such
kind leaks its internal name into candidate-facing text.

### Hypothesize

We believe rejecting internal-identifier bodies at the channel boundary (a
whitelist of candidate-facing templates, internal recipients get their own
safe bodies, unknown kinds are never delivered to a candidate) will improve
the deterministic guardrail `no_internal_identifiers_in_candidate_messages`
from at least 1 failed conversation in the baseline to 0, and the judge's
mean clarity and language scores on the affected conversations upward,
because evidence E: the only code path that can produce such a body is that
single fallback line (verified by reading both dispatch paths), and the
calibration transcripts show the leak reaching the candidate in eval-p002.

### Change

One thing: the channel-body guard.

- Explicit whitelist `CANDIDATE_FACING_TEMPLATES` of templates with real
  human copy (offer, rejection, nudge_1, nudge_2, interview_reminder,
  bench_offer, bench_reengagement).
- Separate set `INTERNAL_RECIPIENT_KINDS` (trainer.notify,
  bench.reserve_backup, backup.activate) and `INTERNAL_RECIPIENT_REFS`
  (manager-sim, hrbp-sim, trainer-sim, bench-backup-sim).
- Body resolution order: configured template copy, then the internal-recipient
  safe body (internal recipients only), never a candidate-facing fallback
  identifier. An unknown kind addressed to a candidate is not delivered; the
  suppression is recorded as a warning log so it stays observable (rule 7).
- New deterministic check `no_internal_identifiers_in_candidate_messages`
  scanning message.out bodies (registered in CHECK_NAMES, with a violating
  fixture in tests).

No message copy changes in this iteration.

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v2`.

- Fast suite (10 personas): deterministic failures 0; leak-carrying
  conversations 8/10 in the v1 baseline subset, 0/10 in v2.
- Full suite (44 personas): deterministic failures 0 (44/44 on
  `no_internal_identifiers_in_candidate_messages`); leak-carrying
  conversations 39/44 in eval-v1, 0/44 in eval-v2.
- Judge mean score: 2.768 (v1) to 2.945-3.009 across three v2 runs of the
  same code and seed; task success, day-1 show rate and cost per hire
  unchanged (1.0, 0.923, 0.002633 USD).
- Harness reproducibility observation for the keep/revert decision: the
  judge mean varies 2.945-3.009 across three v2 runs of identical code at
  seed 42 (sim clocks anchor to wall-clock start time), while deterministic
  checks and the leak count are stable at 0. Pre-existing harness property,
  not a change of this iteration.
- RED evidence: against the pre-fix code, both dispatch paths returned
  `Lumbre Burger: bench.reserve backup`, `Lumbre Burger: trainer.notify` and
  `Lumbre Burger: some.unknown kind` for kinds without configured copy
  (observed directly and via tests/test_channel_body_guard.py).

### Decision

**Keep.** The single change moved the deterministic guardrail from 39 leak-carrying conversations in eval-v1 to 0 in eval-v2 (fast subset 8/10 to 0/10), with deterministic failures at 0, task success at 1.0, day-1 show rate at 0.923 and cost per hire at 0.002633 USD all unchanged. The judge mean rose from 2.768 to 2.945-3.009, but that number is not the basis of this decision: the run-to-run variation across identical seed-42 runs (2.945-3.009) is wider than a single iteration could claim, so the keep rests on the deterministic metric, which is exact and reproducible. Reverting is not justified: no configured message copy changed (PRESERVE tests pin the exact bodies) and the only behavioural delta is that a candidate-facing kind without configured copy is suppressed and logged instead of leaking its identifier.

Follow-up work this measurement exposed, outside the one-change rule:

- Harness reproducibility: the judge mean should be stable for identical code and seed. The simulated clocks anchor to wall-clock start, so conversations differ slightly between runs. Candidate: derive the sim base time from the seed.
- `evals/.cache` judge cache entries from these runs are gitignored and do not affect CI.

## Candidates for iteration-2

Picked from the same calibration read; one change per iteration, in this
order of observed impact:

1. **Language drift:** eval-p002 opens in Spanish, switches to Portuguese,
   then sends the offer in Spanish again. Candidate: pin every outbound to
   the candidate's stated preferred language at the reply composer.
   **Done:** iteration 2 below.
2. **Repeated disclosure:** the AI consent ask repeats verbatim after the
   candidate already consented. Candidate: gate the consent ask on stored
   consent state instead of the turn counter. **Done:** iteration 3 below.
3. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message. **Done:** iteration 4 below.

## Iteration 2: language-aware candidate-facing copy

- **Date:** 2025-03-04
- **Baseline:** eval-v2 (seed 42, full suite) and the calibration read that
  named language drift as the second defect (eval-p002: opens in Spanish,
  switches to Portuguese, receives the offer in Spanish again).

### Observe

Reading eval-v2 with the exact-body method over the stored transcripts, the
single largest remaining deterministic gap against C-O4 (language matches
candidate): 25 outbound candidate-facing messages across 21 of 44
conversations were in Spanish while the candidate had stated Portuguese or
English (21 offers, 4 nudges). Root cause found in code, two layers:

1. The seven candidate-facing templates (offer, nudge_1, nudge_2,
   interview_reminder, bench_offer, bench_reengagement, rejection) exist only
   in Spanish in both dispatch dictionaries (`app/services/scripted.py::
   _SCRIPTED_BODIES` and the `app/sim/dispatch.py` resolution into it).
2. `evals/run.py` built the core snapshot with `language="es"` for every
   persona, and the canned outbox bodies carried no language tag at all, so
   the `outbound_language_matches` guardrail had nothing to compare for them:
   it passed without measuring anything (proven vacuous by a RED test).

The agent-loop replies were already language-aware; the drift comes from the
canned copy and the invisible tags.

### Hypothesize

We believe resolving every candidate-facing template from the candidate's
stated preferred language (es/pt/en, Spanish only as the documented last
resort when the language is genuinely unknown) and carrying the persona's
language into the core snapshot will reduce outbound messages whose language
differs from the candidate's stated language from 25 to 0 (the 21
post-statement drifts to 0) and keep deterministic failures at 0 with the
language guardrail now non-vacuous, because evidence E: both remaining
sources of Spanish-only candidate copy are the two dispatch dictionaries, and
the hardcoded snapshot language plus the untagged canned bodies are the reason
the guardrail never caught them.

### Change

One thing: language-aware candidate-facing copy, end to end.

- Per-language variants (es/pt/en) of the seven candidate-facing templates in
  both dispatch paths, resolved from `candidate.preferred_language`; Spanish
  is the documented last resort only when the language is unknown or
  unsupported. The variants keep the meaning of the Spanish originals, stay
  WhatsApp-sized and add no promises. Portuguese and English copy is authored
  in this iteration; its tone review is a human task.
- Both dispatch paths tag candidate-facing outbound with the resolved
  language (message.out payload and outbox row): the instrumentation, not a
  second behaviour change.
- `evals/run.py` carries the persona's language into the core snapshot
  instead of the literal `"es"`.
- The guardrail is non-vacuous: after the candidate's first inbound message,
  a candidate-facing body must carry a language tag equal to the stated
  preference; untagged or mismatched is a violation. Messages sent before the
  candidate first spoke (the intake first message, timer nudges while
  unanswered) use the intake default and cannot contradict a preference not
  yet stated.
- Internal-recipient bodies from iteration-1 (decision_request,
  decision_reminder, decision_escalation, no_show, interview_reoffer,
  backup_activate) are not candidate-facing and are unchanged.

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v3`.

- Drift count (exact template-body match over the stored transcripts,
  eval-v2.json vs eval-v3.json): 25 to 4 drift messages across the full
  suite; post-statement drift 21 to 0. The 4 remaining are `nudge_1` fired
  before the persona's first reply (late_20h personas P010, P013, P027,
  P044): the candidate had not stated a language yet, so the intake default
  applied, and the non-vacuous guardrail tolerates exactly that case.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, `outbound_language_matches` 44/44
  passed with the check now verifying tags on every candidate-facing body.
- Judge mean 2.945 to 3.050 across three v3 full runs of identical code and
  seed (3.036, 2.945, 3.050); language score by stated language es 2.545
  to 3.045, pt 2.636 to 3.818, en 3.273 to 3.455. Not decision-grade:
  ScriptedJudge scores are deterministic digests keyed by conversation id and
  trace ids carry a fresh random token per run, so the run-to-run variation
  is wider than the effect (the same harness property iteration-1 recorded).
- Task success 44/44, day-1 show rate 0.923 and cost per hire 0.002633 USD
  all unchanged.
- RED evidence: against the pre-fix code, both dispatch paths returned the
  Spanish offer body for Portuguese and English candidates (six copy tests
  failed), and the language guardrail passed on an untagged Spanish offer
  body sent to a Portuguese candidate (vacuous, observed via
  tests/test_language_copy.py).

### Decision

**Keep.** The deterministic metric is exact: post-statement language drift
went from 21 messages in 21 conversations in eval-v2 to 0 in eval-v3, with
deterministic failures at 0 and the guardrail now measuring the candidate's
real stated language instead of passing vacuously. Task success, day-1 show
rate and cost per hire are unchanged. The 4 remaining pre-statement nudges
are the designed intake default, not drift; removing them would require the
webhook to capture language at intake, which is a different change. The judge
numbers are reported but not the basis of the decision (noise, see above).
Reverting is not justified: PRESERVE tests pin the Spanish originals for es
candidates and the unchanged internal-recipient bodies, and the only
behavioural delta is that candidate-facing copy follows the stated language.

Next candidates for iteration-3, in this order of observed impact:

1. **Repeated disclosure:** the AI consent ask repeats verbatim after the
   candidate already consented. Candidate: gate the consent ask on stored
   consent state instead of the turn counter. **Done:** iteration 3 below.
2. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.

Also observed this iteration, outside the one-change rule: the intake first
message and its quick replies are Spanish-only for every candidate (the
webhook has no language at intake); low priority, it precedes any stated
preference.

## Iteration 3: consent captured before the reply to the ask

- **Date:** 2025-03-05
- **Baseline:** eval-v3 (seed 42, full suite) and the observed gap recorded
  in odd/tasks/iteration-3.md (eval-p001, eval-p006, eval-p013 and every
  other transcript: the consent ask twice in a row).

### Observe

Reading the eval-v3 transcripts with an exact match over the consent-ask
wording of both scripted sources, the single largest remaining deterministic
gap against G2 (consent captured with notice version, ask never repeated):
88 agent consent asks across the 44 conversations, 2 per conversation, so
every conversation asked twice (fast-suite subset: 20 asks over 10
conversations). The candidate answers the first contact's ask and the next
agent message asks again before moving to screening. Root cause found in
code, one layer: `evals/run.py::_scripted_reply` composes the reply from
`_current_state`. The HireDesk webhook sends the first contact (the consent
ask) without capturing consent, so on the candidate's first reply the
application is still in `contacted`; the scripted reply for
`("new", "contacted")` emits the consent ask again and only its own
`capture_consent` tool call records the consent. The candidate sees the same
ask twice: once from the webhook, once from the agent turn that captures it.

### Hypothesize

We believe dispatching the candidate's consent from the outstanding ask
before composing the reply (so the ask is emitted only while no consent
record exists, and a reply to an outstanding ask captures consent first)
will reduce duplicate consent asks in the transcript from 44 to 0 and raise
the judge's warmth and clarity on the affected conversations, because
evidence E: the only source of the duplicate ask is the
`("new", "contacted")` branch composing before its own `capture_consent`
tool call runs, and every affected transcript shows exactly one duplicate.

### Change

One thing: consent capture precedes reply composition on the reply to an
outstanding ask.

- `evals/run.py::drive_conversation`: when a persona reply arrives while a
  consent ask is outstanding (state `contacted`, no `Consent` row),
  `_capture_outstanding_consent` dispatches `candidate_consents` through the
  core (candidate actor, the real `contacted` to `consented` transition with
  its `consent_notice_shown` guard) and stores the `Consent` row (channel,
  purpose, notice version, simulated timestamp) before the agent composes
  its next message.
- `evals/run.py::_scripted_reply`: the consent ask is composed only while no
  consent record exists; once consent is stored the conversation moves on.
- As before (the `capture_consent` tool path), the scripted eval treats the
  candidate's first reply as the consent reply regardless of its wording,
  and the tool allow-list and the `capture_consent` tool behaviour are
  untouched (`app/agents/services.py` unchanged).

No message copy changes in this iteration.

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v4`.

- Duplicate consent asks (exact consent-ask match over the stored
  transcripts, eval-v3.json vs eval-v4.json): 88 asks in 44 conversations
  (44 duplicates) to 44 asks in 44 conversations (0 duplicates); fast
  subset 20 asks over 10 conversations to 10 (one per conversation, the
  webhook first contact). In both v4 runs (fast and full) the duplicate
  count is 0.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, every check 44/44.
- Task success 44/44 and day-1 show rate 0.923 unchanged. Cost per hired
  candidate 0.002633 to 0.002116 USD: one scripted agent turn fewer per
  conversation, because consent capture no longer costs a dedicated turn.
- Judge mean 3.050 (v3) to 2.845 and 3.018 across two v4 full runs of the
  same code and seed; clarity 2.909 to 2.636 and 2.705, warmth 3.205 to
  3.000 and 3.159. Not
  decision-grade: ScriptedJudge scores are deterministic digests keyed by
  conversation id, and removing one agent turn changes the conversation
  shape those digests read (the same harness property iterations 1 and 2
  recorded), so the run-to-run variation is wider than the effect.
- RED evidence: against the pre-fix code,
  tests/test_consent_ask_once.py found 2 consent asks per scripted journey
  for both the instant and the late_20h persona (the second ask after the
  candidate had already answered); the first ask was already the first
  outbound message, so the duplicate was the only violation.

### Decision

**Keep.** The deterministic metric is exact: duplicate consent asks went
from 44 conversations in eval-v3 to 0 in eval-v4, with deterministic
failures at 0, task success and day-1 show rate unchanged, and consent now
captured before any processing continues (G2: exactly one `Consent` row,
with the notice version, per conversation). The judge numbers are reported
but not the basis of the decision (noise, see above). Reverting is not
justified: no message copy changed, the tool allow-list and the
`capture_consent` tool behaviour are pinned unchanged, and the only
behavioural delta is that the ask is emitted once and consent is captured
on the reply that answers it.

Next candidate for iteration-4: three questions per message, the screening
message asks three questions at once (work permit, age, commute), which the
judge scores low on brevity and clarity; candidate: split screening into
one question per message.

Also observed this iteration, outside the one-change rule: the live WhatsApp
webhook path has the same shape (it maps consent keywords deterministically);
scoping note in odd/tasks/iteration-3.md, a named follow-up if the same
duplication appears there, not a second change in this iteration.

## Iteration 4: screening asks one question per turn

- **Date:** 2025-03-06
- **Baseline:** eval-v4 (seed 42, full suite) and the observed gap recorded
  in odd/tasks/iteration-4.md: every conversation carries one screening
  message that asks three questions in a single turn (work permit, minimum
  age, commute), and the clarity-v1 anchor 2 ("several questions at once")
  and brevity-v1 anchor 2 ("three or more distinct ideas") describe exactly
  that shape.

### Observe

Reading the eval-v4 transcripts with an exact match over the screening
wording of the scripted source, the single largest remaining conversation
quality gap: 44 of 44 conversations contain one agent message asking all
three screening questions at once ("Gracias. Tres preguntas: ¿puedes
trabajar en España? ¿Tienes 18 o más? ¿Llegas bien al local?", and the
Portuguese and English equivalents). Root cause found in code, one layer:
`evals/run.py::AGENT_BODIES["screening"]` is a single string per language
with the three questions, and `_scripted_reply` for `consented` emits it in
one turn while its `save_screening_answers` tool call captures all three
answers at once. Nothing in the flow supports answering one question at a
time.

### Hypothesize

We believe asking the three screening questions in three separate turns,
with each answer captured before the next question, will raise the judge's
clarity and brevity scores on the screening turn and remove the
multi-question message from every conversation (count to 0), because
evidence E: the only source of the three-question message is the single
`screening` body, and the rubric anchors score multi-question turns down
explicitly.

### Change

One thing: screening becomes three turns, one question each.

- `evals/run.py`: `AGENT_BODIES["screening"]` is replaced by
  `SCREENING_QUESTIONS`, the three ordered per-language question bodies
  (right to work, minimum age, distance). The first question keeps the
  "three questions, one at a time" framing so the candidate knows why more
  messages are coming (and the consent-once test's screening locator,
  `tests/test_consent_ask_once.py`, keys on the same framing). No other
  copy changed; the tool allow-list is untouched.
- `_scripted_reply` for `consented`: while questions are outstanding the
  flow stays in `consented` and each reply is answered with the next
  question (`save_language_tag` still runs on the first). After the third
  question is answered, the reply runs `save_screening_answers` (same
  arguments as before, so the core receives the same facts) and composes
  the proposal exactly as the old screening-state turn did;
  `get_open_shifts` and `propose_shifts` execute inside that same turn,
  after the transition to `screening`, within the untouched allow-list.
- `_handle_silence`: a candidate who goes silent while screening questions
  are outstanding (now inside `consented`) gets the same graceful ending
  the screening state had: the bench message plus two system dispatches,
  `screening_starts` then `benched_with_consent` (the bench transition
  only exists from `screening`).

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v5`.

- Multi-question conversations (exact screening-wording match over the
  stored transcripts, eval-v4.json vs eval-v5.json): 44 of 44 to 0 of 44;
  fast subset (the stable first-10 prefix, contained in both full runs)
  10 of 10 to 0 of 10. All 44 v5 conversations carry the one-at-a-time
  opener and three separate question turns.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, every check 44/44.
- Task success 44/44, day-1 show rate 0.923 and the 39 hires unchanged:
  every conversation reaches the same end state with the same screening
  facts captured (one `save_screening_answers` effect, eligibility ok,
  strictly after the third question; pinned by
  tests/test_screening_one_question.py).
- Cost per hired candidate 0.002116 to 0.002939 USD (166 to 249 agent
  turns): each complete conversation now has two more scripted agent turns,
  the direct and intended cost of asking one question per turn.
- Judge clarity 2.705 to 2.977, brevity 3.227 to 3.114, mean 3.018 to 3.041
  (v5 run 1); across two v5 full runs of the same code and seed the means
  move again (run 2: clarity 3.432, brevity 3.091, mean 3.168). Not
  decision-grade: ScriptedJudge scores are deterministic digests keyed by
  conversation id, trace ids carry a fresh random token per run, and the
  conversation shape changed (two extra turns), so the digests read a
  different shape every run (the same harness property iterations 1 to 3
  recorded); the run-to-run clarity spread (2.977 to 3.432) is wider than
  any single-iteration effect could claim.
- RED evidence: against the pre-fix code,
  tests/test_screening_one_question.py failed 9 tests: the single screening
  message matched three screening-question patterns (3 failures), the three
  questions were not three separate consecutive turns (3 failures), and the
  `save_screening_answers` effect was not strictly after a third question
  turn (3 failures). The same-end-state and silent-candidate tests passed
  before and after (preserve).

### Decision

**Keep.** The deterministic metric is exact: conversations containing a
multi-question message went from 44 of 44 in eval-v4 to 0 of 44 in eval-v5,
with deterministic failures at 0, task success 44/44, day-1 show rate 0.923
and the 39 hires unchanged, and the screening facts still captured exactly
once, after the third question. The judge numbers are reported but not the
basis of the decision (noise, see above). Reverting is not justified: the
proposal, booking, bench and every other state's copy are pinned unchanged,
the tool allow-list is untouched, and the only behavioural deltas are that
screening asks one question per turn and that a candidate silent mid-
screening gets the same consented bench ending they would have got from
screening. The cost per hire rose by the two extra agent turns per
conversation; that is the measured price of the change, accepted because
the deterministic defect it removes is exact and every guardrail held.

Next candidates for iteration-5, in this order of observed impact:

1. **Intake language capture:** the intake first message and its quick
   replies are Spanish-only for every candidate (the webhook has no
   language at intake), so pre-statement nudges and the first contact stay
   Spanish for Portuguese and English candidates (observed in iteration 2).
2. **Harness reproducibility:** the judge mean should be stable for
   identical code and seed; trace ids carry a fresh random token per run
   and the ScriptedJudge digests follow them (observed in iterations 1 to
   4). Candidate: derive the sim base time and the trace token from the
   seed.
3. **Live judge calibration:** ScriptedJudge cannot measure conversation
   quality at all; its scores are digests. Candidate: wire the live judge
   port against the calibrated rubrics and report agreement on the 15
   hand-labeled conversations.
