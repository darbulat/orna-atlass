# Spec: Admin workspace v1

- Status: draft
- Owner: product + backend + frontend + security
- Last updated: 2026-07-30
- Related issue/PR: none
- Related ADRs: [`ADR-0001`](../docs/adr/0001-public-coordinate-projection.md),
  [`ADR-0002`](../docs/adr/0002-fail-closed-playback.md),
  [`ADR-0003`](../docs/adr/0003-versioned-media-assets.md),
  [`ADR-0004`](../docs/adr/0004-service-owned-transactions.md),
  [`ADR-0005`](../docs/adr/0005-segmented-hls-playback.md)
- Supporting analysis: [`../docs/ADMIN_PANEL_ANALYSIS_RU.md`](../docs/ADMIN_PANEL_ANALYSIS_RU.md)

## Problem and outcome

ORNA Atlas уже имеет admin-auth и набор mutation endpoints, но не имеет полноценного
административного web workspace. Администратор не может просматривать полный набор draft/private/
hidden/archived сущностей, находить пользователя, видеть pipeline в контексте сессии и выполнять
существующие команды через безопасный UI. Использовать публичные projections нельзя: они намеренно
скрывают защищённые данные и непубличные состояния.

Результат v1:

- authenticated active `admin` получает отдельный `/admin` workspace;
- anonymous получает `401`-ориентированный sign-in state, authenticated non-admin/editor — `403`;
- администратор может browse/create/update locations, sessions и collections через admin DTO;
- администратор может видеть processing state и запускать только уже существующие безопасные retry/
  registration operations;
- user role и membership management включаются отдельным production gate после last-admin и audit
  hardening;
- exact sensitive coordinates не появляются в public DTO, browser cache, analytics или logs;
- каждая успешная admin mutation имеет audit event в той же service-owned transaction.

Измеримый критерий: каждый in-scope workflow имеет backend allow/deny regression, generated OpenAPI
contract, deterministic Playwright success/error scenario и production-like smoke для route/auth.

## Context and evidence

- Current-state section: [`../docs/CURRENT_STATE.md`](../docs/CURRENT_STATE.md), строки capability
  matrix про coordinate privacy, admin authentication, frontend contracts и processing.
- Domain rules/invariants: [`../docs/DOMAIN_RULES.md`](../docs/DOMAIN_RULES.md), секции Public
  coordinates, Session publication and playback, Authentication and roles, Processing jobs,
  Repeated and concurrent actions.
- Architecture boundaries: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) и
  [`../docs/architecture/BOUNDARIES.md`](../docs/architecture/BOUNDARIES.md).
- Backend entry points:
  - `orna_atlas/app/modules/admin/router.py`;
  - `orna_atlas/app/core/security.py`;
  - domain services/repositories/schemas в `locations`, `sessions`, `media`, `collections`, `users`,
    `memberships`, `admin`.
- Frontend entry points:
  - `web/app/`, `web/components/`, `web/lib/api/`;
  - generated contracts `web/openapi.json`, `web/lib/api/generated.ts`;
  - `web/e2e/mock-api.mjs`, `web/e2e/*.spec.ts`.
- Existing evidence:
  - `orna_atlas/app/tests/test_sprint2_openapi.py`;
  - `orna_atlas/app/tests/test_sprint8_auth_membership.py`;
  - `orna_atlas/app/tests/test_sprint9_editorial.py`;
  - lifecycle/media/privacy tests named in the implementation plan.

At drafting time the backend commands existed while the browse API and web workspace did not. The
implemented runtime is now recorded in `CURRENT_STATE.md`; this draft remains the change-level
acceptance context and does not supersede executable contracts or ADR-0012.

## Scope

### In scope

#### Foundation

- `admin`-only authorization on every `/api/v1/admin/**` endpoint using the current DB-resolved role.
- Typed `AdminIdentityRead` response for `GET /api/v1/admin/me`.
- Separate Next.js admin shell under `/admin`; no privileged controls in the public `SiteHeader`.
- `Cache-Control: no-store` for admin API responses and admin Next.js pages.
- Cookie-auth admin writes reject absent or non-allowlisted `Origin`; Bearer-auth API clients remain
  supported.
