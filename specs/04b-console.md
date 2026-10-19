# 04b · FirstShift Console: see everything the agents do

**Goal:** a web app (React + TypeScript + Tailwind CSS on Vite) where the client's HQ team, the DPO and the demo audience can see every candidate journey, every agent turn and tool call, every integration write and every metric, live, and where a human can step in at any point.

**Who it is for (and who it is not for):**
- **Talent team (HQ):** supervise conversations, handle escalations, take over a conversation, watch the funnel.
- **DPO / compliance:** audit log, consents, erasure requests.
- **Ops leadership:** pilot vs control metrics.
- **The demo audience:** the simulator lives here.
- **Not restaurant managers.** The Phase 2 constraint stands: managers act only through WhatsApp. The console never becomes a step a manager has to take. State this in the console's README section and in `design/adr/` (one ADR: "Console for HQ and oversight only").

The console is also the visible proof of two FDE principles: **human oversight** (any human can see, pause and take over) and **auditability** (every decision traceable to who, what, when and why).

---

## 1. Stack and conventions

| Concern | Choice |
|---|---|
| App | React + TypeScript (strict) on Vite, in `web/` |
| Styling | Tailwind CSS via its Vite plugin; every token from `web/DESIGN.md` mapped once into `web/src/styles/tokens.css` (Tailwind `@theme`); light theme only (see section 4) |
| Fonts | Inter (UI) and Geist Mono (IDs, keys, JSON, prompt versions), self-hosted via Fontsource packages installed with pnpm |
| Routing | React Router |
| Server state | TanStack Query (caching, polling fallback, optimistic updates for human actions) |
| Live updates | Server-Sent Events from `GET /api/events/stream` (one stream, typed events), reconnect with `Last-Event-ID` |
| API types | Generated from FastAPI's OpenAPI schema with `openapi-typescript` (`pnpm gen:api`); no hand-written API types |
| Tables | TanStack Table |
| Charts | Recharts (funnel, time series, comparisons) |
| Diagrams | State machine rendered from the same transition table the backend exposes (`GET /api/meta/state-machine`), so it can never drift |
| Tests | Vitest + Testing Library for components; MSW for API mocking; Playwright for 3 end-to-end flows |
| Lint and format | ESLint + Prettier, `tsc --noEmit` in CI |
| Package manager | pnpm (never npm or yarn; commit `pnpm-lock.yaml`) |

Rules:
1. The console talks **only** to the FirstShift API. It never calls mocks or client systems directly.
2. Every number shown has a tooltip saying where it comes from (endpoint and, for metrics, the formula).
3. Simulated data is always labeled: a persistent "SIMULATION" badge in the header while running on mocks.
4. Personal data is minimized in the UI: candidate phone numbers masked by default, documents shown only as status (received, validated, missing), never the file.
5. No em dash characters in UI copy.

## 2. Backend support (FastAPI, in `app/api/console/`)

| Endpoint | Purpose |
|---|---|
| `GET /api/candidates` | Paginated, filterable list (state, restaurant, agent, SLA risk, language, pilot/control) |
| `GET /api/candidates/{id}` | Full journey: profile (minimized), state history, conversation, agent turns, tool calls, decisions, documents and training status, audit events |
| `GET /api/restaurants` and `/{id}/shifts` | Open shifts, coverage, bench size, manager SLA stats |
| `GET /api/metrics/funnel` and `/api/metrics/kpis` | Metric tree from `design/metric-tree.md`, pilot vs control vs baseline, date range |
| `GET /api/escalations` | Pending manager decisions, SLA breaches, escalated conversations, DLQ items |
| `GET /api/audit` | Searchable audit log |
| `GET /api/evals` and `/{version}` | Eval report data as JSON (the runner writes JSON next to the markdown report) |
| `GET /api/events/stream` | SSE: `agent.turn`, `tool.call`, `state.transition`, `integration.write`, `outbox.retry`, `escalation.created`, `message.in`, `message.out` |
| `POST /api/candidates/{id}/takeover` | A human takes over the conversation; agent pauses for this candidate |
| `POST /api/candidates/{id}/release` | Hand the conversation back to the agent |
| `POST /api/candidates/{id}/messages` | Human sends a message while in takeover |
| `POST /api/restaurants/{id}/pause` | Pause all agents for one restaurant (runbook operation) |
| `POST /api/outbox/{id}/replay` | Replay a dead-lettered write |
| `POST /api/erasure-requests` | Start a GDPR erasure |
| Simulator: `POST /api/sim/scenarios/{id}/load`, `POST /api/sim/clock/advance`, `POST /api/sim/messages` | Load scenario, fast-forward the clock, send messages as candidate or manager |

