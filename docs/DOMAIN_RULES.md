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

Entitled members can discover and render `members_only` session list/detail records through the
authenticated session endpoints. Anonymous and non-entitled callers receive the public projection
only; protected records are reported as not found.

## Authentication and roles

- Access tokens are short-lived and may arrive through a Bearer header or httpOnly cookie.
- Refresh tokens are stored only as hashes, rotated on use, and revoked on logout.
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

## Time and dawn

- Timezone values are valid IANA names; invalid values are rejected, never silently coerced to UTC.
- Stored timestamps are timezone-aware and normalized consistently.
- Dawn state derives from the location, date and timezone. The UI must not invent a fallback time.
- Polar day/night is a valid explicit state, not an error.

## Repeated and concurrent actions

- Repeated create/process requests use an idempotency key or return the existing active operation.
- Cache invalidation occurs after the database transaction commits.
- A retry after partial S3/database failure must converge to one consistent active result.
