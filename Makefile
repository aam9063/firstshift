# FirstShift developer commands.
# Full quick start lives in README.md; this file mirrors it.

.PHONY: up down logs backend-test backend-lint backend-types console-install console-test console-lint console-typecheck console-build

## Start the full stack in Docker (both halves plus Langfuse, Grafana, Prometheus)
up:
	docker compose up -d --build

## Stop the stack
down:
	docker compose down

## Follow stack logs
logs:
	docker compose logs -f

## Backend checks
backend-test:
	uv run pytest

backend-lint:
	uv run ruff check .

backend-types:
	uv run mypy app

## Console checks (run from web/ or use these targets)
console-install:
	cd web && pnpm install

console-test:
	cd web && pnpm test

console-lint:
	cd web && pnpm lint

console-typecheck:
	cd web && pnpm typecheck

console-build:
	cd web && pnpm build