Every human action is an audited event with the acting user (in the prototype, a role picker in the header simulates the logged-in user: Talent, DPO, Ops; real auth with SSO and RBAC is a Phase 6 item).

## 3. Views

### 3.1 Overview (`/`)
- KPI cards: time to first productive shift, time to first contact, interview show rate, offer-to-rota days, day-1 show rate, manager minutes per hire. Each shows pilot value, control value, baseline and target, with a sparkline.
- Funnel chart by stage (Phase 1 stages), pilot vs control.
- "Needs attention" strip: escalations, SLA breaches, DLQ count, guardrail alerts.

### 3.2 Live agent activity (`/live`)
- Streaming feed of SSE events, newest first, filterable by agent (Recruit, Onboard, Pulse), event type, restaurant.
- Each `agent.turn` row expands to show: prompt version, model, input summary, tools called with arguments and results, schema validation outcome, latency, tokens, cost.
- Each `integration.write` row shows target system, operation, idempotency key, status and retries.
- Pause/resume the feed; click any row to jump to the candidate journey.

### 3.3 Candidates (`/candidates`)
- Table with state chips, restaurant, matched shift, language, last activity, SLA risk, current agent, "human in control" flag.
- Saved filters: "waiting for manager", "first shift in next 48 h unconfirmed", "escalated", "benched".

### 3.4 Candidate journey (`/candidates/:id`): the centerpiece
Three columns on desktop, stacked tabs on mobile:
1. **Journey timeline:** state transitions with actor (candidate, manager, system, timer, human user), timestamps and elapsed time between steps; the current state highlighted on a mini state diagram.
2. **Conversation:** WhatsApp-style transcript with the candidate and, in a separate thread, the manager messages about this candidate. Agent messages are tagged with the agent and prompt version. Inline markers where tools were called. **Take over** button opens a composer; while in takeover, a banner shows who is in control.
3. **Record:** matched shift, screening answers (as summarized for the manager), consent record (notice version, timestamp), documents status, training status, decisions with who and why, integration writes for this candidate, bench status.

### 3.5 Restaurants (`/restaurants` and `/restaurants/:id`)
- Grid of the 15 restaurants (pilot and control) with coverage gaps for the next 14 days, bench size, open candidates, manager decision median time.
- Detail: open shifts calendar with which candidate is matched to which shift, and the restaurant bench.

### 3.6 Escalations and operations (`/ops`)
- Queues: manager decisions pending (with SLA countdown), escalated conversations, DLQ with replay, degraded adapters, paused restaurants.
- Actions here map one to one to the runbook in Phase 6.

### 3.7 Evals (`/evals`)
- List of eval versions; compare any two: metrics deltas, deterministic checks, judge scores by criterion, fairness table (ratios below 0.8 highlighted), cost per hire.
- Link from each "worst conversation" to a read-only replay of that conversation.

### 3.8 Compliance (`/compliance`)
- Audit log search, consent records by notice version, erasure requests and their status, data retention countdowns. Only visible with the DPO role.

### 3.9 Simulator (`/simulator`)
- Three panes: candidate phone, manager phone, live timeline (same events as `/live`, scoped to the scenario).
- Scenario loader (D1 to D7 from `04-prototype.md`), clock controls (+1 h, +1 day, jump to next timer), speed toggle for recordings.
- Quick-reply buttons render as real buttons in the manager phone, exactly as they would in WhatsApp.

## 4. Design direction

