# Feature: console-views

## Header

- **Objective:** complete the console views from `specs/04b-console.md` sections 3.5-3.9: restaurants, operations, evals, compliance and the simulator, on real backend data.
- **Status:** in progress
- **Branch:** feature/console-views, from dev (8e4a20b), in the `console-live` worktree.

## Specs

Source of truth: `specs/04b-console.md` sections 3.5, 3.6, 3.7, 3.8, 3.9, 4 and 4.5; `web/DESIGN.md`; the existing `web/src/api/client.ts` and `web/src/api/types.ts`; the running backend on `http://localhost:8001`.

- S1 (3.5): `/restaurants` grid of the 15 restaurants (pilot/control) with coverage gaps for the next 14 days, bench size, open candidates and manager decision median; `/restaurants/:id` with the open-shifts calendar, which candidate is matched to which shift, and the bench.
- S2 (3.6): `/ops` queues: manager decisions pending with SLA countdown, escalated conversations, DLQ with replay, degraded adapters, paused restaurants; actions map one to one to the runbook.
- S3 (3.7): `/evals` list of versions and compare any two (metric deltas, deterministic checks, judge scores by criterion, fairness table with ratios under 0.8 highlighted, cost per hire) plus a read-only conversation replay link.
- S4 (3.8): `/compliance` (DPO role): audit log search, consent records by notice version, erasure requests and status, retention countdowns.
- S5 (3.9): `/simulator`: three panes (candidate phone, manager phone, live timeline), scenario loader D1-D7, clock controls (+1 h, +1 day, next timer), quick replies rendered as buttons.
- S6 (4): the SIMULATION badge remains visible in the header while on mocks; every number has a tooltip with its source endpoint and, for metrics, the formula.
- S7 (4.5): responsive at 390px and 1280px; tokens only, no hard-coded colors, radii, font sizes or shadows.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | Restaurants grid and detail | pending |
| T2 | S2 | Operations queues and actions | pending |
| T3 | S3 | Evals list and comparison | pending |
| T4 | S4 | Compliance view (DPO role) | pending |
| T5 | S5 | Simulator with clock and scenarios | pending |
| T6 | S6,S7 | Tooltips with sources, responsive pass, tests, verify | pending |

## Constraints

- Only `web/**`. No backend changes; when an endpoint is missing, render an honest empty state and report it.
- Vitest + Testing Library + MSW, behaviour first.
- Reuse the existing API client patterns; new endpoints go through `web/src/api/client.ts`.

## Log

- L1 (user, verbatim): "todo en dev. continúa"
- L2: dev at 8e4a20b; the Vite server keeps serving 5173 against the backend on 8001 for smoke checks.
