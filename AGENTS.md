# AGENTS.md: operating contract for FirstShift

Read this file fully before any work in this repository. It applies to the parent session and to every focused agent (explorer, writer, verifier).

## 1. Mission

Simulate a Forward Deployed Engineering engagement for a fictional quick-service restaurant (QSR) group, **Lumbre Burger Group**, and deliver an AI agent system (FirstShift) that takes a staffing gap all the way to a new crew member working their first shift, integrated into the client's existing systems and routines.

The repository is a portfolio piece for an FDE interview at a company that builds AI agents for frontline HR (recruiting, onboarding, engagement) reached through WhatsApp, SMS and voice. Quality of reasoning and evidence matters as much as code.

## 2. Workflow: Organic Driven Development (ODD)

This project runs on gentle-shell (Pi) with ODD as the default protocol.

- **Specs are the source of truth.** `specs/*.md` are written by the human. When a prompt references a spec, quote the relevant section verbatim in the feature document and pass the path to workers instead of paraphrasing it.
- **One feature document per substantial feature** at `odd/tasks/<feature-name>.md` (objective, problem, why, scope, constraints, checklist with stable IDs and acceptance criteria, verification evidence, progress, next step). Mirror it in Engram when available.
- **Small, understood work stays small.** No task document for a one-file fix.
- **Ask one focused question only for a real unresolved decision.** Otherwise pick the most reasonable option, state it in the feature document and continue.
- **Checkoffs require observed proof**: a test run, a command output, a file that exists, a rendered diagram.
- **Do not modify `specs/`** unless the prompt explicitly authorizes it. If a spec is wrong or contradictory, record it under "Open questions" in the feature document and tell the human.
- SDD is not used in this project unless the human asks for it explicitly.

## 3. TDD and checks

- TDD mode: **enabled** for code under `app/`, `mocks/` and `simulator/` (runner: `uv run pytest`) and for `web/` (runner: `pnpm test` in `web/`, Vitest). Observed RED before implementation, then GREEN, then REFACTOR, recorded as evidence. Pure visual styling changes in `web/` do not need a failing test first; behavior does (data loading, SSE handling, takeover, filters).
- Documentation phases (discovery, framing, design) have no test runner. Their checks are: every required section exists, every claim about the client traces to `specs/00-client-brief.md` or to a simulated interview transcript, and every diagram renders (Mermaid syntax valid).
- Lint and types: `uv run ruff check .` and `uv run mypy app` must pass before closing a backend feature; `pnpm lint` and `pnpm typecheck` in `web/` before closing a frontend feature.
- API contract: after any change to FastAPI routes or schemas, run `pnpm gen:api` in `web/` and commit the regenerated types. A frontend feature cannot close with stale API types.

## 4. Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Matches the target company's agent stack |
| API | FastAPI + Pydantic v2 | Typed contracts, fast to iterate |
| Persistence | PostgreSQL (Docker) via SQLAlchemy 2 + Alembic | Real migrations, real constraints |
| Async jobs | Celery + Redis | Scheduled nudges, retries, outbox relay |
| LLM | OpenAI API through Strands Agents (Python SDK, tool use), model configurable via env (default gpt-4.1-mini) | Conversation and extraction only |
| Messaging | Channel port with two adapters: local simulator (default) and Twilio WhatsApp | Demo without external dependencies |
| Tests | pytest, pytest-asyncio, respx for HTTP mocks | |
| Packaging | uv | |
| Observability | Langfuse (LLM traces, prompts, evals) + Grafana stack (Prometheus, Loki) for metrics and logs + Sentry for error tracking | Every conversation turn and integration call is traceable and every error is captured |
| Console (frontend) | React + TypeScript (strict) on Vite, Tailwind CSS, React Router, TanStack Query and Table, Recharts | HQ oversight, live agent activity and the demo simulator (full spec: `specs/04b-console.md`) |
| Live updates | Server-Sent Events from FastAPI | Agent turns and integration writes appear in the console in real time |
| Frontend tests | Vitest + Testing Library + MSW, Playwright for end-to-end flows | |
| API types | `openapi-typescript` generated from FastAPI's OpenAPI schema | Backend and frontend can never disagree silently |

## 5. Architecture rules (non-negotiable)

