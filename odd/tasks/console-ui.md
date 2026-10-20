# F05: Console UI from mockups (frontend, mocked data)

Build the three FirstShift Console views shown in `web/public/img` as a React + TypeScript frontend with mocked data, while the backend is built in parallel in another session. When the backend becomes operational, the mock layer gets swapped for the real API client.

## Problem

The console (`specs/04b-console.md`) has only a scaffold: one health page. The three mockup images define the target UI for the demo, but they are too large to read directly in an agent session (1440px wide, up to 2019px tall), which blocked a previous session. Readable downscaled copies live at `C:/Users/alber/AppData/Local/Temp/ui-mockups/` (Overview, Live agent activity, Candidate journey).

## Why

The demo audience and the HQ talent team need the visible proof of oversight and auditability. This session owns UI only; backend contracts land in parallel, so the UI must mock at the API boundary, not inside components.

## Scope

- App shell: SIMULATION banner, header with search and role picker ("Viewing as Talent team"), sidebar nav with agents panel, routes.
- Overview (`/`): KPI cards with baseline/target and sparkline, hiring funnel (pilot vs control), Needs attention panel, recent activity feed, shift coverage table (14 days).
- Live agent activity (`/live`): event feed with type filters and pause, expandable rows (prompt, model, state, tokens, validation, trace, tool call arguments and result), health panel, guardrails panel.
- Candidate journey (`/candidates/:id`): journey timeline, candidate and manager threads with tool call chips, matched shift and record rail, take over control (UI state only).
- Mock data layer at the API boundary: typed fixtures plus a mock event stream, shaped so swapping in the real API client and SSE later is configuration, not rewrite.

## Constraints

- Specs 00 and 04b govern. `web/DESIGN.md` is the visual source of truth; every value goes through `web/src/styles/tokens.css` (provisional values approved 2026-10-19 per spec 4.1).
- pnpm only. No em dash in any file. UI copy in English (repo rule); conversation content inside mock transcripts may be Spanish per repo language rules.
- The console never calls client systems or mocks directly: the mock layer impersonates the FirstShift API contract.
- TDD for behavior (data loading, filters, expand, takeover toggle) with Vitest + Testing Library; pure styling exempt.
- Actor colors per spec 4.3: agent blue, human orange, system steel.

## Specs

- S1: "En web/public/img tienes 3 imagenes de ejemplo de como querria la UI, para integrar el backend con los agentes de IA."
- S2: "Esta sesion es para UI, el backend lo tengo en otra terminal. Vais a trabajar en paralelo. Tu mockea y segun vaya estando back operativo lo integraremos"
- S3: specs/04b-console.md sections 3.1, 3.2, 3.4 (view content) and section 4 (design direction) apply; sections for views outside the three mockups are out of scope for this feature.
- S4: web/DESIGN.md component and token names are referenced verbatim in component code intent; no hard-coded colors, radii, font sizes or shadows in components.

## Tasks

- T1 (S2): Mock data layer: typed fixtures for overview metrics, funnel, activity, attention items, coverage, live events, candidate journey; mock SSE generator. Route: writer. Commit: feat(console): mock data layer for the console views.
- T2 (S1, S3): App shell: banner, header, sidebar, routing, placeholder routes for nav items not in scope. Commit: feat(console): app shell with navigation and simulation banner.
- T3 (S1, S3): Overview view. Commit: feat(console): overview view with KPIs, funnel and coverage.
- T4 (S1, S3): Live agent activity view. Commit: feat(console): live agent activity feed with filters and event detail.
- T5 (S1, S3): Candidate journey view with takeover UI. Commit: feat(console): candidate journey view with threads and takeover.
- T6 (S4): Checks green: vitest, eslint, tsc, build; README section; token grep clean. Commit: chore(console): verification evidence and docs.

## Log

- L1 (2026-10-20, verbatim): "Vale, ayer tuve que cerrar una sesion porque me daba error y estaba con la parte de la UI. En web/public/img tienes 3 imagenes de ejemplo de como querria la UI, para integrar el backend con los agentes de IA. Me decia que eran muy grandes las imagenes y no podia leerlas bien. Revisa los commits y miralo que creo que hay algo por ahi que solo pudo leer una imagen"
- L2 (2026-10-20, verbatim): "Esta sesion es para UI, el backend lo tengo en otra terminal. Vais a trabajar en paralelo. Tu mockea y segun vaya estando back operativo lo integraremos"
- L3 (2026-10-20): Decision recorded: UI session works with mocked data at the API boundary; integration with the real backend happens later in this session.

## Progress

- Feature opened 2026-10-20. Branch feature/console-ui created from dev.

## Next step

T1 mock data layer.
