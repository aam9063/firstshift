# PROMPTS.md: running FirstShift with gentle-shell (Pi) under ODD

Paste these prompts into Pi **one at a time, in order**. Each one authorizes a single ODD feature. Let the agent explore, track it in `odd/tasks/<feature>.md`, implement task by task and close with evidence before you send the next prompt.

Your job between prompts (5 to 15 minutes each): read the feature document, open the outputs, push back where it is weak. That review is the human part of the FDE loop, and it is what you will talk about in the interview.

---

## 0. Before the first prompt

```bash
mkdir firstshift && cd firstshift && git init
# copy README.md, AGENTS.md, PROMPTS.md and specs/ into the repo
git add . && git commit -m "chore: specs and agent contract"
gentle-shell            # or: pi, with gentle-pi installed
/gentle:status
/gentle:doctor
```

Optional but recommended: `/gentle:review-mode enable` so substantial code deliverables get a frozen, risk-scoped review.

---

## F01 · repo-setup

```
Implementation is authorized. Feature name: repo-setup.
Read AGENTS.md fully. Set up both halves exactly as AGENTS.md sections 4 and 6 describe:
- Backend: uv project, folder layout, docker compose with Postgres and Redis, FastAPI app with a /health endpoint, CORS for the Vite dev server, pytest, ruff and mypy configured.
- Console: Vite + React + TypeScript (strict) app in web/ with Tailwind CSS, React Router, TanStack Query, Vitest + Testing Library + MSW, ESLint, Prettier, pnpm as the package manager (pnpm-lock.yaml committed, no package-lock.json), and the scripts dev, build, test, lint, typecheck and gen:api (openapi-typescript against the running backend). One page that calls /health and shows the status.
- A Makefile or task list with the commands from README.md "Quick start".
TDD: backend runner `uv run pytest`, start with a failing test for /health; console runner `pnpm test`, start with a failing test for the health status component.
Do not write any business logic yet. Close with the command outputs of both halves as evidence.
```

## F02 · discovery-stakeholders-and-interviews

```
Implementation is authorized. Feature name: discovery-stakeholders-and-interviews.
Source of truth: specs/00-client-brief.md and specs/01-discovery.md sections 1, 2 and 3. Quote those sections in the feature document and pass the paths to any worker.
Produce discovery/stakeholder-map.md, discovery/interview-guides.md, all transcripts in discovery/transcripts/ and discovery/ride-along-benidorm.md.
Run the interviews as described in section 2: each stakeholder role-played by a separate worker that receives only its brief row plus its private truth; the interviewer never sees private truths. Save transcripts verbatim with line IDs like [T-yolanda-14].
No code. Checks: every stakeholder in the brief has a transcript, every interviewer note has the 3 required bullets.
```

## F03 · discovery-process-systems-funnel

```
Implementation is authorized. Feature name: discovery-process-systems-funnel.
Source of truth: specs/01-discovery.md sections 4, 5, 6 and 7, plus the baseline table in specs/00-client-brief.md section 4.
Produce discovery/as-is-process.md, discovery/systems-and-data.md, the seeded mock dataset in mocks/seed/ with a fixed seed, the re-runnable funnel script `uv run python -m mocks.funnel`, discovery/funnel-baseline.md, discovery/pain-points.md and discovery/insights.md with the 60-second readout at the top.
TDD applies to the funnel script: test that the seeded data reproduces the brief's baseline within a tolerance you state.
Every insight must cite transcript IDs or data files that exist. Validate Mermaid syntax.
```

## F04 · problem-framing

```
Implementation is authorized. Feature name: problem-framing.
Source of truth: specs/02-problem-framing.md (all sections). Inputs: everything in discovery/.
Produce design/problem-statement.md, metric-tree.md, hypotheses.md, constraints.md, non-goals.md, assumptions.md and pilot-charter.md.
The problem statement must use the exact template in section 1. Every number must trace to the brief or to discovery files. If discovery contradicts a hypothesis in the spec, follow the evidence and record why.
No code.
```

## F05 · solution-design

