# ADR-0016: Version billing offers and preserve entitlement provenance

- Status: accepted
- Date: 2026-08-03
- Supersedes: ADR-0011 only where it fixes the production price at USD 10.00; ADR-0013 remains authoritative for template test mode

## Context

The first Bereke checkout implementation fixes one production amount/currency in code and stores only a purchase snapshot. Operators cannot change the production lifetime offer through an audited database mutation. A checkout retry can use a new current price instead of its purchase snapshot, and the single membership row cannot distinguish payment-backed access from administrative or legacy access. Member-only content is also projected inconsistently across direct sessions, collections, search and Atlas.

Provider registration can finish while its response is lost. Replaying such a request is unsafe unless Bereke documents idempotency or authoritative reconciliation for the exact registration path. The template path represents a real KZT charge and does not accept ORNA's merchant reference.

## Decision

The production `lifetime_member` offer is an append-only, versioned PostgreSQL configuration. Amount is a positive integer in minor units and currency is one of the currencies supported by the active Bereke adapter; initially USD and KZT, both represented with two decimal minor units. Exactly one production version is active. One authenticated admin may activate a new version through an audited `If-Match` mutation; dual approval is not required by the current product decision.

Every purchase snapshots offer ID/version, amount and currency before provider registration. Existing purchases use only that immutable snapshot for registration, retry and callback verification. Changing the active offer affects only later purchases.

Any provider registration failure whose outcome cannot be proven pre-acceptance moves the purchase to `provider_outcome_unknown`. ORNA does not automatically register another order until an authoritative reconciliation or explicit audited operator resolution exists. Template test mode remains fixed at KZT 2.00 under ADR-0013 and is not overridden by the production offer table.

Payment-backed access is represented by an entitlement grant linked uniquely to its purchase. Administrative and legacy access remain independent grants. A paid callback activates only the purchase grant; a refund accepts only a payment-backed transition and revokes only that grant. Canonical entitlement is the union of active unexpired grants. Because the pre-migration membership row has no purchase linkage, every existing active membership is independently backfilled as a legacy grant even when paid purchases coexist; purchase grants are additional provenance and are never used to guess ownership of that legacy state.

Every entitlement-varying catalog projection uses the canonical policy. Membership exposes published, non-archived, publicly discoverable `members_only` recordings; it never exposes private, draft, archived, hidden-location or unready playback data.

Self-service full-refund requests are accepted through 14 calendar days after `paid_at`; later exceptions require a separate audited support/admin operation. Bereke callback bodies and fields are bounded in the application as well as at ingress.

The schema cutover remains compatible with callback writers from the previous release. Revision 0018 leaves legacy `creating` rows unchanged; the new checkout service lazily quarantines such a row before any possible repeat provider call. Revision 0019 takes a bounded writer lock while atomically installing a compatibility trigger and backfilling grants. Until all old writers are gone, that trigger mirrors paid/refund purchase state into the purchase-scoped grant, closing the point-in-time backfill gap without changing independent legacy/admin grants.

## Consequences

Pricing changes require a new offer row rather than mutation of purchase history. Schema, OpenAPI and frontend validation must accept configured supported values instead of exact hardcoded pairs. Price activation and checkout creation need row locking/concurrency tests. Ambiguous provider outcomes may require operator reconciliation and can reduce checkout availability, but cannot silently create duplicate real charges.

Entitlement migration and reads become more explicit but refunds can no longer cancel unrelated access. Public and member catalog responses must use separate no-store/private behavior or authorization-class-safe caching. ADR-0011 continues to govern hosted checkout, verified callbacks and fiscal rollout; ADR-0013 continues to govern the fixed template test mode.