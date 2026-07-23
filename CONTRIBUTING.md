# Contributing to ORNA Atlas

## Setup

Copy `.env.example` to `.env`, review every target URL, and start the local stack with `docker compose up --build`. Apply migrations with `docker compose exec api alembic upgrade head`. The seed command is optional and must only target local disposable data.

For host-side checks install Python 3.12 dependencies with `pip install '.[dev]'` and frontend dependencies with `cd web && npm ci`.

Read `AGENTS.md` before editing; it routes architecture context, specialist roles, repository skills, specs and required checks.

## Pull request contract

A change is ready for review when:

- behavior and scope are described;
- critical business rules have regression tests;
- Python tests and Ruff pass;
- `python scripts/run_agent_evals.py --tier fast` passes;
- durable architecture changes include a new indexed ADR;
- frontend typecheck and lint pass for frontend changes;
- migration upgrade and downgrade were checked for schema changes;
- public API and frontend types agree;
- `CURRENT_STATE.md` and domain rules remain accurate;
- no secrets, local media or generated build output are included.

Prefer small commits that keep the application runnable. Avoid broad refactors mixed with behavior changes. Explain intentional follow-up work rather than leaving anonymous TODOs.

## Test layers

- Agent governance: `python scripts/run_agent_evals.py --tier fast`.
- Unit/contract: `python -m pytest`.
- Real dependencies: start PostgreSQL, Redis and MinIO, then run `RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration`.
- Browser smoke: start API and web, then run `cd web && npm run test:e2e`.

Integration tests are skipped unless explicitly enabled so they cannot accidentally connect to infrastructure. Use only local disposable services.