```
Implementation is authorized. Feature name: solution-design.
Source of truth: specs/03-solution-design.md (all sections). Inputs: discovery/ and design/ from previous features.
First write design/options.md with at least 8 genuinely different options and design/decision-matrix.md, and stop to show me the matrix before writing the concept. That is the one product decision I want to make myself.
After my answer: concept.md with sequence diagram, agents.md, state-machine.md (stateDiagram-v2 plus transition table, timers and invariants), architecture.md, data-model.md, integration-contracts.md, guardrails.md and at least 5 ADRs in design/adr/.
Check that every constraint in design/constraints.md maps to a guardrail or invariant, and list the mapping.
```

## F06 · walking-skeleton

```
Implementation is authorized. Feature name: walking-skeleton.
Source of truth: specs/04-prototype.md section 1 (Milestone A), design/state-machine.md, design/data-model.md, design/integration-contracts.md and AGENTS.md section 5.
Build mocks for all client systems behind ports, the HireDesk webhook, the core state machine for the happy path with invariants as tests, the audit log, and the outbox with an idempotent relay worker. Design the typed event model now (state.transition, integration.write, message.in, message.out; agent events come in F07) because the console will stream it. No LLM yet: scripted replies.
TDD enabled, runner `uv run pytest`: observed RED before each implementation step.
Acceptance criteria are the ones in Milestone A. Close with test output and one integration test log showing a candidate reaching first_shift_scheduled.
```

## F07 · agents-and-simulator

```
Implementation is authorized. Feature name: agents-and-simulator.
Source of truth: specs/04-prototype.md sections 2, 3 and 4, design/agents.md and design/guardrails.md.
Add the Recruit, Onboard and Pulse (day-3) agents with versioned prompts in app/prompts/, per-state tool allow-lists and Pydantic validation of every LLM output that feeds the core. Build the simulator backend: simulated channel adapter, controllable clock, scenario loading and the simulator API from specs/04b-console.md section 2. Persist every agent turn, tool call, state transition and integration write as a typed event and stream it on GET /api/events/stream (SSE).
Implement scenarios D1 to D7 as automated scenario tests (LLM calls may be recorded and replayed in tests for determinism). The UI comes in C1.
TDD enabled for code.
```

## C1 · console-shell-live-simulator

```
Implementation is authorized. Feature name: console-shell-live-simulator.
Source of truth: specs/04b-console.md sections 1, 3.2, 3.9, 4 and 5 (steps 1 and 2), web/DESIGN.md, and AGENTS.md sections 5 (rules 7 and 8) and 7b.
First task: resolve the token values as specs/04b-console.md section 4.1 says (ask me once if they are missing), then create web/src/styles/tokens.css and the base components named in web/DESIGN.md that this feature needs (button-primary, button-secondary, card-base, badge-type, sidebar-nav-item, sidebar-section-header, promo-banner, code-block, text-input).
Then build the console shell (layout, header with SIMULATION badge and role picker, routing, generated API client, SSE hook with reconnect and Last-Event-ID), the live agent activity view and the simulator view with three panes, clock controls and scenario loader.
Regenerate API types with pnpm gen:api before writing any data-fetching code.
TDD with Vitest + MSW for the SSE hook, the feed filters and the simulator clock controls. Close with a screenshot or recording of scenario D1 running in /simulator as evidence, plus test output.
Then write docs/demo-script.md for D1 + D4 + D6 using the console (specs/04-prototype.md section 4).
```

## C2 · console-candidate-journey

```
Implementation is authorized. Feature name: console-candidate-journey.
Source of truth: specs/04b-console.md sections 2 (candidate and takeover endpoints), 3.3 and 3.4.
Add the backend endpoints if missing (TDD with pytest), regenerate API types, then build the candidates list and the candidate journey view with timeline, conversation and record columns, and the takeover / release / human message flow with audit events.
Add the Playwright flow "takeover": load D1, open the candidate, take over, send a message, see it in the simulator candidate pane, release.
```

## C3 · console-overview-and-restaurants

```
Implementation is authorized. Feature name: console-overview-and-restaurants.
Source of truth: specs/04b-console.md sections 3.1 and 3.5, and design/metric-tree.md for metric definitions and formulas.
Build the metrics endpoints (pilot vs control vs baseline) and the overview and restaurants views. Every KPI has a tooltip with its source endpoint and formula. Run this after F08 so the numbers come from a real eval or simulation run.
```

