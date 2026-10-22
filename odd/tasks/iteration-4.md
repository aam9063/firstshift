# Feature: F11 iteration-4

## Header

- **Objective:** one measured iteration per specs/05 section 4, fourth gap: the screening message asks three questions at once.
- **Status:** in progress
- **Branch:** feature/iteration-4, stacked on feature/iteration-3 (PR 34 open).

## Specs

Source of truth: `specs/05-iteration-evals.md` section 4; the judge rubrics `evals/judge/rubrics/clarity-v1.md` (anchor 2: several questions at once) and `brevity-v1.md` (anchor 2: three or more distinct ideas).

## The observed gap

Every conversation carries one screening message that asks three questions in a single turn: work permit, minimum age and commute (es/pt/en). The calibrated judge scored clarity 2-3 on these conversations against a human scale of 4-5, and the rubric anchors describe exactly this shape. It is also the last item on the iteration candidate list.

## Root cause

`evals/run.py::AGENT_BODIES["screening"]` is a single string per language containing three questions, and `_scripted_reply` for `consented` emits it in one turn while its tool call captures all three answers at once (`save_screening_answers`). Nothing in the flow supports answering one question at a time.

## Hypothesis

We believe asking the three screening questions in three separate turns, with each answer captured before the next question, will raise the judge's clarity and brevity scores on the screening turn and remove the multi-question message from every conversation (count to 0), because evidence E: the only source of the three-question message is the single `screening` body, and the rubric anchors score multi-question turns down explicitly.

## The single change

Screening becomes three turns, one question each: the flow stays in `consented` until the three answers are captured, each turn asks exactly one question, and `save_screening_answers` runs after the third answer (so the core still receives the same facts, unchanged). Copy is split per language, one question per message; no other copy changes.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3 | RED test: no conversation contains a message asking more than one screening question; three question turns in order | pending |
| T2 | S3 | Implement the one-question-per-turn screening flow in the eval path | pending |
| T3 | S4 | docs/iteration-log.md iteration-4 entry, eval-v5 measurement (multi-question count, deterministic checks, judge clarity/brevity) | pending |
| T4 | S5 | Keep or revert with numbers, close | pending |

## Open questions

- The live WhatsApp path composes screening from the same scripted dictionary only in the sandbox; the production conversation layer will follow `design/agents.md` (one question per turn) once the live model is enabled. Named follow-up, not a second change.

## Log

- L1 (user, verbatim): "antes de empezar F11 soluciona A y B" with the chosen scope "solo las dos iteraciones pendientes".
- L2: Stacks on feature/iteration-3 because PR 34 is still open; reconciles with dev after its merge.
