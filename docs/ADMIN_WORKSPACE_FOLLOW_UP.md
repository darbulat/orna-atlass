# Admin Workspace v1 follow-up

Status: implementation complete. Release approval still requires the frozen-candidate review, exact-head CI and production smoke described below; results belong in the PR/deployment handoff rather than in this durable checklist.

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

## Closed implementation requirements

### Backend and audit contracts

- Executable acceptance tests cover the exact location, session, collection, media, role and membership audit event names, subjects, actor provenance and allowlisted metadata.
- A failure-atomicity canary proves that an audit insert failure prevents the service-owned transaction from committing.
- Collection link-only stale writes and last-admin role changes retain their PostgreSQL concurrency canaries.
- Every `/api/v1/admin/**` outcome, including validation/auth errors and empty `204` responses, receives `Cache-Control: no-store` at the application boundary.

### Frontend privacy and authorization

- Browser coverage proves focus revalidation clears privileged content after role loss and performs at most one access-cookie refresh before failing closed.
- Target-email confirmation is checked against the freshly loaded target user, and a mismatch sends no mutation request.
- Sensitive e-mail, IDs, IP and User-Agent filters remain transient and are excluded from URL, history, notices and browser persistence.
- Runtime parsers accept only the generated array contracts and validate required fields, nested resources, enums, UUIDs, bounded coordinates, RFC 3339 timestamps, e-mail and revisions before privileged rendering.
- Admin interaction state is bounded in `web/components/admin/**`; the route remains the server-side workflow composition boundary.

### Concurrency, paging and request behavior

- The stateful browser mock exercises GET revision, one successful mutation, a second mutation with the old ETag, typed `412`, and no replay.
- Multi-page list scenarios assert stable ordering, bounded filters and no duplicate rows.
- Network request counters prove rejected confirmation and stale-write scenarios do not produce extra mutations.

### OpenAPI and generated contracts

- Admin errors and enums remain represented in generated contracts; two consecutive generations are byte-identical.
- A mechanical backend matrix checks every admin operation for authorization-before-domain-work, endpoint status behavior and no-store responses.

### Production-like smoke

- The read-only smoke script accepts route/API endpoints and credentials through environment variables only; it does not place credentials in source, arguments, URLs or logs.
- It checks anonymous/member denial, authenticated admin identity/location/audit reads, response shape and `Cache-Control: no-store`.
- The HTTPS Compose overlay exposes the direct frontend probe only on loopback (`127.0.0.1:3000`), while the nginx HTTP redirect and HTTPS `/admin` route remain the public ingress checks.

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

## Verification baseline for release handoff

The implementation candidate has executable coverage for backend audit/atomicity/no-store behavior, strict privileged parsers, refresh-once/revoke behavior, target confirmation, sensitive-filter privacy, stale writes, paging and mobile controls. The PR handoff must record the exact candidate hash plus the final results of all commands above, independent review, exact-head CI and both direct/frontend and nginx production smoke paths. Historical counts are not release evidence for a later commit.
