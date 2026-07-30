# ORNA Atlas domain rules

These rules are the review baseline for code and tests. Rows marked “decision required” describe conservative behavior until the product owner confirms a different policy.

## Public coordinates

| Visibility | Public latitude/longitude | Exact coordinates | Public lists/details |
|---|---|---|---|
| `exact` | Exact values | Allowed | Allowed when the location itself is public. |
| `approximate` / legacy `public_only` | Stable approximate projection | Never | Allowed when the location itself is public. |
| `hidden` | `null` or omitted | Never | Location must not become discoverable through nested collections/sessions. |

Admin DTOs may contain exact values after authorization. Public DTOs must be constructed explicitly and must not serialize ORM objects directly. A collection cannot be used to bypass a location’s visibility.

## Session publication and playback

Publication, access and processing are independent facts:

Publication uses `draft`, `published` and `archived`; access uses `public`, `members_only` and `private`; processing reports pipeline readiness independently. Public queries require `publication_status=published` before applying caller access policy.

| Published/public | Access permits caller | Ready playable rendition exists | Public detail | Playback grant |
|---:|---:|---:|---:|---:|
| No | any | any | No | No |
| Yes | No | any | Policy-dependent summary only | No |
| Yes | Yes | No | Yes, with unavailable state | No; return a typed conflict/unavailable error |
| Yes | Yes | Yes | Yes | Yes, short-lived URL |

Mock silence is development fixture behavior, not a successful production fallback. A storage timeout or missing object must not be reported as playable.

Membership entitlement is active only when `status=active` and `expires_at` is absent or in the future. Public sessions may issue anonymous grants; `members_only` sessions require an active entitlement. Editor and admin roles may inspect protected playback for editorial operations. Every successful grant creates an audit event; denied requests never create a success event.

Lifetime Member Access is a digital entitlement sold for one non-recurring USD 10.00 payment. The
server owns the product, amount and currency. A browser return, client assertion or unverified provider
message never grants access: only an idempotently processed Bereke confirmation whose merchant
reference, provider order, amount and currency match the recorded purchase may activate lifetime
membership with no expiry. A provider-confirmed refund revokes payment-backed access unless another
valid entitlement remains.

An explicitly configured billing test mode may replace the production offer with the fixed Bereke
template price of KZT 2.00. Test mode must be visible to the buyer, must create a distinct provider
order for every local purchase, and matches callbacks by their signed provider order identifier.
It is not evidence that the production USD offer or authenticated Bereke API is ready.

Entitled members can discover and render `members_only` session list/detail records through the
authenticated session endpoints. Anonymous and non-entitled callers receive the public projection
only; protected records are reported as not found.

## Authentication and roles

- Access tokens are short-lived and may arrive through a Bearer header or httpOnly cookie.
- Refresh tokens are stored only as hashes, rotated on use, and revoked on logout.
- An external identity is identified by `provider + subject`; matching email is discovery evidence,
  not proof that an identity belongs to an existing ORNA account. An OAuth email conflict creates a
  short-lived, opaque, server-side intent addressed by a token digest. Linking requires a new
  authentication of the recorded target account after the conflict and a separate explicit
  confirmation. The intent is single-use on confirmation or cancellation, browser-supplied email,
  user ID and provider subject are never trusted, and an identity linked to another user is never
  moved. Magic-link reauthentication during this flow is login-only and remains bound to the
  recorded target user even if the account is deleted before consumption.
