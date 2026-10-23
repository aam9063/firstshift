# Feature: F11 simulated-pilot-and-redteam

## Header

- **Objective:** turn the measured agent quality into a business story and a safety story: a 30-day simulated pilot (12 pilot vs 3 control restaurants) written as a weekly ops review, and a red-team suite whose every case ends in the designed safe behavior.
- **Status:** in progress
- **Branch:** feature/pilot-redteam, from dev (27cd8e2).

## Specs

Source of truth: `specs/05-iteration-evals.md` sections 5 and 6. Governing quotes:

- S1 (§5): "Run the full system over the 12 pilot restaurants for a simulated 30 days (clock fast-forward) with persona arrival rates matching the client's seasonality, and compare with the 3 control restaurants running the 'as-is' process model from discovery. Produce `docs/pilot-sim-day30.md` in the format of a real weekly ops review: headline numbers vs baseline, what went wrong, top escalations, decisions needed from the client."
- S2 (§5): "State its limits plainly: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect."
- S3 (§6): "run a dedicated suite of adversarial personas: prompt injection, attempts to extract other candidates' data, attempts to get an offer without approval, abusive language, a distressed candidate, a minor below the legal working age, a candidate who sends documents of someone else. Every case must end in the designed safe behavior. Record results in `evals/reports/redteam-v1.md`."
- S4 (§6): failures found by the red team are fixed as separate tasks with tests.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1,S2 | Pilot simulator: 30 simulated days, 12 pilot restaurants vs a 3-restaurant as-is control model, seasonality-aware arrivals | pending |
| T2 | S1,S2 | docs/pilot-sim-day30.md written as a weekly ops review with the simulation caveat visible | pending |
| T3 | S3 | Red-team suite: seven adversarial classes, each asserting the designed safe behavior | pending |
| T4 | S3,S4 | evals/reports/redteam-v1.md with per-case results; every failure fixed with a test or explicitly blocked | pending |
| T5 | - | Verify (suite, ruff, mypy), close, PR | pending |

## Constraints

- The simulation must reuse the real pipeline (persona simulator, agents, core, mocks) and must not weaken any deterministic check to make numbers look good.
- Control is a model of the as-is process from discovery (`discovery/funnel-baseline.md`), clearly labelled as a model.
- Every red-team case asserts a designed behavior from `design/guardrails.md` or the state machine invariants; no case may pass vacuously.
- No web/ changes.

## Open questions

- The pilot report's "decisions needed from the client" are written as if for Marta and Raul; they must trace to failure modes the simulation actually produced.

## Log

- L1 (user, verbatim): "listo. Dale a la F11"
- L2: PRs 35 (iteration-4) and 36 (signature diagnostics) merged as 19b0149 and 27cd8e2 before starting.
