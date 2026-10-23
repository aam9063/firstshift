# Feature: F11 iteration-3

## Header

- **Objective:** one measured iteration per specs/05 section 4, third gap: the AI disclosure and consent ask repeat after the candidate has already answered.
- **Status:** closed (keep), awaiting review (PR open)
- **Branch:** feature/iteration-3, stacked on feature/iteration-2 (PR 33 still open).

## Specs

Source of truth: `specs/05-iteration-evals.md` section 4, plus guardrail G1/G2 (AI disclosure in the first message, consent captured with notice version before processing) in `design/guardrails.md`.

## The observed gap

The calibration transcripts show the consent ask twice in a row: an agent message asks for consent, the candidate answers affirmatively, and the next agent message asks for consent again before moving to screening (eval-p001, eval-p006, eval-p013, and others). The judge scores warmth and clarity down on those turns.

## Root cause

`evals/run.py::_scripted_reply` composes the reply from `_current_state(engine, run)`. The HireDesk webhook sends the first contact (the consent ask) without capturing consent, so on the candidate's first reply the application is still in `contacted`. The scripted reply for `("new", "contacted")` therefore emits the consent ask again, and only its tool call (`capture_consent`) records the consent. The candidate sees the same ask twice: once from the webhook, once from the agent turn that actually captures it.

## Hypothesis

We believe dispatching the candidate's consent from the outstanding ask before composing the reply (so the ask is emitted only while no consent record exists, and a reply to an outstanding ask captures consent first) will reduce duplicate consent asks in the transcript from the baseline count to 0, and raise the judge's warmth and clarity on the affected conversations, because evidence E: the only source of the duplicate ask is the `("new", "contacted")` branch composing before its own `capture_consent` tool call runs, and every affected transcript shows exactly one duplicate.

## The single change

Consent capture precedes reply composition on the reply to an outstanding ask: if a consent ask has been sent and no consent record exists, the candidate's reply is processed as consent (candidate_consents through the core) before the agent composes its next message; the consent ask itself is emitted only when no consent record exists and no ask is outstanding. No copy changes in this iteration.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3 | RED test: a scripted journey must show exactly one consent ask between first contact and screening | done |
| T2 | S3 | Implement the consent-before-reply rule in the eval path | done |
| T3 | S4 | docs/iteration-log.md iteration-3 entry, eval-v4 measurement (duplicate asks, deterministic checks, judge warmth/clarity) | done |
| T4 | S5 | Keep or revert with numbers, close | done: KEEP |

## Open questions

- The live WhatsApp webhook path has the same shape (it maps consent keywords deterministically); this iteration is scoped to the eval/scripted path where the measurement lives. If the same duplication appears in the webhook path, it is a named follow-up, not a second change.

## Log

- L1 (user, verbatim): "antes de empezar F11 soluciona A y B" and, in the follow-up choice, "solo las dos iteraciones pendientes" (iteration-3 and iteration-4 before F11).
- L2: PR 33 (iteration-2) still open when this branch started; it stacks on that branch and reconciles with dev after the merge.

- L3: Measure: duplicate consent asks 44 -> 0 across the full suite (fast subset 20 asks over 10 conversations -> 1 each); deterministic failures 0, every check 44/44; task success 44/44, day-1 show 0.923 unchanged; cost per hire 0.002633 -> 0.002116 USD (one fewer agent turn). Judge means reported, not decision-grade (ScriptedJudge noise, same property as iterations 1-2). Decision KEEP. Parent verified 343 tests, ruff, mypy.
