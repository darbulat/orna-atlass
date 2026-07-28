# ADR-0010: OAuth identities link only after exact-account reauthentication and explicit confirmation

- Status: accepted
- Date: 2026-07-28

## Context

A verified OAuth identity can report an email that already belongs to an ORNA account. Email equality is not proof that the provider subject and the existing account have the same owner, so automatically merging them would permit account takeover. Rejecting the callback permanently is safe but gives the legitimate owner no recovery path. A recovery flow crosses the provider callback, Redis, browser cookies, PostgreSQL identity uniqueness, existing password or magic-link authentication, and asynchronous browser state.

## Decision

ORNA never links OAuth identities by matching email alone. A verified same-email conflict creates a short-lived, opaque linking intent bound to the exact existing account, provider and immutable provider subject. The raw intent exists only in a narrowly scoped `HttpOnly`, `SameSite=Lax` browser cookie; Redis records use a digest-derived key, bounded payload and fixed expiry. Raw intents, provider subjects, authorization codes and provider tokens never enter public DTOs, redirects, analytics or logs.

The user must authenticate the exact target account after the conflict. Refreshing or presenting an older session, authenticating another account, or registering a new account does not satisfy this boundary. Password, a target-bound magic link, or a different already-linked provider may perform the reauthentication; the provider currently being linked is suppressed as an authentication option.

Reauthentication only marks the intent ready. Creating the identity requires a separate same-origin POST with explicit confirmation. The auth service owns the database transaction, repositories only query or flush, and existing uniqueness constraints remain authoritative. A provider subject is never moved between users. Concurrent inserts are reconciled only when the database winner is the same requested `(user, provider, subject)` association; every other race fails closed.

Intents are single-use. Stale, malformed, expired, wrong-user and ambiguous infrastructure or commit outcomes return conservative errors, clear browser authority where appropriate, and never invent successful linking. Frontend continuations are guarded by the current authentication/linking generation so stale pending, confirm or cancel responses cannot publish account state.

## Consequences

Legitimate users can recover from a same-email OAuth conflict, but linking requires an extra authentication and confirmation step. Redis holds bounded intent state until consumption or expiry. Backend schemas, OpenAPI, generated clients and browser state must change together. The flow requires unit coverage for denial and race behavior, disposable PostgreSQL/Redis integration coverage for uniqueness and single-use semantics, and browser coverage for resumability, explicit confirmation, cancellation and stale-response ownership.

## Rejected alternatives

- Automatically linking verified accounts by email treats an assertion about contactability as account ownership.
- Treating an existing or refreshed session as reauthentication allows ambient browser state to authorize a new sign-in method.
- Linking immediately after password, magic-link or provider authentication removes the user's explicit confirmation boundary.
- Storing raw intents in Redis keys, URLs, browser-visible storage or public responses expands bearer-secret exposure.
- Moving a provider subject between users or treating every uniqueness race as success can transfer identity ownership.

## Rollback

Disable creation and confirmation of new linking intents before removing the endpoints or browser UI. Existing Redis intents must be allowed to expire or be removed only by their exact digest-derived keys; broad prefix deletion is forbidden. Revert backend routes, service behavior, OpenAPI/generated clients and membership UI together. Existing successfully linked identities remain authoritative account credentials and must not be detached automatically.
