# Feature: F10 iteration-2

## Header

- **Objective:** one measured iteration per specs/05 section 4, second gap: language drift between the candidate's stated language and the copy the agent sends.
- **Status:** in progress
- **Branch:** feature/iteration-2, from dev (5040319, after iteration-1 merged).

## Specs

Source of truth: `specs/05-iteration-evals.md` section 4 (Observe, Hypothesize, Change one thing, Measure, Decide) and section 2 (deterministic checks must be 100%).

## The observed gap

Calibration report v1 named language drift as the second defect: `eval-p002` opens in Spanish, switches to Portuguese, then sends the offer in Spanish again. Root cause found in code, two layers:

1. `app/services/scripted.py::_SCRIPTED_BODIES` and `app/sim/dispatch.py::SIM_BODIES` hold every candidate-facing template in Spanish only (offer, nudge_1, nudge_2, interview_reminder, bench_offer, bench_reengagement, rejection).
2. `evals/run.py:335` builds the core snapshot with `language="es"` for every persona, so the language guardrail compares outbound tags against a hardcoded value. For Portuguese and English personas this makes `language_matches_candidate` pass without measuring anything.

The agent-loop replies (built in `evals/run.py` from the persona) are already language-aware; the drift comes from the canned outbox copy and the hardcoded snapshot language.

## Hypothesis

We believe resolving every candidate-facing template from the candidate's stated preferred language (es/pt/en) and carrying that language into the core snapshot will reduce outbound messages whose language differs from the candidate's stated language from the baseline count to 0, and raise the judge's language score on the affected conversations, because evidence E: both remaining sources of Spanish-only copy are the two dictionaries above, and the hardcoded snapshot language is the reason the guardrail never caught them.

## The single change

Language-aware candidate-facing copy, end to end: per-language variants of the seven candidate-facing templates, resolved from the candidate's `preferred_language` with Spanish only as the last-resort fallback when the language is genuinely unknown, plus the core snapshot language taken from the persona instead of a literal. The instrumentation is not a second behaviour change: it is what makes the existing guardrail measure the thing it claims to measure.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3 | Per-language candidate-facing templates (es/pt/en) in both dispatch paths, plus snapshot language from the persona | pending |
| T2 | S2 | Make the language guardrail non-vacuous: a RED test with a Portuguese candidate proves the check fails on Spanish-only copy | pending |
| T3 | S2,S4 | docs/iteration-log.md iteration-2 entry with hypothesis and numbers | pending |
| T4 | S4 | Fast then full suite seed 42, label v3; report before/after (drift count, judge language score) | pending |
| T5 | S5 | Keep or revert with numbers, close | pending |

## Open questions

- Portuguese and English offer copy is authored in this iteration (short, WhatsApp-sized, no promises). The tone review is a human task; flag any copy the owner wants changed.

## Log

- L1 (user, verbatim): "dale"
- L2: PR 32 (iteration-1) merged as 5040319 before starting; root cause located by reading both dictionaries and the snapshot construction.
