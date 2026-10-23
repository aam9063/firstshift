# Feature: console-live

## Header

- **Objective:** the FirstShift Console shows real backend data instead of fixtures, and works on phone and desktop widths. No view imports mock data any more.
- **Status:** in progress
- **Branch:** feature/console-live-data, in its own Orca worktree (`console-live`) so the console session's tree and `backend-infra` are untouched.

## Specs

Source of truth: `specs/04b-console.md` sections 1, 2, 3.1-3.4 and 4.5, `web/DESIGN.md` Responsive Behavior, and the live backend contract already running at `http://localhost:8001`.

- S1: data access stays behind `web/src/api/client.ts`; components never import fixtures. Every function fetches its documented endpoint; errors are typed and surfaced.
- S2: `GET /api/events/stream` replaces the scripted stream: one EventSource, reconnect with `Last-Event-ID`, pause/resume keeps working, and each SSE envelope maps to a `LiveEvent` (agent.turn -> agent_turn, tool.call -> tool_call, state.transition -> state_change, integration.write -> integration, human/audit rows -> human_action).
- S3: `/candidates` stops being a placeholder: a real table from `GET /api/candidates` (state chip, restaurant, cohort, language, last activity, SLA risk) linking to the journey.
- S4: responsive per DESIGN.md: sidebar becomes a drawer below 1024px; tables scroll horizontally instead of overflowing; KPI grid stacks; touch targets 44px on mobile; the page is usable at 390px and 1280px.
- S5: no fixture imports remain in non-test source (grep must return none); fixtures stay for tests only.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | API client against the real endpoints, RED first with MSW | pending |
| T2 | S2 | Real SSE hook replacing the scripted stream | pending |
| T3 | S3 | Candidates list page with real rows | pending |
| T4 | S4 | Responsive fixes at 390px and 1280px | pending |
| T5 | S5 | Verify (tests, lint, typecheck, build, grep for fixtures) and run on 5173 | pending |

## Constraints

- Only `web/**`. No backend changes.
- Tests: Vitest + Testing Library + MSW, behavior first (loading, error, data, reconnect).
- Tokens only: no hard-coded colors, radii, font sizes or shadows.

## Log

- L1 (user, verbatim): "Pero quiero ver datos reales no mockeados, ni que me diga que esta ok el back. Y por favor, hazlo responsive"
- L2: Worktree `console-live` created from dev (74e0d6c); the console session's tree is not modified by this feature.