1. **Deterministic core, LLM at the edge.** The hiring process is a state machine in plain Python. The LLM never decides state transitions, eligibility or scheduling. It only (a) talks to people in natural language, (b) extracts structured data from free text into Pydantic models, (c) summarizes for humans. Every LLM output that feeds the core is validated against a schema; invalid output triggers a re-ask, never a guess.
2. **Ports and adapters.** Every client system (ATS, HRIS, scheduling, POS forecast, LMS, messaging) is accessed through a port interface in `app/ports/`. Mocks live in `mocks/` and implement the same contract the real adapter would. Swapping a mock for a real adapter is configuration, not code.
3. **Humans own consequential decisions.** The system never rejects a candidate automatically and never sends a job offer without a manager approval. It recommends; a human decides. Every decision is logged with who, what, when and why.
4. **Idempotency everywhere.** Inbound webhooks carry an idempotency key; outbound writes use an outbox table relayed by a worker with retries and backoff.
5. **Privacy by design.** Collect the minimum data. Personal documents are referenced by ID, never logged. Candidate consent is captured before any processing and stored with a timestamp and version of the notice.
6. **No hidden prompts in code paths.** Prompts live in `app/prompts/` as versioned files so eval reports can reference a prompt version.
7. **Everything the agents do is observable.** Every agent turn, tool call, state transition and integration write emits a typed event that is persisted and streamed to the console. If it is not visible in the console, it did not happen.
8. **The console is for HQ oversight, never a step for managers.** Managers act only through WhatsApp. The console reads through the FirstShift API only and never calls client systems or mocks directly.

## 6. Folder layout

```
app/
  core/          # state machine, policies, scoring rules (pure, no I/O)
  agents/        # conversation agents (recruit, onboard, pulse), tool definitions
  prompts/       # versioned prompt files
  ports/         # interfaces to client systems
  adapters/      # real adapters (twilio, etc.)
  api/           # FastAPI routers (webhooks, console API, SSE stream, simulator API)
  workers/       # celery tasks (nudges, outbox relay, forecasts)
  db/            # models, migrations
mocks/           # mock ATS, HRIS, scheduling (WFM), POS forecast, LMS with seed data
simulator/       # simulated messaging channel + clock control (backend only; UI lives in web/)
web/             # FirstShift Console: React + TypeScript + Tailwind on Vite
  src/api/       # generated OpenAPI types + typed client
  src/features/  # overview, live, candidates, journey, restaurants, ops, evals, compliance, simulator
  src/components/
  e2e/           # Playwright flows
evals/           # personas, golden conversations, judges, reports
discovery/       # phase 1 outputs
design/          # phase 2 and 3 outputs
docs/            # runbook, rollout plan, case study
tests/
odd/tasks/       # ODD feature documents
```

## 7. Language and writing rules

- All repository artifacts are in **English** (the reader is an international hiring team). Conversations with simulated candidates and crew are in **Spanish** by default, with Portuguese and English support where the spec says so.
- Do not use the em dash character in any file you write. Use commas, colons, parentheses or new sentences. (`web/DESIGN.md` is a reference file provided by the human: do not edit it.)

## 7b. Frontend rules

- **Package manager: pnpm only.** Never run `npm` or `npx` (use `pnpm dlx`), never commit `package-lock.json` or `yarn.lock`.
- **Design system: `web/DESIGN.md`** is the visual source of truth. Read it and `specs/04b-console.md` section 4 before any UI work. All values go through `web/src/styles/tokens.css`; no hard-coded colors, radii, font sizes or shadows in components.
- Write for a busy reader: lead with the conclusion, then the evidence.
- Never invent facts about real companies. The client and all its systems are fictional. Public facts about the target company may only appear in `specs/07-handover-and-story.md` and must already be present there.

## 8. Git workflow

- `dev` is the integration branch. Every `feature/...` or `fix/...` branch is created from `dev` and merged back into `dev` through a pull request.
- `main` only receives merges from `dev` when the state is demo-ready. Direct pushes to `main` or `dev` are not part of the workflow.
- CI (`.github/workflows/ci.yml`) must be green before merging: backend pytest/ruff/mypy, console vitest/eslint/tsc/build, compose config validation.
- After every `dev` -> `main` merge, main is synced back into `dev` automatically by `.github/workflows/sync-dev.yml`. `main` only ever receives merges from `dev` (it is a subset of `dev`), which is what makes the automated `-X ours` reconciliation safe. Never let `main` and `dev` diverge, and never push a feature branch straight to `main`.
- Secret scanning is owned by GitGuardian (GitHub App). No passwords, API keys or tokens ever live in the repository: configuration arrives through environment variables (`env.example` documents the shape, `.env` is gitignored).

## 9. Definition of done for any feature

- Acceptance criteria in the feature document are checked with evidence.
- Tests green, lint and types clean (code features).
- The relevant spec section is satisfied or the deviation is recorded with a reason.
- `README.md` or the relevant doc updated if behavior or commands changed.
- The feature document's "next step" names the next feature from `PROMPTS.md`.