- Detail reads expose an opaque revision precondition; UI-reachable update/archive actions submit
  it and receive a typed stale-write error instead of silently overwriting a newer edit. The exact
  wire form (`ETag`/`If-Match` or an explicit version field) must be frozen before acceptance.

#### Browse/read API

Add the following exact operations while preserving existing mutation paths:

```http
GET /api/v1/admin/locations
GET /api/v1/admin/locations/{location_id}
GET /api/v1/admin/sessions
GET /api/v1/admin/sessions/{session_id}
GET /api/v1/admin/collections
GET /api/v1/admin/collections/{collection_id}
GET /api/v1/admin/users
GET /api/v1/admin/users/{user_id}
GET /api/v1/admin/audit-events
```

All list operations use bounded `limit`/`offset` and deterministic ordering. The UI uses “Load more”
rather than requiring a total count. Filters:

- locations: `q`, `coordinate_visibility`, `sensitivity_level`, `include_archived`;
- sessions: `q`, `location_id`, `publication_status`, `processing_status`, `access_level`,
  `include_archived`;
- collections: `q`, `is_public`;
- users: `email`, `role`, `is_active`, `membership_status`;
- audit: existing `event_type` plus `actor_user_id`, `subject_type`, `subject_id`, `created_from`,
  `created_to`.

`q`/`email` are trimmed and bounded to 200 characters; empty strings are treated as absent. List
ordering includes a unique tie-breaker (`id`) to avoid unstable offset pages.

#### Editorial workflows

- Locations: list, create, detail/edit. Exact and public coordinates are visibly separated;
  `hidden_public` never shows a public coordinate preview. Location archive is not exposed in v1.
- Sessions: list, create as draft by default, detail/edit, separate publication/access/processing
  controls, processing status, managed-key asset/segment registration and bounded retry.
- Session archive may be exposed only with typed confirmation and explicit notice that linked assets
  enter the existing retention/cleanup lifecycle. No undo is claimed.
- Collections: list, create, detail/edit and ordered location/session membership using admin datasets.
  Hard delete is not exposed.
- Audit: list/filter; metadata rendered as escaped, collapsed JSON; IP/user-agent treated as personal
  operational data.

#### Account administration production gate

- User list and detail include `UserRead` plus membership projection; password hashes, refresh token
  hashes and OAuth provider subjects are never included.
- Existing exact mutation paths remain:

```http
PATCH /api/v1/admin/users/{user_id}/role
PUT /api/v1/admin/memberships/{user_id}
```

- An admin cannot change their own role in v1.
- Role change serializes against concurrent role changes and must not leave zero active admins.
- Tier C must define an aggregate user/membership revision precondition before its UI is enabled;
  concurrent role or membership edits must not silently overwrite a newer result.
- Target user must exist and be active, as in the current rule.
- Role and membership changes are separate forms, separate confirmations and separate audit events.
- The frontend account-administration navigation is disabled in production until backend security
  regression, exact-candidate security review and migration/contract gates (if any) are green.

#### Audit coverage

Preserve existing event names `user.role_updated` and `membership.updated`. Add these exact event
names for UI-reachable admin mutations:

- `location.created`, `location.updated`;
- `session.created`, `session.updated`, `session.archived`;
- `collection.created`, `collection.updated`;
- `media.asset_registered`, `media.segments_registered`;
- `media.processing_retried`, `media.asset_archived`.

Every event records the actor when available, subject, bounded changed-field names and request IP/user
agent. Metadata must not contain passwords, tokens, object credentials, exact coordinates, arbitrary
full request bodies or raw media/worker payloads. For a local-only admin actor, `actor_user_id` stays
`null` and bounded metadata records `actor_mode=local`; production cannot enter this mode.

### Non-goals

- Giving `editor` any admin route or user-management permission.
- Introducing recordist/moderator/custom permissions or tenant scoping.
- Browser binary upload, multipart upload or presigned-upload lifecycle.
- User activation/deactivation, account deletion, password reset on behalf of a user, OAuth identity
  management or refresh-session inspection/revocation.
- Billing, payments, refunds, invoices or external subscription-provider integration.
- Location archive, collection hard delete, media object purge, bulk delete or prefix cleanup in UI.
- Bulk import/export, CSV, moderation queues, analytics dashboards or arbitrary SQL/reporting.
- Redesigning the public site or adding admin links for non-admin users.