**The design system is `web/DESIGN.md`.** It is the visual source of truth for every component in `web/`. Reference its component names and tokens directly (`button-primary`, `card-base`, `{colors.ink}`, `{rounded.full}`), never paraphrase them, and never hard-code a color, radius, font size or shadow in a component: everything goes through `web/src/styles/tokens.css`. Do not edit `web/DESIGN.md` (it is a reference file and is exempt from the repository's no-em-dash rule).

### 4.1 Token values (blocking check before C1 styling)

`web/DESIGN.md` names its tokens but does not include their values (no front-matter token block). Before writing `tokens.css`:
1. If the human has provided a version of `DESIGN.md` with token values, use those exactly.
2. Otherwise **ask the human once** for the values. Only if the human explicitly says to proceed without them, create provisional values, mark every one with a `/* provisional */` comment, and list them under "Open questions" in the feature document. Two values can be derived from the file itself and are not provisional: `{colors.brand-green}` is `rgb(0 212 164)` (from the featured-tier glow) and `{colors.brand-tag}` is `rgb(55 114 207)` (from `badge-tag`).

### 4.2 Adapting a marketing-and-docs system to an operations console

`DESIGN.md` describes a marketing site plus documentation surfaces. The console uses **only the documentation side** of it:

| DESIGN.md says | Console applies it as |
|---|---|
| 3-column documentation layout (sidebar ~240px / prose / TOC ~200px) | App shell: left sidebar nav with `sidebar-section-header` and `sidebar-nav-item`, center content, right rail for context (candidate record in the journey view, filters in the live feed) |
| Documentation density: `{typography.body-sm}` 14px, 1.50 line height | Tables, feed rows, transcripts. Page titles use `{typography.heading-3}`; never use `hero-display`, `display-lg` or `heading-1` |
| Hero bands with atmospheric gradients | **Not used.** The console has no marketing surfaces |
| Geist Mono for code and type signatures | IDs, idempotency keys, prompt versions, tool arguments and results (in `code-block`), timestamps in the feed |
| `badge-type`, `badge-tag`, `badge-required` | State chips, agent tags, "REQUIRED" or "SLA BREACH" labels |
| `button-primary` black pill | Primary action per view (Take over, Replay, Load scenario) |
| `button-accent-green` | At most one per viewport, for the single most important positive action (Release to agent, Approve in simulator) |
| `segmented-tab` | Tabs inside the candidate journey on mobile and inside the evals comparison |
| `promo-banner` | The persistent SIMULATION banner above the header |
| `card-base`, `{rounded.lg}`, flat elevation level 0 | KPI cards, restaurant tiles. No heavy shadows; elevation level 2 only for popovers |
| `text-input-focused` mint border | Focus state for every input, including the takeover composer |
| Inline `code-inline` | Field names in record panels, endpoint names in KPI tooltips |

### 4.3 Actor colors (agent, human, system) inside the allowed palette

`DESIGN.md` forbids accents beyond mint, tag blue, error red and testimonial orange. The console's actor coding stays inside that palette:
- **Agent** events and messages: `{colors.brand-tag}` (blue).
- **Human** actions (takeover, manager decisions, Talent actions): `{colors.testimonial-orange}`.
- **System** events (timers, integrations, outbox): `{colors.steel}` (neutral).
- **Success and active states:** `{colors.brand-green}` and `{colors.brand-green-soft}` backgrounds, sparingly.
- **Warnings and errors:** `{colors.brand-warn}` and `{colors.brand-error}`.

Every colored chip also carries a text label or icon: color never carries meaning alone.

### 4.4 Filling the gaps DESIGN.md declares

- **Dark mode:** not defined by the design system, so the console ships light only. Do not invent a dark palette.
- **Hover:** DESIGN.md documents no hover states. For interactive rows and nav items, use `{colors.surface}` as the hover background with a 150 ms ease transition (the file's own recommendation).
- **Success states in forms:** brand-green border plus a `badge-discount`-style success chip.
- **Syntax highlighting for tool JSON:** keep it minimal on `{colors.surface-code}`: keys in `{colors.on-dark}`, strings in `{colors.brand-annotate}`, numbers in `{colors.brand-tag}`, warnings in `{colors.brand-warn}`.
- **Touch targets and breakpoints:** follow the "Responsive Behavior" section of DESIGN.md (sidebar becomes a drawer below 1024px, 44px targets on mobile).

### 4.5 Other rules

Dense but calm, readable at a glance during a screen share. State chips share colors with the state diagram. Keyboard shortcuts for the demo: `g l` live, `g s` simulator, `t` take over. The product name in the UI is FirstShift; never show the name or logo of the brand that inspired the design system.

If the design linter mentioned in DESIGN.md is available, run it with `pnpm dlx` (never `npx`).

## 5. Build order

1. **Shell:** Vite app, Tailwind, routing, layout with header (SIMULATION badge, role picker), API client generated from OpenAPI, SSE hook with reconnect.
2. **Simulator + Live feed** (needed for the demo first).
3. **Candidate journey** with takeover.
4. **Overview** with KPIs and funnel.
5. **Candidates list, Escalations/ops, Restaurants.**
6. **Evals and Compliance** (Phase 5 and 6, can land after the 27th).

## Exit criteria

- [ ] `pnpm dev` with the API running shows live events during a simulator scenario with under 1 s delay.
- [ ] Demo scenarios D1, D4 and D6 can be presented entirely from `/simulator` and `/candidates/:id`.
- [ ] Takeover works end to end: agent pauses, human message reaches the candidate pane, audit event recorded with role.
- [ ] Every KPI tooltip shows its source and formula.
- [ ] API types generated, `tsc --noEmit`, ESLint and Vitest green; 3 Playwright flows green (happy path, takeover, DLQ replay).
- [ ] Works at 1280 px for screen sharing and is usable at 390 px.
- [ ] No hard-coded colors, radii, font sizes or shadows in components (grep for hex values and arbitrary Tailwind values outside `tokens.css` returns nothing); every component maps to a named component or token in `web/DESIGN.md`.
- [ ] `pnpm-lock.yaml` committed; no `package-lock.json` or `yarn.lock` in the repo.
