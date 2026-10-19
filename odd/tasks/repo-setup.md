# Feature: F01 repo-setup

Two-halves repository setup per AGENTS.md sections 4 and 6 and PROMPTS.md F01. No business logic.

## Header

- **Objective:** runnable backend (uv + FastAPI + Postgres + Redis) and console (Vite + React + TS + Tailwind) in Docker, with tests, lint, types and a /health integration on both sides.
- **Status:** closed, awaiting human review before F02
- **Next step:** after human review, PROMPTS.md F02 discovery-stakeholders-and-interviews.

## Specs

- S1: "Backend: uv project, folder layout, docker compose with Postgres and Redis, FastAPI app with a /health endpoint, CORS for the Vite dev server, pytest, ruff and mypy configured."
- S2: "Console: Vite + React + TypeScript (strict) app in web/ with Tailwind CSS, React Router, TanStack Query, Vitest + Testing Library + MSW, ESLint, Prettier, pnpm as the package manager (pnpm-lock.yaml committed, no package-lock.json), and the scripts dev, build, test, lint, typecheck and gen:api (openapi-typescript against the running backend). One page that calls /health and shows the status."
- S3: "A Makefile or task list with the commands from README.md Quick start."
- S4: "TDD: backend runner `uv run pytest`, start with a failing test for /health; console runner `pnpm test`, start with a failing test for the health status component."
- S5: "Do not write any business logic yet. Close with the command outputs of both halves as evidence."
- S6 (user decision, verbatim): "vamos a usar strands agents con python https://strandsagents.com/ para crear los agentes de la app. Y twilio como canal para whatsapp."
- S7 (user decision, verbatim): "OpenAI como API de IA para el agente, Langfuse o Prometheus para obs y evals, que yo creo que langfuse mejor, grafana o sentry para metricas y errores."
- S8 (user decision, verbatim): "Vamos a tenerlo todo en docker como en los demas proyectos."
- S9 (user decision, Q&A): observability = "Grafana + Sentry" (Grafana self-hosted in compose for metrics/logs; Sentry via SDK + DSN, self-hosting Sentry is out of scope for compose, documented). Pydantic confirmed. Default LLM model gpt-4.1-mini, env-configurable. DESIGN.md token values: provisional, marked `/* provisional */`, listed under Open questions.
- S10 (verbatim, DESIGN.md tokens): "Otherwise ask the human once for the values. Only if the human explicitly says to proceed without them, create provisional values, mark every one with a `/* provisional */` comment".

## Constraints

- AGENTS.md section 5 architecture rules hold; Strands Agents is used at the agent layer only, the deterministic core stays plain Python (agents come in F07, not here).
- Do not modify specs/.
- No em dash in any repository file.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | - | Commit baseline specs and agent contract (PROMPTS.md section 0) | done |
| T2 | S6,S7,S8,S9 | Update AGENTS.md and README stack tables to the decided stack | pending |
| T3 | S1,S4 | Backend skeleton: uv project, /health with RED first, CORS, pytest/ruff/mypy | pending |
| T4 | S8 | docker compose full stack: postgres, redis, langfuse, grafana/prometheus, backend, web, worker | done |
| T5 | S2,S4,S10 | Console scaffold with provisional tokens.css and health page, RED first | done |
| T6 | S1,S2 | Install dependencies both halves; run all checks | done |
| T7 | S3 | Makefile + README Quick start (Docker-first) | done |
| T8 | S5 | Close feature with command outputs as evidence | done |

## Open questions

- DESIGN.md token values are provisional (human chose "provisional, marked"): all colors except the two derivable ones ({colors.brand-green} rgb(0 212 164), {colors.brand-tag} rgb(55 114 207)), shadows beyond the documented rgba values, and {colors.primary}/{colors.on-primary} (described as "black" only). Every provisional value carries `/* provisional */` in tokens.css.

## Log

- L1 (user request, verbatim): "Este es un proyecto para una entrevista de Forward Deployed Engineer en una startup. Se dedican a integrar sus agentes de IA en los procesos de las empresas que la contratan. Son agentes de HR (recruiting, onboarding y pulse), entonces tienes todos los md ahi en el proyecto para que los leas y empieces a iterar. Añade tambien que vamos a usar strands agents con python https://strandsagents.com/ para crear los agentes de la app. Y twilio como canal para whatsapp. Tiene su DESIGN.md para hacer lo que es el front para que el humano tenga controlado todo lo que hacen los agentes y al personal (como altas y bajas, horarios, onboardings etc). Sigue todos los pasos, aunque ya se ha iniciado el repo porque esta clonado desde github aunque esta vacio aun y lo que hay esta sin commitear todavia. Tu te encargas de instalar todas las dependecias de ambas partes. Vamos a tenerlo todo en docker como en los demas proyectos. OpenAI como API de IA para el agente, Langfuse o Prometheus para obs y evals, que yo creo que langfuse mejor, grafana o sentry para metricas y errores. Usa glm 5.3 flassh para orquestar y DeepSeek V4-Flash (4.1-1017 version) para implementar y correcciones."
- L1a: Model note: glm 5.3 flash / DeepSeek V4-Flash refer to Pi host model configuration; session proceeds with its configured model.
- L2: Human decisions (Q&A): Grafana + Sentry; Pydantic confirmed; gpt-4.1-mini default (env-configurable); DESIGN.md tokens provisional; one feature per turn with human pause between features (F01 closes and waits for review before F02).
- L3: Evidence (backend): `uv run pytest` 2 passed; `uv run ruff check .` all checks passed; `uv run mypy app` no issues in 10 source files. RED observed for /health (ModuleNotFoundError) and /metrics (assert failure) before implementation.
- L4: Evidence (console): `pnpm test` 2 passed; `pnpm typecheck` OK; `pnpm lint` OK; `pnpm build` OK. RED observed (Failed to resolve import ./HealthStatus) before implementation.
- L5: Evidence (Docker): `docker compose up -d --build` runs 7 services; `docker compose ps` shows backend, postgres, redis healthy; curl: console 200, /health {"status":"ok"} with CORS header for localhost:5173, langfuse 200, grafana 200, prometheus healthy with target firstshift-backend up.
- L6: Docker fixes during verification: pnpm 11 rejects invalid `allowBuilds` placeholder in pnpm-workspace.yaml (set esbuild/msw true); missing .dockerignore let host node_modules corrupt the image (added web/.dockerignore and root .dockerignore); host ports 5432 and 8000 were occupied by other local services, so postgres maps to host 5433 and backend to host 8001.
- L7: Sentry deviation: the user chose Grafana + Sentry. Sentry self-hosting is a separate 20+ container deployment, so F01 ships the sentry-sdk hook wired to SENTRY_DSN (empty disables it) and Grafana + Prometheus fully self-hosted. Sentry SaaS DSN or a separate self-hosted deployment is a later decision. Recorded as an open item for the human.
