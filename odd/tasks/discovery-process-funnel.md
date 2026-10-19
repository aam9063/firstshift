# Feature: F03 discovery-process-systems-funnel

## Header

- **Objective:** replace HQ's described process with evidence: as-is map, systems and data inventory, seeded mock dataset, re-runnable funnel, pain points and insights.
- **Status:** closed, awaiting human review (PR open)
- **Next step:** F04 problem-framing after human review.
- **Branch:** feature/discovery-process-funnel, stacked on feature/discovery-stakeholders-interviews (PR #12) because it cites F02 transcripts.

## Specs

Source of truth: `specs/01-discovery.md` sections 4, 5, 6 and 7 plus the baseline table in `specs/00-client-brief.md` section 4. Governing quotes:

- S1 (section 4): as-is Mermaid swimlane with lanes Candidate, Restaurant Manager, Talent team, People Ops/Payroll, Crew Trainer, Systems; mark handoffs, shadow paths, elapsed time per step, the 3 longest waits and 3 highest drop-off points; plus the paragraph "The process HQ described vs the process that actually runs".
- S2 (section 5): systems and data inventory (data objects, source of truth, read/write, latency, rate limits, auth, quirks, write approvers) ending with a "data object ownership" table; key finding to test: no system owns the transition from "hired" to "on the rota".
- S3 (section 6): mock dataset for the 15 pilot and control restaurants, last 6 months, seeded and reproducible in `mocks/seed/` with a fixed seed, consistent with the baseline table in the brief; funnel Applied > Contacted > Screened > Interview scheduled > Interview attended > Offer > Documents complete > On rota > Day 1 worked > Day 30 active > Day 90 active with counts, conversions and median elapsed times; re-runnable via `uv run python -m mocks.funnel`.
- S4 (TDD, AGENTS.md section 3): the funnel script gets a failing test first, asserting the seeded data reproduces the brief baseline within a stated tolerance.
- S5 (section 7): `pain-points.md` ranked by frequency x impact x cost with formula for the 12 pilot restaurants; `insights.md` with a 60-second readout at top and 5 to 8 non-obvious insights, each with evidence citations that resolve to real files.

## Constraints

- Dataset numbers must be consistent with `specs/00-client-brief.md` section 4 (medians within tolerance stated in T1 acceptance).
- Tolerance for the baseline test: conversion rates within 5 percentage points, median elapsed days within 1.0 day, attrition within 5 points.
- Every insight cites transcript IDs (F02 branch) or data files that exist.
- No em dash. English artifacts.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3,S4 | Seeded dataset in mocks/seed/ + mocks/funnel.py + tests, RED then GREEN | pending |
| T2 | S1 | discovery/as-is-process.md swimlane with waits and drop-offs | pending |
| T3 | S2 | discovery/systems-and-data.md inventory + ownership table | pending |
| T4 | S3 | discovery/funnel-baseline.md from script output | pending |
| T5 | S5 | discovery/pain-points.md and discovery/insights.md with evidence | pending |
| T6 | - | Exit verification and close | pending |

## Open questions

- None blocking. Shadow-path hires in the dataset: the seeded data models only the official funnel; Yolanda's maybes volume stays qualitative (transcript evidence), noted in insights.

## Log

- L1 (user request, verbatim): "continua, ya mergeare despues"
- L2: Branch stacked on F02 (PR #12 open); when #12 merges, this PR shows only the F03 delta.
- L3: Evidence (T1, code): RED observed (ModuleNotFoundError for mocks), then 12 passed (`uv run pytest`, includes health and metrics regression); ruff clean; `uv run python -m mocks.funnel` reproduces baseline within tolerance (never contacted 41.0%, median first contact 3.9 d, interview no-show 38.0%, offer-to-shift 9.5 d, day-1 no-show 17.9%, 90-day attrition 52.0%).
- L4: Evidence (T2-T5): as-is Mermaid passes structural lint (7 subgraphs/7 ends, classDefs consistent, no tabs); external renderer mermaid.ink is down from this environment (HTTP 400 even for trivial diagrams), final render check happens on the GitHub PR view, which renders Mermaid natively; 69 + 48 transcript citations across the four docs all resolve to existing lines (worker grep plus parent spot check, including a false-alarm misattribution check on [T-candidate-a-20] that proved correct).
- L5: Key finding confirmed with evidence: no system owns the hired-to-rota transition (five-step chain in systems-and-data.md); the seeded funnel's largest time sink is exactly that window (5.1 days median on-rota step).
- L6: Slice note: total authored lines exceed 4000 because mocks/seed/applications.csv (388 KB, 4500 rows) is generated data pinned byte-identical by test; reviewable code is tests/test_funnel.py, mocks/seed/generate.py and mocks/funnel.py.