## C4 · console-ops-evals-compliance

```
Implementation is authorized. Feature name: console-ops-evals-compliance.
Source of truth: specs/04b-console.md sections 3.6, 3.7 and 3.8, and docs/runbook.md for the operations that /ops must expose.
Build the escalations and operations view (manager SLA queue, DLQ with replay, pause restaurant), the evals comparison view (the eval runner must also write JSON next to each markdown report) and the compliance view (DPO role only).
Add the Playwright flow "DLQ replay". Run this after F12 so the DLQ and fault injection exist.
```

## F08 · eval-harness

```
Implementation is authorized. Feature name: eval-harness.
Source of truth: specs/05-iteration-evals.md sections 1, 2 and 3.
Build the persona generator (40+ personas, seeded), the candidate simulator agent, deterministic checks, the LLM judge with a versioned rubric, the fairness table and the runner command. Calibrate the judge on 15 conversations I will label: generate them, then ask me to label them before computing agreement.
Run the full suite and write evals/reports/eval-v1.md as the baseline.
```

## F09 · iteration-1 (repeat as F10 iteration-2, and so on)

```
Implementation is authorized. Feature name: iteration-1.
Source of truth: specs/05-iteration-evals.md section 4. Input: the latest evals/reports/eval-vN.md.
Follow the protocol exactly: pick the single largest gap, write the hypothesis in docs/iteration-log.md, change one thing, run fast then full suite with the same seed, keep or revert, record the numbers. Produce eval-v(N+1).md.
Deterministic checks must stay at 100%.
```

## F11 · simulated-pilot-and-redteam

```
Implementation is authorized. Feature name: simulated-pilot-and-redteam.
Source of truth: specs/05-iteration-evals.md sections 5 and 6.
Run the 30-day simulated pilot (12 pilot vs 3 control restaurants) and write docs/pilot-sim-day30.md as a real weekly ops review. Run the red-team suite and write evals/reports/redteam-v1.md. Every adversarial case must end in the designed safe behavior; fix what does not, as separate tasks with tests.
```

## F12 · integration-hardening

```
Implementation is authorized. Feature name: integration-hardening.
Source of truth: specs/06-integration-rollout.md sections 1 and 2, design/integration-contracts.md.
Add fault injection to the mocks, harden every adapter for the listed failure modes, add contract tests, DLQ, tracing, health checks and degraded-mode holding messages. Write docs/integration-guide.md with every write per system.
TDD enabled: each failure mode starts as a failing test.
```

## F13 · compliance-rollout-runbook

```
Implementation is authorized. Feature name: compliance-rollout-runbook.
Source of truth: specs/06-integration-rollout.md sections 3, 4, 5 and 6.
Write docs/security-and-compliance.md, docs/rollout-plan.md, docs/training/manager-quickstart.md, docs/runbook.md, and extend the simulation to 90 days for docs/pilot-sim-day90.md.
Keep the simulation caveat visible in every results section.
```

## F14 · handover-and-story

```
Implementation is authorized. Feature name: handover-and-story.
Source of truth: specs/07-handover-and-story.md (all sections).
Write docs/handover.md, docs/case-study.md, docs/demo-video-notes.md and docs/interview-narrative.md, and update README.md with results, "What is stubbed" and links.
For the bridge to my real experience, ask me for the details before writing them; do not invent any. Use only the public facts listed in section 5 about the target company.
```

---

## If you are short on time before Tue 27 Oct

Full order: F01 → F02 → F03 → F04 → F05 → F06 → F07 → C1 → C2 → F08 → C3 → F09 → F10 → F11 → F12 → C4 → F13 → F14.

Minimum credible path: F01 → F02 (lighter: 5 key stakeholders) → F03 → F04 → F05 → F06 → F07 (D1, D4, D6 only) → C1 → C2 → F08 (20 personas) → F09 → F14 (narrative and demo only). C3 is a nice extra if a day is left. F11 to F13 and C4 deepen the project for later technical rounds.

Tip: the console is where you will spend the demo, and it is your strongest stack. If you need to save agent time, build C1 and C2 yourself (or pair closely with the agent) and let the agents run the backend features in parallel.
