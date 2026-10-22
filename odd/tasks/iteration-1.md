# Feature: F09 iteration-1

## Header

- **Objective:** one measured iteration per specs/05 section 4: pick the single largest gap, state the hypothesis, change one thing, measure with the same seed, keep or revert, publish eval-v2.
- **Status:** in progress
- **Branch:** feature/iteration-1, stacked on feature/eval-harness (PR 30 still open).

## Specs

Source of truth: `specs/05-iteration-evals.md` section 4. Governing quotes:

- S1: "**Observe:** read the latest report and pick the single largest gap against a Phase 2 target or guardrail."
- S2: "**Hypothesize:** write in `docs/iteration-log.md`: "We believe changing X will improve metric M from a to b because evidence E.""
- S3: "**Change one thing:** a prompt version, a policy rule, a timer, a message template or a tool. Not several at once."
- S4: "**Measure:** run the fast suite, then the full suite with the same seed."
- S5: "**Decide:** keep, revert or refine. Record the decision and the numbers."

## The observed gap

F08 calibration (evals/reports/calibration-v1-report.md) inspected the transcripts and found a deterministic defect, not a taste disagreement: `eval-p002` delivers the raw internal identifier `bench.reserve backup` to the candidate as a message body. Root cause: `app/sim/dispatch.py::_channel_message` falls back to `f"Lumbre Burger: {template.replace('_', ' ')}"` whenever a core outbox kind has no configured body template. Every such kind leaks its internal name into candidate-facing text.

## Hypothesis

We believe rejecting internal-identifier bodies at the channel boundary (a whitelist of candidate-facing templates, internal recipients get their own safe bodies, unknown kinds are never delivered to a candidate) will remove leaked internal identifiers from candidate-facing messages (from at least 1 observed in the baseline to 0) and raise the judge's clarity and language scores on the affected conversations, because evidence E: the only fallback path that can produce such a body is that single line, and the calibration transcripts show the leak reaching the candidate in eval-p002.

## Measurements

- New deterministic check: `no_internal_identifiers_in_candidate_messages` (must be 0 failures; it is a guardrail, so a violation fails the suite).
- Judge (live, gpt-4.1-mini, rubrics v1) mean clarity and language on the full suite, compared with eval-v1.
- Task success, fairness and cost must not regress.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3 | RED test: an unknown/internal template must never become candidate-facing text | pending |
| T2 | S3 | Implement the channel-body guard (whitelist + internal recipients + no candidate fallback) | pending |
| T3 | S1 | New deterministic check for internal identifiers (with a violating fixture) | pending |
| T4 | S2 | docs/iteration-log.md with the hypothesis in the required form | pending |
| T5 | S4 | Fast then full suite with seed 42, label v2, live judge on the full set | pending |
| T6 | S5 | Decide keep/revert, publish eval-v2, close | pending |

## Open questions

- None blocking. The language drift in the same conversation is a separate gap and belongs to iteration-2 (one change per iteration).

## Log

- L1 (user, verbatim): "porque sigue el archivo de calibration en dev sin commitear? o ya lo has metido tu por otro lado?"
- L2: PR 30 CI green on e00edae; iteration starts stacked on it because the eval runner and judge live there.
- L3: Root cause located at app/sim/dispatch.py::_channel_message fallback; the same pattern exists in app/services/scripted.py for scripted journeys (checked there too).
