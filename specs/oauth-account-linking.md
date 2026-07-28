# Spec: Explicit OAuth account linking after email conflict

- Status: accepted
- Owner: authentication/backend + frontend
- Last updated: 2026-07-28
- Related issue/PR: pending
- Related ADRs: [ADR-0010](../docs/adr/0010-explicit-oauth-account-linking.md)

## Problem and outcome

A verified OAuth identity whose normalized email already belongs to an ORNA account currently ends
in a generic `account_conflict` notice. Refusing an implicit email-based merge is correct, but the
user has no safe recovery path. The outcome is a resumable flow that asks the user to authenticate
the existing ORNA account, explicitly confirm the provider connection, and then links the provider
subject to that account.

## Context and evidence

- Current-state section: `docs/CURRENT_STATE.md` authentication and membership.
- Domain rules/invariants: `docs/DOMAIN_RULES.md` authentication and roles.
- Relevant entry points: auth OAuth callback/router, auth service/repository/models, Redis OAuth
  state, generated OpenAPI types, `web/lib/api/auth.ts`, and the membership auth state machine.
- Existing evidence: `test_social_login_refuses_implicit_link_to_existing_email` and the browser
  `account_conflict` notice prove the current safe-but-terminal behavior.

## Scope

### In scope

- Preserve the rule that provider identities are keyed by `(provider, subject)` and are never
  silently linked by matching email.
- Create a short-lived, opaque, HttpOnly, browser-bound linking intent after a verified OAuth email
  conflicts with an existing active account.
- Require a successful explicit authentication of that exact existing account after the intent was
  created; refresh alone and a pre-existing session do not qualify.
- Show an actionable anonymous UX, preserve the intent through password, magic-link, or another
  configured OAuth sign-in, and require a separate confirmation action.
- Link transactionally, audit the change, handle uniqueness races fail-closed, support cancellation,
  and provide truthful expired/unavailable/conflict states.

### Non-goals

- Automatic linking based only on provider email.
- Account merging, moving an identity between users, unlinking the last sign-in method, or managing
  all connected providers in account settings.
- Persisting provider access or ID tokens.
- Changing membership entitlement policy.

## Design and boundaries

The OAuth callback verifies the provider identity, resolves the existing user by normalized email,
and stores a bounded Redis intent containing only provider identity fields, target user ID and safe
return path. The browser receives only an opaque HttpOnly cookie. Explicit login callbacks may mark
that exact intent reauthenticated only when the authenticated user ID matches its target. Refresh
never marks it.

A new authenticated confirmation endpoint atomically consumes the intent before calling the auth
service. The service locks/validates the active target user, checks existing provider identities,
creates the identity and audit event, and owns the commit. Repository methods query/flush only.
Known failures after intent consumption require restarting OAuth; an ambiguous successful commit is
safe because later provider login resolves the durable identity.

The membership page reads a bounded pending-intent status, renders an actionable sign-in state while
anonymous, and renders an explicit connect/cancel confirmation only after matching reauthentication.
All async state writes are auth-generation guarded.

## Contract and data changes

- Add `GET /api/v1/auth/oauth/link/pending`.
- Add `POST /api/v1/auth/oauth/link/confirm`.
- Add `POST /api/v1/auth/oauth/link/cancel`.
- Add explicit allowlisted response schemas and regenerate OpenAPI/TypeScript contracts.
- No database schema change: existing OAuth identity uniqueness constraints already enforce one
  subject owner and one identity per provider per user.
- Redis intent payload is ephemeral and versioned; no provider token is stored.

## Security, privacy and failure behavior

- The intent cookie is opaque, host-only, HttpOnly, Secure in production, SameSite=Lax and scoped to
  the auth API. Redis stores only a digest-derived key and a bounded payload.
- Pending status exposes only provider, pending/ready state, and no email, subject, user ID or token.
- Confirm/cancel require same-origin POST semantics; confirm additionally requires an active current
  user matching both target and post-intent reauthentication marker.
- Refresh, registration, another user's login, expired/corrupt intent, Redis outage and provider/user
  uniqueness conflicts fail closed without linking.
- Intent consumption is single-use. Database errors never invent success. Logs, redirects, cookies
  and public DTOs omit provider subject and all credentials/tokens.

## Acceptance scenarios

1. Given a verified Google identity with an email owned by an existing password account, callback
   creates a pending intent and redirects with `account_conflict` without linking.
2. Given that intent, password login as the target account marks it ready; the UI asks for explicit
   confirmation; confirm creates exactly one Google identity and reports success.
3. Given that intent, magic-link or an already-linked different OAuth provider authentication for
   the target account can mark it ready and resume the same confirmation UX.
4. A pre-existing session, refresh, registration, or authentication as another user never marks the
   intent ready and cannot link it.
5. Missing, expired, replayed, corrupt, wrong-user or unready intents return a sanitized denial and
   create no identity or audit success.
6. A provider subject already owned by another user, or a different subject already linked for the
   same provider, remains unchanged and returns conflict.
7. Concurrent confirmations converge to one identity; no repository commits occur.
8. Cancel removes the pending intent and cookie; browser Back or stale responses cannot restore the
   confirmation state.
9. Public callback/query data, logs and generated contracts expose no provider subject, target user
   ID, raw intent, authorization code or provider token.

## Verification plan

- Narrow regression tests: Redis intent lifecycle, service linking/races, callback cookie/redirect,
  explicit-auth marking, pending/confirm/cancel routes.
- Backend checks: focused auth tests, complete pytest and Ruff.
- Disposable integration: real Redis single-use lifecycle and PostgreSQL identity uniqueness/race
  behavior in the repository integration suite.
- Frontend checks: generated contract check, Node unit tests, typecheck, lint and production build.
- Browser checks: anonymous conflict instructions, password and magic-style resume, explicit
  confirm/cancel, denial/stale-generation/accessibility behavior.
- Migration checks: not applicable because the existing schema is unchanged; `alembic check` still
  verifies no model drift.

## Rollout, rollback and observability

Deploy backend and frontend from one reviewed commit because the UI consumes new API contracts.
Existing OAuth logins remain compatible. Rollback removes the new endpoints/UI; unconsumed Redis
intents expire automatically and durable identities already linked remain valid under the existing
OAuth login behavior. Audit `auth.oauth_identity_linked` without subject/email metadata.

## Documentation and decisions

Update `docs/DOMAIN_RULES.md` with the explicit-link invariant and `docs/CURRENT_STATE.md` only after
all evidence is green. The durable cross-module authentication boundary and rollback policy are
recorded in [ADR-0010](../docs/adr/0010-explicit-oauth-account-linking.md).

## Open questions

None for this accepted scope.

## Implementation handoff

Primary roles are backend/auth service, frontend auth state, test, and security review. Deliver in
vertical RED/GREEN slices: intent lifecycle; transactional service; HTTP callback/endpoints; frontend
resume/confirmation; generated contracts and full verification. Preserve unrelated worktree files.