## Design and boundaries

### Backend dependency flow

- `modules/admin/router.py` owns HTTP translation, shared admin dependency, request context and admin-
  specific read endpoints.
- Read use cases may be coordinated by `modules/admin/service.py`, but each domain query remains in
  the responsible repository. Admin routers never query ORM directly.
- Existing domain mutations remain in the responsible service:
  `router -> locations/sessions/media/collections/users/memberships service -> repository -> model`.
- Repositories query/flush only. The responsible domain service writes the domain mutation and audit
  event, then commits once. Cache invalidation remains after commit.
- Request actor context is a bounded typed object passed from router to service; service code never
  trusts actor IDs from request bodies.

### Frontend dependency flow

- `web/app/admin/**` composes routes and no-store metadata.
- `web/components/admin/**` owns shell, tables/cards, forms, confirmation dialogs and interaction
  state.
- `web/lib/api/admin.ts` owns credentials, refresh-once behavior and generated admin DTOs.
- Runtime parsing validates high-risk discriminants/enums before exact coordinates or role controls
  are rendered. Malformed privileged payloads fail closed with an unavailable state.
- `401` routes to `/membership?mode=login&returnTo=<admin-path>`; `403` renders a denied page without
  leaking admin data. A role loss during the session clears rendered privileged state.

### Staged rollout

1. Foundation/read-only workspace.
2. Editorial mutations and processing controls.
3. Account administration gate.

Each stage is independently deployable; later-stage UI is absent, not merely hidden with CSS, until
its backend and review gates pass.

## Contract and data changes

### New/changed schemas

- `AdminIdentityRead`: `id`, `role="admin"`, `mode="token"|"local"`.
- `AdminLocationRead`: reuse existing schema for list/detail and mutations.
- `SessionRead`: reuse existing admin session projection for list/detail; no public projection is
  widened.
- `CollectionAdminRead`: reuse existing schema.
- `AdminUserRead`: `{ user: UserRead, membership: MembershipRead }`, where absent membership uses the
  existing inactive/none projection.
- `AuditEventRead`: unchanged fields; list query gains bounded filters.

List responses remain arrays in v1 to match repository conventions. `limit` maximum is 100 except
`audit-events`, which retains maximum 500. Default UI page size is 50 (audit 100).

### Compatibility

- Existing public contracts are unchanged.
- Existing admin mutation paths and request bodies are unchanged.
- `GET /admin/me` becomes typed but keeps existing keys and values.
- Generated `web/openapi.json` and `web/lib/api/generated.ts` must be regenerated atomically.
- No schema migration is currently expected. If query plans show a missing production index, add an
  Alembic revision and update this section before implementation proceeds.

## Security, privacy and failure behavior

- Authorization is server-side on every request; UI role state is not an enforcement boundary.
- Exact coordinates only use `AdminLocationRead` after successful admin authorization. Public DTO
  canaries must remain unchanged.
- Admin API/pages send `Cache-Control: no-store`; frontend stores no admin payload in localStorage,
  IndexedDB, analytics events or URL query values beyond bounded non-sensitive filters.
- Mutation payloads use JSON and same-origin/allowlisted Origin checks for cookie credentials.
- Any audit insert failure rolls back the associated DB mutation; the API must not return success.
- Cache invalidation happens only after commit. A post-commit invalidation failure is reported/
  observed according to the existing domain policy and cannot roll back committed data silently.
- Processing retry returns existing active work when the domain idempotency rule applies. The UI
  disables duplicate submit but does not substitute for backend idempotency.
- Storage/broker failures remain typed failures; UI never invents ready/playable status.
- Session/location archives use only recorded asset inventories and existing retention cleanup. Broad
  prefix deletion remains forbidden.
- Role changes use transaction serialization. Concurrent attempts cannot both observe themselves as
  preserving an admin and commit a zero-admin result.
- Editorial and account forms carry the accepted revision token. Missing/stale preconditions fail
  before mutation and audit success; the UI reloads current data and does not auto-replay the write.
- Audit metadata is allowlisted and bounded. Exact coordinates, tokens, credentials, storage keys
  and raw arbitrary metadata are excluded.
- Admin forms render all server-originated text as text, never HTML.

## Acceptance scenarios

