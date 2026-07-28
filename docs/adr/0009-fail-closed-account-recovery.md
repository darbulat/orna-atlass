# ADR-0009: Account recovery is fail-closed across delivery and browser callbacks

- Status: accepted
- Date: 2026-07-28

## Context

Email verification and password recovery cross several independently failing boundaries: PostgreSQL account state, Redis one-time tokens, SMTP delivery, HTTP cookies, and asynchronous browser navigation. A delivery can succeed while its response is lost, a cancellation can arrive during compensation, and an older browser continuation can settle after a newer authentication flow owns the page. Treating any of those outcomes as definitive success can reactivate an obsolete token or publish authenticated account state after an ambiguous reset.

## Decision

Account verification and recovery use an explicit `prepare → deliver → activate → claim → finalize/rollback` lifecycle. Redis mutations are versioned and idempotent. Activation retries preserve tokens already in a progressed state, while finalized ordering evidence remains for the original token lifetime so an older delivery cannot become active later. PostgreSQL account changes remain service-owned transactions; token finalization follows the durable database outcome, with conservative repair or fail-closed behavior when that outcome is ambiguous.

Cancellation preserves the first observed `CancelledError` across mutation, compensation, and cleanup. Compensation is bounded and its concrete Redis/database operations must cooperate with cancellation so nested tasks are observed and do not outlive the covered auth operation. Ordinary non-cancellation failures remain visible.

An ambiguous terminal password-reset outcome returns an unavailable response, disables caching, expires both authentication cookies, and leaves the browser anonymous. Verification and reset fragments are removed before requests begin and establish one atomic callback owner. Dual-key fragments are rejected. Every asynchronous account-restoration path is guarded by the current authentication generation and callback ownership; browser history or a newer flow invalidates older continuations. Optional-auth infrastructure failure remains distinguishable from a genuinely anonymous request.

Public authentication and user DTOs are explicit allowlists. Backend schemas, generated OpenAPI, frontend types, and API wrappers change together.

## Consequences

Recovery remains unavailable rather than inventing success when Redis, PostgreSQL, delivery, or commit status is uncertain. Users may need to request a new link or sign in again after an ambiguous reset, but stale tokens and authenticated UI cannot be trusted across that boundary. Token tombstones consume bounded Redis storage until their original expiry. Browser auth flows require explicit generation and ownership guards, and concurrency behavior requires real Redis/PostgreSQL plus browser regression coverage.

## Rejected alternatives

- Activating a token before delivery can expose an undelivered credential and makes delivery failure destructive.
- Deleting any token whose activation response is ambiguous can destroy a concurrently claimed or finalized credential.
- Treating an optional-auth outage as anonymous silently weakens protected behavior.
- Using the visible URL alone as callback ownership fails after `history.replaceState()` and same-route browser navigation.
- Allowing each asynchronous callback to restore account state independently permits an older flow to republish private UI.

## Rollback

Disable verification and recovery entry points before removing the lifecycle. Existing token records must be allowed to expire or be invalidated by exact recorded keys; broad Redis-prefix deletion is not permitted. Reverting browser ownership guards requires reverting the matching backend, OpenAPI, and cookie behavior in the same release.
