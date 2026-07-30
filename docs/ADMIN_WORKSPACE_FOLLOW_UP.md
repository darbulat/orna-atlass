# Admin Workspace v1 follow-up

Status: paused on 2026-07-30. The current implementation is intentionally merged as an incomplete internal capability; do not treat Admin Workspace v1 as release-complete until every gate below is closed.

Source of truth: [`../specs/admin-workspace-v1.md`](../specs/admin-workspace-v1.md).

## Implemented baseline

- Backend admin list/detail and mutation routes for locations, sessions, collections, users/memberships, media processing and audit.
- Server-side bounded filters and pagination.
- Strong aggregate ETags, required `If-Match`, `412` and `428` behavior.
- Row/advisory locking, including last-admin serialization and user+membership aggregate revision.
- Account-management feature gate, structured audit writes and `Cache-Control: no-store`.
- Dynamic SSR `/admin`, fail-closed privileged DTO parsers, transient email/operational searches, and generic notices.
- Client admin-session revalidation on focus, visibility changes and a bounded timer.
- Explicit target-email confirmation for account mutations.
- Typed OpenAPI admin error responses and domain enum filters.

## Required follow-up before release

### Backend and audit contracts

- Add executable audit acceptance coverage for every required mutation event:
  - `location.created`, `location.updated`, `location.archived`;
  - `session.created`, `session.updated`, `session.archived`;
  - `collection.created`, `collection.updated`;
  - `media.segments_registered` and processing retry/archive events;
  - `user.role_updated` and `membership.updated`.
- Assert exact `event_type`, `subject_type`, `subject_id`, actor provenance and bounded structured metadata.
- Add a failure-atomicity canary proving an audit insert failure prevents the domain transaction from committing.
- Retain the collection link-only concurrency canary: after a successful ordered-link PATCH, reuse of the old ETag must fail with `412` before save/audit.
- Run the disposable PostgreSQL integration suite for row/advisory-lock behavior.

### Frontend privacy and authorization

- Add browser coverage proving revoked admin access clears privileged content on focus/visibility revalidation.
- Add browser coverage for explicit target-email confirmation and verify a mismatched confirmation sends no mutation request.
- Add browser coverage for transient sensitive filters and verify IDs, email, IP and User-Agent never enter URL/history/notices.
- Verify strict DTO parsers fail closed for every privileged resource when any required field, nested object, enum, UUID, timestamp or revision is malformed.
- Continue decomposing orchestration from `web/app/admin/page.tsx` into bounded `web/components/admin/**` components.

### Concurrency, paging and request behavior

- Exercise a real stale-write sequence: GET revision, successful mutation, second mutation with the old ETag, typed `412` response, no replay.
- Cover load-more/cursor behavior with multiple pages, stable ordering and no duplicate rows.
- Add network request counters for no-replay/idempotency acceptance scenarios.

### OpenAPI and generated contracts

- Regenerate `web/openapi.json` and `web/lib/api/generated.ts` after every backend contract change.
- Verify two consecutive generations are byte-identical.
- Keep a mechanical matrix test over every admin operation for auth security, `401`/`403`, endpoint-specific success statuses, typed `412`/`428`, enum filters and pagination bounds.

### Production-like smoke and release blocker

- Parameterize the read-only smoke script with API base URL plus admin/member credentials without placing credentials in source, arguments, URLs or logs.
- Smoke anonymous denial, member denial, authenticated admin read, response shape and `Cache-Control: no-store`.
- Fix nginx/gateway routing before release. Last verified state was:
  - local `127.0.0.1:3000/admin`: `200`, `Cache-Control: no-store`;
  - HTTP gateway `/admin`: HTTPS redirect;
  - HTTPS gateway `/admin`: `404` — release blocker.

## Required completion gates

Run against one frozen exact candidate:

```bash
python -m ruff check .
python -m pytest
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
cd web
npm run api:generate
npm run api:generate  # outputs must remain byte-identical
npm run test:unit
npm run typecheck
npm run lint
npm run build
npm run test:e2e
bash scripts/check-admin-route-smoke.sh
```

Then perform a bounded independent review of the exact commit/digest, close all reproducible auth/privacy/integrity/lifecycle findings, obtain green exact-head CI, deploy that approved SHA and repeat production smoke.

## Verification snapshot before pause

Earlier pre-review candidates passed backend `419` tests, frontend `28` unit tests, one PostgreSQL concurrency integration test, admin-specific Playwright `10` scenarios, typecheck, lint and production build. Those results do **not** certify the current post-review worktree because subsequent fixes changed backend contracts and frontend behavior. A complete frozen-candidate rerun remains mandatory.