1. Given no authentication, when `/admin` loads, then no admin data request succeeds and the page
   offers sign-in with the exact return path.
2. Given an active member or editor, when any `/api/v1/admin/**` endpoint is called, then it returns
   `403` and no admin payload or mutation is produced.
3. Given a token whose claim says admin but whose DB role is now member, when an admin endpoint is
   called, then current DB state wins and access is denied.
4. Given an active admin, when the locations list is loaded with `include_archived=true`, then hidden
   and archived records are visible through `AdminLocationRead`, while the public location endpoints
   remain unable to reveal hidden or exact protected coordinates.
5. Given malformed admin list payload or unknown enum value, when the frontend parses it, then the
   corresponding region fails closed and does not render stale privileged data.
6. Given a new location with invalid IANA timezone or mismatched public coordinate pair, when saved,
   then validation is shown and no row/audit event commits.
7. Given a hidden location, when its form is edited, then exact coordinates are available only inside
   the authorized form and no public preview coordinates are invented.
8. Given a new session, when it is created without an explicit publication promotion, then it remains
   `draft`; processing readiness and access policy remain separate controls.
9. Given a processing retry is already active, when retry is submitted again, then backend converges
   to the existing active operation and UI does not claim a second successful job.
10. Given broker/storage outage, when asset registration/retry is attempted, then the UI shows a typed
    unavailable/error state and does not display ready/playable success.
11. Given session archive confirmation, when archive succeeds, then session publication becomes
    archived, assets follow existing retention cleanup, one audit event commits, and public cache is
    invalidated after commit.
12. Given an admin edits a collection using hidden/draft entities, when the collection is public,
    then existing public projection rules still omit hidden/non-published nested content.
13. Given an admin attempts to change their own role, when submitted, then backend rejects it with a
    conflict/forbidden domain response and no audit success event is written.
14. Given only one active admin, when another actor/concurrent request attempts to demote that admin,
    then serialization rejects the change and at least one active admin remains.
15. Given two authorized admins, when one changes another active user's role, then DB mutation and
    `user.role_updated` audit event commit atomically and a stale target JWT loses privileges on its
    next request.
16. Given membership update, when it commits, then entitlement follows only `status=active` and
    unexpired `expires_at`; role is unchanged; `membership.updated` records no secret/private body.
17. Given cookie-auth mutation from absent/disallowed Origin, when called, then it is rejected before
    domain mutation. Given equivalent Bearer-auth automation, it remains supported.
18. Given a 320 px viewport and keyboard-only input, when an admin completes each in-scope workflow,
    then there is no document-wide horizontal overflow, focus remains visible, dialogs trap/restore
    focus, and actionable controls are at least 44×44 CSS px.
19. Given exact coordinates, user email, IP or user-agent are displayed, when browser history/cache,
    analytics payloads and client storage are inspected, then those values are absent outside the
    current no-store admin response/UI.
20. Given an audit event filter, when pagination advances, then deterministic ordering prevents
    duplicate/omitted rows within an unchanged dataset and filter values remain bounded.
21. Given two admins loaded the same editable record, when one commits and the other submits the
    stale form, then the second write returns the accepted typed precondition failure, writes no
    success audit event and offers an explicit reload rather than silently merging fields.

## Verification plan

- Narrow regression tests:
  - new `orna_atlas/app/tests/test_admin_workspace.py` for auth, list/detail, filters, audit atomicity,
    self/last-admin safety and no-store/origin behavior;
  - existing privacy/lifecycle/media tests for non-regression.
- Backend unit/contract checks:
  - `python -m pytest orna_atlas/app/tests/test_admin_workspace.py -q`;
  - `python -m pytest orna_atlas/app/tests/test_sprint2_openapi.py orna_atlas/app/tests/test_public_dto_privacy.py orna_atlas/app/tests/test_lifecycle_and_metadata.py -q`;
  - `python -m pytest`;
  - `python -m ruff check .`.
- Disposable dependency/integration checks:
  - add admin query/transaction concurrency cases under `tests/integration/` only if unit mocks cannot
    prove locking, filtering/index usage or atomic rollback;
  - run with disposable PostgreSQL, never production.
- Frontend unit/type/build checks:
  - generated-contract and runtime-parser tests;
  - `cd web && npm run api:check && npm run test:unit && npm run typecheck && npm run lint && npm run build`.
