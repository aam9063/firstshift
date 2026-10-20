# Feature: F05 solution-design

## Header

- **Objective:** generate genuinely different ways to hit the north star, choose one with explicit reasoning, and design it to plug into Lumbre's systems and routines.
- **Status:** closed, awaiting human review (PR open)
- **Next step:** F06 walking-skeleton after human review.
- **Branch:** feature/solution-design-options, from dev.
- **Scope split:** this session owns backend and infra only. The frontend (web/) is owned by a parallel session on feature/console-ui. Architecture docs here describe the console at spec level but no web/ code is touched.

## Specs

Source of truth: `specs/03-solution-design.md` (all sections). Governing quotes:

- S1 (section 1): at least 8 genuinely different options, each with one-line idea, which hypothesis it attacks, rough effort, risk, and what would have to be true. Include the obvious options and push for non-obvious ones.
- S2 (section 2): decision matrix scoring 1 to 5 on impact on TTFPS, impact on day-1 show rate, evidence strength, integration effort (inverse), compliance risk (inverse), manager behavior change required (inverse), demo-ability in 5 days; weight impact and evidence highest; weighted totals + paragraph on why the winner wins and what was consciously left out.
- S3 (PROMPTS.md F05, human decision): "First write design/options.md with at least 8 genuinely different options and design/decision-matrix.md, and stop to show me the matrix before writing the concept. That is the one product decision I want to make myself."
- S4 (sections 3-8, phase 2 after the human picks): concept.md, agents.md, state-machine.md, architecture.md, data-model.md, integration-contracts.md, guardrails.md, 5+ ADRs, constraint-to-guardrail mapping.

## Constraints

- Inputs: design/ problem-framing docs (hypotheses H1-H7, constraints, metric tree) and discovery/ evidence. Every scoring claim ties to evidence.
- Backend/infra only: no web/ edits in this branch.
- No em dash. English.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | design/options.md with 8+ options | done (12) |
| T2 | S2 | design/decision-matrix.md with weighted scores and rationale | done |
| T3 | S3 | STOP: show matrix to the human, record the concept choice | done: human approved the full matrix recommendation ("vamos con todo") |
| T4 | S4 | Phase 2 docs (concept, agents, state machine, architecture, data model, integration contracts, guardrails, ADRs) | done |

## Open questions

- The concept choice itself: reserved to the human per S3.

## Log

- L1 (user, verbatim): "console-ui es otra sesion abierta que esta trabajando en el front. Aqui seguimos con backend e infra solo"
- L2: Phase 1 (T1-T2) delegated to a worker; phase 2 starts only after the human picks the winning combination from the matrix.
- L3 (human decision, verbatim): "vamos con todo" = approved the matrix recommendation as-is: combined concept of O2 shift-matching + O4 bench + O5 pre-boarding + O6 commitment engine + O7 manager-WhatsApp + O8 check-ins (scoped) + O11 promise-to-payroll tracker + O12 CSV reconciliation gate, with O1 screening as first-contact component, O3 demand-triggered as phase-2, O9 referrals out of pilot, O10 voice as v2.
- L4: Phase 2 evidence: 10 docs committed (10c28a1). Cross-checks: all 22 constraints map to G1-G7 or INV-1..11; INV numbering unified (state machine owns INV-1..5, architecture/contracts own INV-6..11); all 22 state names present; 7 ADRs; 0 em dashes in design/; 3 Mermaid blocks structurally balanced (render check on the PR view). One interpreted timing recorded: bench fires at 48 h after first contact (spec says nudge 2 h, 24 h, then bench without a third timestamp).
