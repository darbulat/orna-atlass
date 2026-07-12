# ORNA Atlas agent guide

This file is the operational entry point for developers and coding agents. Read it before changing the repository. The current implementation is documented in `docs/CURRENT_STATE.md`; product intentions that are not implemented must not be treated as runtime facts.

## Repository map

- `orna_atlas/app/main.py`: FastAPI application and health endpoint.
- `orna_atlas/app/modules/`: domain modules. Backend flow is normally `router -> service -> repository -> model`.
- `orna_atlas/app/integrations/`: Redis, S3, sunrise and BirdNET boundaries.
- `orna_atlas/app/workers/`: background processing entry points.
- `orna_atlas/app/migrations/`: Alembic migrations; models alone do not change the database.
- `orna_atlas/app/tests/`: fast unit and contract tests.
- `tests/integration/`: opt-in tests against real PostgreSQL, Redis and S3-compatible storage.
- `web/app/`: Next.js routes.
- `web/components/`: interactive UI and audio player state.
- `web/lib/api/`: frontend copies of API contracts. Keep them synchronized with OpenAPI until generation is introduced.
- `web/e2e/`: Playwright browser smoke tests.
- `docs/DOMAIN_RULES.md`: domain invariants and public-data rules.
- `docs/adr/`: accepted architecture decisions.

## Required checks

Run the narrowest relevant test first, then the complete local checks:

```bash
python -m pytest
python -m ruff check .
cd web && npm run typecheck && npm run lint
```

With the compose dependencies running, execute integration tests explicitly:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
cd web && npm run test:e2e
```

## Safety rules

- Never use a production database, bucket or Redis instance in tests or seed commands.
- Never commit `.env`, credentials, generated audio, database dumps, `.next`, `node_modules` or model caches.
- Do not expose exact coordinates through public DTOs. Apply the rules in `docs/DOMAIN_RULES.md` to every new public flow.
- Do not issue playback grants for missing or unready renditions.
- Do not invent successful fallback data after infrastructure failure.
- Do not add `commit()` to repositories. A service owns a transaction and commits once after all state changes succeed.
- Every schema change requires an Alembic migration and upgrade/downgrade verification.
- Seed scripts are local-only and may mutate data. Inspect their target connection before running them.
- Preserve unrelated worktree changes. Do not rewrite or delete user files.

## Change workflow

1. Identify the public/business invariant affected by the change.
2. Add or update a regression test that demonstrates the desired behavior.
3. Change the smallest responsible layer; avoid bypassing services from routers.
4. Update OpenAPI-facing schemas and the corresponding frontend type when a contract changes.
5. Update `docs/CURRENT_STATE.md` if a capability moves between implemented, limited and planned.
6. Record a new ADR only for a durable cross-module decision, not for routine implementation detail.

