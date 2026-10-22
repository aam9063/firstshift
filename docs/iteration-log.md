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
   consent state instead of the turn counter.
3. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.

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
   consent state instead of the turn counter.
2. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.

Also observed this iteration, outside the one-change rule: the intake first
message and its quick replies are Spanish-only for every candidate (the
webhook has no language at intake); low priority, it precedes any stated
preference.
