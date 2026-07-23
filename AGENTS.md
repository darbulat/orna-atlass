# ORNA Atlas operational contract

Read this file before changing the repository. It is the concise entry point for developers and
coding agents; follow links only when they are relevant to the task.

## Truth and context order

Use evidence in this order:

1. Code, Alembic migrations, generated OpenAPI contracts and executable tests establish current
   runtime behavior.
2. `docs/CURRENT_STATE.md` summarizes behavior that has been verified.
3. `docs/DOMAIN_RULES.md` and accepted records in `docs/adr/` define invariants and durable
   decisions. A mismatch with code is a bug or an explicit decision gap, not permission to weaken
   the rule silently.
4. `docs/ARCHITECTURE.md` is the one canonical target architecture. Files under
   `docs/architecture/` only index or explain it; they must not replace or duplicate it.
5. An accepted task spec in `specs/` describes change-level intent. Plans, reviews and chat
   transcripts are supporting context, never proof of implementation.

Do not present target behavior as current behavior. When sources disagree, cite the discrepancy in
the handoff and resolve it in the smallest authoritative source that owns the fact.

## Context-first workflow

1. Inspect `git status` and preserve all unrelated changes and untracked user files.
2. Read the relevant route in `docs/architecture/README.md`, then the applicable role contract in
   `.agents/roles/README.md`.
3. Load only the relevant current-state section, domain rules, ADRs and accepted spec.
4. Verify the claim in the responsible code, migration, API contract and existing tests.
5. State the affected invariant and acceptance behavior before editing. Add a regression test first
   when behavior changes.
6. Change the smallest responsible layer, run the narrowest test, then the required suite.
7. Reconcile docs and finish with the PR handoff described below.

## Architecture boundaries

- Backend domain flow is `router -> service -> repository -> model`. Routers translate HTTP;
  services own use cases and transactions; repositories query/flush but never `commit()`.
- `integrations/` contains external-system boundaries. Workers use explicit application/domain
  operations and must preserve idempotency, leases and retry semantics.
- Admin routes do not bypass domain services.
- `web/app/` composes routes, `web/components/` owns interactive UI, and `web/lib/api/` owns API
  access. Keep OpenAPI-generated types and wrappers synchronized with backend schemas.
- Public DTOs are explicit allowlists. Never serialize ORM objects or private worker/storage
  metadata into public responses.
- Models do not change a database by themselves: every schema change requires an Alembic revision.

See `docs/architecture/BOUNDARIES.md` for ownership and dependency details.

## Non-negotiable invariants

- Exact sensitive coordinates never cross a public boundary; hidden places stay undiscoverable
  through nested sessions, collections, search or atlas responses.
- Playback is fail-closed. A grant requires caller access plus a ready, verified rendition; an
  outage or missing object never becomes invented success data.
- A service owns every transaction; repositories never commit. Each atomic database phase commits
  once after its state changes succeed. Multiple durable phases are allowed only when external-side-
  effect ordering, retry/idempotency and failure recovery are explicit and tested. Cache
  invalidation follows the relevant commit.
- Processing and repeated writes are idempotent. Obsolete attempts cannot activate output, and
  failed retries preserve the last successful asset or analysis.
- Object keys are immutable per revision/attempt. Cleanup deletes only recorded inventories; broad
  prefix deletion is forbidden.
- Timestamps are timezone-aware. Invalid IANA zones and polar day/night are explicit states, not
  silent UTC or dawn fallbacks.
- Authentication, membership and role behavior follows `docs/DOMAIN_RULES.md`; free accounts do
  not imply membership entitlement.

## Forbidden actions

- Never use production PostgreSQL, Redis or buckets in tests, seeds or migration checks.
- Never commit `.env`, credentials, private keys, database dumps, generated audio, user media,
  `.next`, `node_modules` or model caches.
- Never run a seed or destructive cleanup before inspecting its exact target and ownership scope.
- Never invent fallback domain data after infrastructure failure or relax privacy/access behavior
  to make a test pass.
- Never rewrite accepted ADR rationale; add a superseding ADR. Never duplicate or move
  `docs/ARCHITECTURE.md`.
- Never delete or rewrite unrelated worktree files, including untracked images.

## Tests and migrations

Run the narrowest relevant test first, then the complete local checks:

```bash
python -m pytest
python -m ruff check .
cd web && npm run typecheck && npm run lint
```

When the change affects generated contracts, frontend behavior or builds, also run the applicable
`npm run api:check`, `npm run test:unit`, `npm run build` and `npm run test:e2e` commands.

With disposable Compose dependencies running, execute integration checks explicitly:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
cd web && npm run test:e2e
```

For every schema change, add an Alembic migration, run `alembic upgrade head` and `alembic check`,
and verify upgrade/downgrade with the repository migration-cycle command. Inspect the configured
database before any migration or seed command.

## Documentation, decisions and specs

- Update `docs/CURRENT_STATE.md` only when tests prove a capability or limitation changed.
- Update `docs/DOMAIN_RULES.md` when a business invariant changes, with code and regression coverage
  in the same change.
- Add an ADR only for a durable cross-module decision; routine implementation belongs in code and
  the PR. Update `docs/adr/README.md` when adding or superseding a record.
- Use `specs/TEMPLATE.md` for ambiguous, cross-layer, security-sensitive or migration-heavy work.
  A spec is acceptance context, not evidence that its behavior exists.
- Keep documentation links relative and route new context through the indexes instead of growing
  this file into a handbook.

## Specialist routing

Role contracts live in `.agents/roles/` and set review boundaries; use more than one for cross-cutting
work.

| Work | Primary role | Useful repository skill |
| --- | --- | --- |
| Cross-module design, boundaries, ADRs | `architect` | `refactor-module` |
| FastAPI, services, repositories, workers, migrations | `backend` | `create-api`, `optimize-query` |
| Next.js, typed API wrappers, player and accessibility | `frontend` | `create-component` |
| Regression, integration and browser coverage | `test` | `write-tests` |
| Auth, privacy, grants, storage and abuse boundaries | `security` | `review-change` |
| Current-state, architecture, ADR and spec accuracy | `documentation` | `review-change` |

Skills accelerate a bounded workflow; they do not override this contract, domain rules, accepted
ADRs or task scope. See `.agents/roles/README.md` and `.agents/skills/`.

## PR handoff

Every handoff must state:

- the user-visible outcome and files/layers changed;
- the invariant and acceptance scenarios covered;
- tests/checks run, with pass/fail/skip status;
- migration, OpenAPI/frontend-contract and documentation impact;
- security/privacy considerations and remaining risks or follow-ups;
- unrelated worktree changes that were intentionally preserved.

Do not claim completion when required checks were not run; explain the blocker or reason for each
skip.