- Password-account mailbox verification and password recovery use opaque, bounded-lifetime,
  single-use tokens. Public recovery responses never disclose account existence, active state or
  sign-in method, and raw tokens never appear in URL query strings or logs. Token activation occurs
  only after successful delivery; confirmation claims a token before the database transition. A
  known pre-commit failure releases the claim, while an ambiguous `COMMIT` result burns it fail-closed.
  A bounded finalized-version tombstone prevents delayed older deliveries from reactivating after a
  newer token was used. Mutating Redis transitions are idempotent for the exact token and claim
  identity so an unknown transport outcome can be retried without widening replay access. An
  activation retry never deletes a token that has already advanced to claimed or finalized, even
  when confirmation advances concurrently between attempts. If cancellation is recorded after a
  successful claim, compensating rollback is best-effort: its failure leaves the claim fail-closed
  but never replaces the original task cancellation with a live service error. Repeated
  cancellation while PostgreSQL rollback and token finalization/rollback are running cannot
  interrupt those bounded compensations or replace the first recorded cancellation. The first
  cancellation is retained across repeated Redis-operation cancellation, including client-close
  cleanup after the mutation has settled, and cancellation-only compensation has an internal
  two-second deadline; an unfinished child is cancelled and observed without indefinitely retaining
  the request task. These rules apply to both verification and reset.
- Password reset revalidates the active password account, replaces its password hash, revokes all
  refresh sessions and does not create a replacement session. Existing access tokens expire at
  their normal short TTL, and the confirming browser's auth cookies are cleared. A commit-unknown
  response also expires both HttpOnly auth cookies before returning, so reload cannot restore a
  possibly revoked session; only a definitive sanitized invalid-token `400` preserves them. Recovery
  request loading and error state is scoped to its navigation generation, so leaving the recovery
  route invalidates delayed continuations. Browser-history exit from a consumed reset fragment also
  invalidates any pending confirmation and clears the reset token, busy state and local account view.
  Entering a verification or reset fragment is also an ownership boundary: prior callback ownership
  and sensitive reset fields are discarded before selecting exactly one new owner, and a fragment
  containing both recognized token keys is rejected without confirmation requests. Earlier
  password-login, magic-link and verification-delivery continuations cannot publish state or retain
  control of the destination action's busy indicator; abandoning an in-flight reset for a new
  callback also clears authenticated UI because the earlier reset outcome can become unknown.
- Email verification status does not itself grant membership and does not block login unless a
  separately accepted product policy introduces that restriction.
- Editors do not inherit admin publication or user-management permissions.
- The local admin header is a development-only escape hatch and is invalid production configuration.
- The first production admin is promoted from an existing active account by the one-time,
  transaction-locked bootstrap command. Once an admin exists, all role changes require admin auth.


## Processing jobs

- At most one active processing job exists for an asset revision and job type.
- A rendition becomes `ready` only after its object was uploaded and existence was verified.
- Retry is idempotent and cannot activate output for an obsolete master revision.
- A failed attempt does not destroy the last successful analysis/rendition.
- Source and rendition object keys are immutable per revision/attempt. Only an archived, inactive asset may be purged.
- Admin-provided storage keys must remain inside the managed relative `sessions/` namespace; absolute paths and arbitrary S3 buckets are rejected.
- Services own transaction boundaries; repositories flush/query but do not commit independently.

## Segmented recordings and HLS

- Segment sequence numbers are contiguous and each segment remains linked to one immutable source asset.
- Timeline offsets derive from ordered ffprobe durations; BirdNET intervals are source-local until translated by that offset.
- A session HLS build is unique for its ordered source-set fingerprint and processes no more than one WAV at a time.
- Every init and media fragment must be uploaded and verified before the final manifest is published and the rendition activated.
- A private HLS request must have a valid rendition-scoped grant and name an object in the rendition's verified inventory.
- Cleanup deletes only the recorded inventory. Prefix-wide deletion is forbidden.

## Time and dawn

- Timezone values are valid IANA names; invalid values are rejected, never silently coerced to UTC.
- Stored timestamps are timezone-aware and normalized consistently.
- Dawn state derives from the location, date and timezone. The UI must not invent a fallback time.
- Polar day/night is a valid explicit state, not an error.

## Repeated and concurrent actions

- Repeated create/process requests use an idempotency key or return the existing active operation.
- Cache invalidation occurs after the database transaction commits.
- A retry after partial S3/database failure must converge to one consistent active result.
