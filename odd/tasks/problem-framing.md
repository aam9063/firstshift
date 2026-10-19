# Feature: F04 problem-framing

## Header

- **Objective:** turn discovery into a sharp problem definition, measurable targets and explicit constraints, so Phase 3 designs for the real bottleneck and the pilot has signed success criteria.
- **Status:** closed, awaiting human review (PR #14)
- **Next step:** F05 solution-design: STOP at the decision matrix, that choice is the human's.

## Specs

Source of truth: `specs/02-problem-framing.md` (all sections). Governing quotes:

- S1 (section 1): the reframe in three layers (asked / need / blocks, the third from discovery evidence), then the problem statement in the exact template: "**For** [who] **at** [where], **when** [situation], **the current process** [what fails, with numbers], **which causes** [business consequence, with numbers]. **We will know it is solved when** [measurable outcome]." Every number traced.
- S2 (section 2): one JTBD per actor (candidate, restaurant manager, talent team, payroll, crew trainer, area ops), conflicts noted.
- S3 (section 3): metric tree under north star TTFPS (median days from application to end of first worked shift with hygiene module completed before starting); each metric with baseline and pilot target; guardrail metrics; attribution section honest about 3 control units and proposing a stronger option.
- S4 (section 4): 5 to 7 falsifiable hypotheses with testing metric and kill threshold, adjusted to discovery evidence.
- S5 (section 5): constraints grouped (legal/compliance, operational, technical) written as testable rules, including GDPR art 22, EU AI Act note on Annex III and dates under revision, food hygiene as precondition to tasks not hiring, no new app for managers, multi-tenant, Spanish first, documented APIs only, EU data residency, idempotent writes.
- S6 (section 6): at least 6 non-goals with one-line reasons.
- S7 (section 7): one-page pilot charter (problem, north star with baseline/target, guardrails, scope 12+3 x 90 days, roles, cadence, day-30 and day-90 go/no-go, exit plan with data deletion and conversation handover).

## Constraints

- Every number traces to `specs/00-client-brief.md`, `discovery/funnel-baseline.md` or a transcript ID.
- Files land in `design/`: problem-statement.md, metric-tree.md, hypotheses.md, constraints.md, non-goals.md, assumptions.md, pilot-charter.md.
- No code. No em dash. English.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1,S2 | problem-statement.md (reframe, template statement, JTBD) | done |
| T2 | S3 | metric-tree.md with TTFPS, targets, guardrails, attribution | done |
| T3 | S4,S5,S6 | hypotheses.md, constraints.md, non-goals.md, assumptions.md | done |
| T4 | S7 | pilot-charter.md, one page | done |
| T5 | - | Trace check (every number cited), close, PR | done |

## Open questions

- None blocking. Attribution weakness (3 control units) is handled in the charter with a staggered-rollout option as the spec requires.

## Log

- L1 (user request, verbatim): "continua, ya mergeare despues" (F03 CI was green, so F04 proceeds stacked).
- L3: Verification (T5): problem statement matches the exact template with all bold connectors and a traced-number table (26 source references); metric tree derives TTFPS baseline 27.3d (funnel stage medians) and target 14d with visible arithmetic; 7 hypotheses with kill thresholds; 24 constraints; 9 non-goals; 12 assumptions; charter 51 lines. 0 em dashes in design/. Offer-acceptance has no funnel baseline: instrumented-in-pilot commitment marked in metric-tree and H2.
