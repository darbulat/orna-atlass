# Spec: Email verification and password recovery

- Status: accepted
- Owner: backend + frontend + security
- Last updated: 2026-07-27
- Related issue/PR: user request in current delivery
- Related ADRs: [ADR-0002](../docs/adr/0002-playback-access.md)

## Problem and outcome

Password accounts can be created and authenticated, and `users.email_verified_at` exists, but password registrations have no way to prove mailbox ownership and users cannot recover a forgotten password. The outcome is an accessible, enumeration-resistant email verification and password reset flow using the configured SMTP boundary and the existing account UI.

## Context and evidence

- Current-state section: `docs/CURRENT_STATE.md` authentication and membership row.
- Domain rules/invariants: `docs/DOMAIN_RULES.md` authentication rules; services own transactions and refresh tokens are hashed, rotated and revocable.
- Relevant code: `modules/auth/{router,service,magic}.py`, `modules/users/*`, `web/lib/api/auth.ts`, `web/app/membership/page.tsx`.
- Existing persistence: `users.email_verified_at` and nullable `password_hash` were added by migration `0014_oauth_identities`; no new database column is required.

## Scope

### In scope

- Authenticated request and anonymous one-time confirmation of a password account email.
- Enumeration-safe password reset request, one-time reset confirmation, password replacement and revocation of all refresh sessions.
- Opaque 256-bit tokens stored only under SHA-256-derived Redis keys with bounded TTL, delivery-gated activation and recoverable atomic claim/finalize semantics.
- SMTP delivery, bounded errors, audit events, rate limiting, explicit user/API status, generated contracts and responsive browser flows.
- Fragment-based frontend token links so raw tokens do not reach HTTP request targets, access logs or referrers.

### Non-goals

- Blocking login or playback for unverified accounts; that requires a separate product-policy decision.
- Changing email addresses, linking OAuth identities, MFA, passkeys, checkout or membership entitlement.
- Persisting recovery tokens in PostgreSQL or building a durable email outbox/worker.
- Automatically assigning passwords to OAuth-only accounts.

## Design and boundaries

- Router translates HTTP and owns cookie clearing; service owns user state, audit events and commits; repositories query/flush only.
- A dedicated auth-token delivery module owns Redis token prepare/activate/claim/finalize state and SMTP messages. Raw tokens exist only in email fragment URLs and request bodies.
- Email verification requests require an active authenticated user. Already verified accounts return an idempotent accepted response without sending another message.
- Password reset requests always return the same accepted contract for unknown, inactive and passwordless accounts. Delivery failures remove token state; public copy says only that a matching eligible account will receive mail.
- Confirmation atomically claims the active token, revalidates active user identity/email under the applicable database lock, updates the user and commits. A known pre-commit failure rolls the claim back to active; an exception or cancellation from `COMMIT` has an ambiguous durable outcome and therefore finalizes the claim fail-closed rather than risking replay. Finalization retains a bounded version tombstone until token expiry so a delayed older delivery cannot reactivate after the newer token was used. Password reset also revokes every refresh token. Existing access JWTs remain valid only for their existing short TTL; the confirming browser's auth cookies are cleared.
- Registration remains compatible: password login is not gated by verification. The browser requests verification after a newly registered account is authenticated and always offers resend from the account dashboard.

## Contract and data changes

- `UserRead.email_verified: boolean`.
- `POST /api/v1/auth/email-verification/request` → `202 {accepted: true}`; authenticated.
- `POST /api/v1/auth/email-verification/confirm` with `{token}` → `{status: "verified"}`.
- `POST /api/v1/auth/password-reset/request` with `{email}` → `202 {accepted: true}`.
- `POST /api/v1/auth/password-reset/confirm` with `{token, password}` → `{status: "password_reset"}` and clears auth cookies.
- Malformed confirmation bodies use the same bounded `400` error DTO as invalid or expired tokens; these routes do not publish a separate `422` contract.
- No schema migration. Generated OpenAPI and frontend types change.

## Security, privacy and failure behavior

- Tokens use at least 256 bits of randomness, short TTLs (24 hours verification, 1 hour reset) and SHA-256 Redis keys. A token remains pending until SMTP delivery succeeds; activation orders concurrent deliveries without invalidating an older successfully delivered token merely because a newer delivery failed. Confirmation uses an atomic single-claim protocol, then finalizes only after the service-owned PostgreSQL commit. Retrying activation after an unknown Redis response preserves an exact token that concurrently advanced to claimed or finalized state.
- Token payloads contain only bounded kind, user id and normalized email; tokens/emails are absent from logs, metrics, analytics and public errors.
- Fragment links prevent tokens from entering gateway/API request lines and referrer headers.
- Request and confirm endpoints use the existing fail-closed Redis auth rate limiter.
- Reset request responses do not disclose account existence, active state or sign-in method.
- Invalid, expired, mismatched and replayed tokens return one bounded invalid/expired error.
- A successful password reset revokes all refresh sessions and never issues a new session automatically.
- After an ambiguous reset transport outcome, the browser discards the raw token and any locally authenticated account state, then directs the user to try the new password or request another link; it never restores a possibly revoked session or offers an unsafe replay as if the first mutation were known to have failed.
- Recovery request busy, accepted and error state belongs to the current navigation generation. Browser Back, history changes and an explicit return to sign-in invalidate delayed request continuations so they cannot disable sign-in controls or render stale recovery messages.

