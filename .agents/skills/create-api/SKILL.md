---
name: create-api
description: "Create or extend ORNA Atlas FastAPI endpoints and API contracts. Use for router, Pydantic schema, service, repository, authorization, error-mapping, OpenAPI, or frontend-client changes caused by a backend endpoint."
---

# Create an ORNA API

## Establish the contract

1. Read `AGENTS.md`, `docs/CURRENT_STATE.md`, and the affected rules in `docs/DOMAIN_RULES.md`.
2. Inspect the nearest router -> service -> repository -> model flow, its tests, and its web API consumer before editing.
3. State the public or business invariant, caller classes, response projection, error states, and transaction boundary.
4. Add a focused regression test that fails for the missing behavior.

## Implement the smallest flow

- Keep HTTP parsing, dependencies, and domain-error mapping in the router.
- Keep authorization, orchestration, and every transaction in the service. Commit once per atomic
  database phase; add durable phases only for explicit, tested side-effect ordering and recovery.
- Keep repositories limited to queries and `flush()`; never add `commit()` there.
- Reuse shared domain enums and transport-independent service errors.
- Construct public DTOs as explicit allowlists; never serialize ORM rows or arbitrary metadata directly.
- Omit exact coordinates from public contracts. Exclude hidden locations through every nested session, collection, search, and atlas path.
- Treat publication, caller access, and rendition readiness as separate checks.
- Issue playback grants only for an active, ready, verified rendition. Require an active entitlement for `members_only` content and audit only successful grants.
- Return truthful typed failures for unavailable dependencies or media; never invent fallback data or playable silence.

## Synchronize durable contracts

- Add an Alembic revision for every schema change and verify both upgrade and downgrade.
- Regenerate `web/openapi.json` and `web/lib/api/generated.ts` with `cd web && npm run api:generate` after an OpenAPI change.
- Update typed web client behavior without hand-copying generated schema shapes.
- Update `docs/CURRENT_STATE.md` only when the implemented capability or limitation changes.
- Record an ADR only for a durable cross-module decision.

## Verify

1. Run the narrowest affected pytest module first.
2. Run `python -m pytest` and `python -m ruff check .`.
3. Run `cd web && npm run typecheck && npm run lint` when contracts or clients change.
4. Run opt-in dependency or browser tests when the behavior crosses PostgreSQL, Redis, S3, or the UI.
5. Inspect the final diff for leaked coordinates, object keys, tokens, timestamps, and unrelated edits.
