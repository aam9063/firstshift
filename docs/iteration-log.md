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

(placeholder: keep, revert or refine, with the numbers)

## Candidates for iteration-2

Picked from the same calibration read; one change per iteration, in this
order of observed impact:

1. **Language drift:** eval-p002 opens in Spanish, switches to Portuguese,
   then sends the offer in Spanish again. Candidate: pin every outbound to
   the candidate's stated preferred language at the reply composer.
2. **Repeated disclosure:** the AI consent ask repeats verbatim after the
   candidate already consented. Candidate: gate the consent ask on stored
   consent state instead of the turn counter.
3. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.