## Acceptance scenarios

1. Given an unverified active password account, requesting verification sends a one-time link; confirmation marks it verified and replay fails.
2. Given an already verified account, requesting verification succeeds idempotently without another email.
3. Given missing SMTP/Redis or failed delivery, authenticated verification reports unavailable and orphaned state is removed.
4. Given any submitted recovery email, the request response is identical; only an eligible active password account receives a reset link.
5. Given a valid reset link and compliant new password, confirmation changes the hash, revokes all refresh tokens, clears browser auth cookies and replay fails.
6. Invalid, expired, malformed, wrong-kind or identity-mismatched tokens never modify a user.
7. Verification/reset tokens are removed from browser location before API calls and never enter analytics payloads.
8. Keyboard and screen-reader users receive labelled forms, progress, success and error states; mobile controls remain within the viewport and at least 44 px high.
9. Given a finalized newer token and a later ambiguous issuance cleanup, the finalized version evidence survives until TTL and a delayed older delivery cannot activate.
10. Given an authenticated browser and an ambiguous password-reset confirmation, local account state is discarded and the browser offers sign-in rather than restoring the possibly revoked session.
11. Given a pending reset request, leaving recovery through Browser Back or sign-in navigation immediately releases sign-in controls and ignores the delayed request outcome.
12. Optional-auth session operations publish anonymous, Bearer and cookie alternatives in OpenAPI, while protected recovery operations publish only Bearer or cookie authentication.
13. Given a lost activation response followed by a concurrent token claim, retrying activation preserves the claim, confirmation can finalize it, and delayed older delivery remains rejected.
14. Given a pending password-reset confirmation, leaving through explicit sign-in or Browser Back clears the local account/reset view and ignores the stale continuation without restoring an authenticated dashboard.
15. Given a pending password login or magic-link request, entering reset through a post-mount fragment releases reset controls and prevents the stale action from publishing account, message or busy state.
16. Given a pending verification delivery, entering a verification callback immediately releases resend ownership and suppresses the delayed delivery outcome.
17. Given same-route navigation from register to an unsupported membership mode, the UI resolves to the default auth mode rather than retaining stale registration state.
18. Given access and refresh cookies plus a commit-unknown password-reset confirmation, the `503`
    response is `no-store` and expires both cookies; a definitive sanitized invalid-token `400`
    preserves an otherwise valid session.
19. Given cancellation recorded during verification or reset after a successful Redis claim or an
    ambiguous PostgreSQL commit, a compensation failure or later cancellation—including Redis client
    close after mutation—cannot replace the exact first cancellation. Compensation has a two-second
    internal deadline, after which the child is cancelled and observed while token state remains
    fail-closed and request cancellation returns.
20. Given a new verification/reset fragment while another callback owns state, the prior owner and
    sensitive reset fields are discarded before selecting exactly one new owner. A fragment with both
    recognized token keys is rejected without either confirmation request.

## Verification plan

- Narrow regression: token issue/consume/replay/delivery-failure tests and service state-transition tests.
- Backend: auth contract/router/service tests, full pytest and Ruff.
- Dependency integration: disposable Redis/PostgreSQL tests where available; no production dependencies.
- Frontend: typed API checks, unit/type/lint/build and focused/full Playwright.
- Migration: no new migration; `alembic check` confirms no model drift.
- Security review: exact staged backend/token, frontend/session and contract/deployment reviews.

## Rollout, rollback and observability

Deploy API before or with web because web depends on new contracts. The change is additive and requires no migration. Rolling back web/API removes the new flows without data rollback; already verified timestamps and changed passwords are durable user actions and must not be reversed. Audit events record only bounded event types and user ids.

## Documentation and decisions

Update `docs/CURRENT_STATE.md` and `docs/DOMAIN_RULES.md` after executable evidence passes. No ADR is required because the implementation stays within the existing authentication architecture.

## Open questions

- Product owner: whether unverified password accounts should later be restricted. Explicitly deferred; current login behavior remains unchanged.
- Operations: real sender/domain and production round-trip verification depends on configured SMTP credentials and is a deployment gate, not a local-test claim.

## Implementation handoff

Primary owners: backend for token/service/contracts, frontend for account/recovery UX, security for enumeration/token/session boundaries, test for replay/outage/browser evidence, documentation for current-state reconciliation. Preserve the unrelated local `deploy/nginx.conf.template` certificate diff.
