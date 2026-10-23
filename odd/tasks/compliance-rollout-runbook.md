# Feature: F13 compliance-rollout-runbook

## Header

- **Objective:** the pack a client's IT, DPO and operations leads need to say yes, plus the plan to change how managers and HR actually work: security and compliance, rollout waves, manager quickstart, runbook, and the day-90 simulated steering readout.
- **Status:** in progress
- **Branch:** feature/compliance-rollout, from dev (8e4a20b).

## Specs

Source of truth: `specs/06-integration-rollout.md` sections 3, 4, 5 and 6. Governing requirements:

- S1 (§3): `docs/security-and-compliance.md` for IT (Hugo) and the DPO (Laura): data flow diagram with every personal-data field, where it is stored, for how long and who can read it; record of processing activity draft; legal basis per purpose; candidate notice text ES/PT/EN; retention for rejected and benched candidates plus the erasure procedure and its audit; AI transparency and human oversight; access control (SSO via Microsoft 365, roles Talent/DPO/Ops/Admin, least privilege per view and action, secrets, encryption, EU hosting); DPIA outline (the DPO owns the final one); model and prompt change management (no prompt goes live without a passing eval report).
- S2 (§4): `docs/rollout-plan.md` with waves 0 to 3 (shadow, assisted, pilot, expand), each with scope, entry and exit criteria; the concrete change-management moves (Raul presents the day-30 numbers, managers get a 10-minute in-restaurant onboarding, Yolanda's maybes imported into the bench with consent, the talent team's new weekly routine, payroll receiving complete packs, a WhatsApp FEEDBACK keyword).
- S3 (§5): `docs/runbook.md` covering at least: pause the agent for one restaurant, take over a conversation, replay a stuck outbox message, handle a Nomina360 outage, process an erasure request, roll back a prompt version, who to call for what.
- S4 (§6): extend the simulated pilot to 90 days and write `docs/pilot-sim-day90.md` as a steering-committee readout: results vs the charter, cost per hire vs baseline with the formula, what was learned, what would change, a go/no-go recommendation with conditions for expansion, and the simulation caveat visible.
- S5 (§4): `docs/training/manager-quickstart.md`, one page, mostly screenshots of the WhatsApp messages managers receive.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | security-and-compliance.md with the data flow, ROPA draft, retention, transparency, access control, DPIA outline and prompt change management | pending |
| T2 | S2 | rollout-plan.md with the four waves and the change-management moves | pending |
| T3 | S3 | runbook.md with the seven operations | pending |
| T4 | S4 | 90-day pilot simulation and docs/pilot-sim-day90.md | pending |
| T5 | S5 | training/manager-quickstart.md | pending |

## Constraints

- Documentation phase: checks are structural (every required section present), factual (numbers trace to the brief, evals or the simulation output) and visual (Mermaid valid). No code changes.
- Every claim about a real-world legal obligation is stated as a design requirement with its source section, never as legal advice.
- Simulation caveat visible in `pilot-sim-day90.md`.
- English, no em dash.

## Log

- L1 (user, verbatim): "todo en dev. continúa"
- L2: dev at 8e4a20b; the 90-day run uses `uv run python -m evals.pilot --days 90 --seed 42 --label day90`.