- Browser/accessibility checks:
  - `web/e2e/admin.spec.ts` with mock API for deterministic auth/success/error/responsive flows;
  - `cd web && npm run test:e2e -- admin.spec.ts`;
  - one full `npm run test:e2e` cycle after focused GREEN.
- Migration upgrade/downgrade checks:
  - not applicable if no schema/index change;
  - if an index is added: `alembic upgrade head`, `alembic check` and repository migration-cycle command
    against disposable PostgreSQL.
- Production smoke after approved SHA deploy:
  - anonymous `/admin` does not expose data;
  - admin login reaches workspace;
  - member receives denial;
  - one read-only list and audit query succeed;
  - no destructive production mutation is used as smoke evidence.

## Rollout, rollback and observability

- Ship foundation/read-only routes first. Enable editorial mutations only after exact-head review and
  browser checks. Enable account administration last.
- Use a frontend/server configuration gate for account administration; backend remains authoritative.
- Emit bounded route-template logs and existing request IDs. Do not label metrics by user ID, email,
  location ID, exact path value or audit subject.
- Observe admin request counts by operation/status and processing retry outcomes using bounded labels.
- Rollback frontend can remove workspace routes without data migration. Backend additive GET routes
  are backward-compatible. Audit event additions are data-compatible and remain after rollback.
- A committed archive or role/membership change is not automatically reversible by deployment
  rollback; recovery is a new explicit domain mutation, not database history rewriting.

## Documentation and decisions

- Add this spec to `specs/README.md` while status is `draft`.
- Keep `docs/ADMIN_PANEL_ANALYSIS_RU.md` as supporting analysis, not runtime truth.
- Update `docs/CURRENT_STATE.md` only after the implemented capability and limitations are proven.
- Update `docs/DOMAIN_RULES.md` only if product accepts editor permissions, self-role change or a new
  account policy; this draft does not change those rules.
- No ADR is required for the proposed v1 because it follows existing boundaries and accepted ADRs.
  Fine-grained permissions or browser upload may require a separate durable decision.

## Open questions

- Product owner before acceptance: should session archive be visible in v1, or should v1 remain
  create/update/retry only? Default in this draft: visible with typed confirmation.
- Product + operations before Slice B: is managed storage-key registration acceptable as the initial
  media workflow? Default: yes; browser binary upload is deferred.
- Product + security before Slice C: should user/membership management launch with editorial tools or
  remain a separately enabled production gate? Default: separate gate.
- Product owner before acceptance: should admin links appear in the signed-in account dashboard for
  role `admin`? Default: yes, after `UserRead.role` is fetched; no public header link.
- Operations before implementation: expected dataset sizes for users, sessions and audit events, to
  decide whether existing indexes are sufficient. Default: bounded offset pages; add indexes only
  with measured query evidence.
- Security before acceptance: is Origin enforcement sufficient with current SameSite=Lax cookies, or
  is a synchronizer CSRF token required? Default: Origin enforcement for cookie-auth admin writes,
  retain Bearer automation.
- Architect + backend before acceptance: use standard `ETag`/`If-Match` (`428` when missing, `412`
  when stale) or an explicit version field for optimistic concurrency? Default: `ETag`/`If-Match`
  for editorial detail/update/archive; define an aggregate revision before Tier C.

## Implementation handoff

Primary owner: architect for contract/scope, then backend and frontend vertical slices; security owns
account administration and privacy review; test owns acceptance evidence; documentation reconciles
current state after implementation.

Sequence constraints:

1. Accept scope/defaults and freeze exact endpoint/schema/event names.
2. Prove backend deny paths and role invariants before adding UI actions.
3. Add one list/detail workflow at a time, regenerate OpenAPI, then build its UI.
4. Add audit in the same domain transaction before enabling each mutation.
5. Keep account administration absent until its independent gate passes.
6. Freeze and review the exact staged candidate, run full required checks, deploy approved SHA and
   perform non-destructive production smoke.

Known risks: broad admin DTOs contain sensitive operational data; offset pagination can drift under
heavy writes; managed-key media registration is operational rather than end-user-friendly; current
mutation services need audit-context signature changes. None permit weakening public privacy,
playback fail-closed behavior, service-owned transactions or inventory-bounded cleanup.
