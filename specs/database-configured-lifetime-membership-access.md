# Spec: Database-configured lifetime membership and complete member catalog access

- Status: accepted
- Owner: backend/frontend/security
- Last updated: 2026-08-03
- Related issue/PR: direct user request and payment/membership review
- Related ADRs: `../docs/adr/0011-bereke-hosted-checkout.md`, `../docs/adr/0013-bereke-template-test-mode.md`, `../docs/adr/0016-database-billing-offers-and-entitlement-grants.md`

## Problem and outcome

The implemented lifetime membership offer hardcodes production USD 10.00 and test KZT 2.00 values in application and frontend code. The database stores only a price snapshot on each purchase and is not the authoritative source for the active production offer. Retrying an unfinished purchase can send the current configured price to Bereke rather than the immutable price recorded on that purchase.

A confirmed lifetime payment activates membership for direct session list/detail/playback and account-library flows, but members-only recordings remain absent or visually locked in collections, search, Atlas navigation and Popular Locations. Refund processing can also revoke an unrelated entitlement because membership provenance is not represented.

The outcome is one non-recurring lifetime product whose active production amount and provider-supported currency are configured and versioned in PostgreSQL, whose purchase snapshot remains immutable, and whose verified payment unlocks every eligible members-only recording consistently across discovery, detail, playback and library surfaces.

## Context and evidence

- Current-state section: `../docs/CURRENT_STATE.md` — Lifetime membership billing, Authentication and membership, Playback, Account library and Frontend tests.
- Domain rules/invariants: `../docs/DOMAIN_RULES.md` — server-owned billing values, verified callbacks, payment-backed revocation and member discovery.
- Billing entry points: `../orna_atlas/app/modules/billing/{models,repository,schemas,service,router}.py`, `../orna_atlas/app/integrations/bereke.py`.
- Entitlement entry points: `../orna_atlas/app/modules/memberships/`, `../orna_atlas/app/modules/sessions/`, `../orna_atlas/app/modules/library/`, `../orna_atlas/app/modules/collections/`, `../orna_atlas/app/modules/atlas/`.
- Frontend entry points: `../web/lib/api/billing.ts`, `../web/lib/api/sessions.ts`, `../web/lib/api/collections.ts`, `../web/components/atlas/AtlasExplorer.tsx`, `../web/components/popular-locations.tsx`, `../web/components/membership-billing-panel.tsx`.
- Existing focused checks are green but encode fixed prices and do not prove callback-to-full-catalog access.

## Scope

### In scope

- A versioned PostgreSQL configuration for the active `lifetime_member` production offer.
- Positive integer `amount_minor` and an ISO 4217 currency supported by the active Bereke adapter.
- Exactly one active production offer version per product; safe audited admin read/update with optimistic concurrency.
- Atomic selection of the active offer and immutable price/currency/offer-version snapshot on each new purchase.
- Retry and callback behavior that always uses and verifies the purchase snapshot.
- Explicit fail-closed handling for an ambiguous provider result; no automatic retry when duplicate real charges are possible.
- Entitlement grants with provenance so a refund revokes only the grant created by its purchase.
- Entitlement-aware sessions, collections, search, Atlas, Popular Locations and account-library behavior.
- Account-aware/no-store caching wherever a response differs by entitlement.
- Enforcement of the published 14-calendar-day self-service refund window.
- A bounded Bereke callback body and parameter contract.
- Migration, OpenAPI/generated TypeScript, backend/frontend tests, browser acceptance and documentation reconciliation.

### Non-goals

- Recurring subscriptions, renewals, expiry-based paid plans or multiple sellable products.
- Unlocking draft, archived, private, hidden-location, unpublished, unready or missing-media recordings.
- Supporting currencies Bereke cannot register or authoritatively reconcile.
- Changing the bank-issued template test price. Test mode remains an explicitly labelled real KZT template charge and is not the database-configured production offer.
- Partial refunds, direct card handling, fabricated provider success or unaudited direct production SQL as the normal pricing workflow.

## Design and boundaries

Billing remains `router -> service -> repository -> model`; Bereke transport remains in the integration adapter. Add a versioned billing-offer model and repository. The billing service owns offer activation and checkout transactions. Admin routes call the billing service and never write the offer table directly.

A new checkout transaction locks or otherwise serializes the active offer selection, creates the purchase with `offer_id`/`offer_version`, `amount_minor` and `currency`, and commits that immutable local reference before calling Bereke. Existing purchases always call Bereke with their stored snapshot. A price change affects only purchases created after activation of the new version.

Normal Bereke registration may retry only under a demonstrated provider idempotency contract using the stable merchant reference. Template registration must enter a `provider_outcome_unknown` state after an ambiguous result unless Bereke supplies a safe reconciliation/idempotency mechanism. It must not create a second hosted order automatically.

Replace the single provenance-free paid membership mutation with entitlement grants. A verified paid callback idempotently creates or activates the grant linked to its purchase. A verified full refund revokes only that grant. Canonical membership entitlement is true when at least one valid grant or accepted administrative entitlement remains.

Member catalog projections use the canonical entitlement policy. Eligible means published, non-archived, publicly discoverable and otherwise safe under the existing privacy rules. Playback additionally requires a ready verified rendition and remains fail-closed.

## Contract and data changes

- Add `billing_offers` with immutable version rows, product code, amount, currency, active/effective state, revision and timestamps.
- Add a database constraint/index proving only one active production offer for `lifetime_member`.
- Add purchase references to the selected offer/version while retaining immutable `amount_minor` and `currency` for historical verification.
- Add entitlement-grant storage with source type, source ID, status, start/end/revocation timestamps and uniqueness for a billing purchase.
- Add a purchase state for ambiguous provider outcome if reconciliation cannot resolve it synchronously.
- Add admin billing-offer read/update contracts with required `If-Match`; emit an audit event containing bounded changed-field metadata, never credentials or checkout URLs.
- Keep public `BillingOfferRead.amount_minor` and `currency`, but remove frontend checks for exact hardcoded pairs. Runtime validation requires the correct product, non-recurring flag, positive integer amount and a supported currency.
- Make collections and search optionally authenticated. Entitled responses include eligible `members_only` records; anonymous/free responses retain the public projection.
- Supply an explicit entitlement/access presentation signal to Atlas/Popular Locations or otherwise derive it from validated account state without treating `access_level=members_only` as always locked.
- Regenerate `web/openapi.json` and `web/lib/api/generated.ts`.
- Provide reversible Alembic migrations and deterministic backfill for existing lifetime memberships/purchases. Ambiguous provenance must be preserved conservatively rather than guessed.

## Security, privacy and failure behavior

- The server and database own product price/currency; browser-supplied values are never trusted.
- A callback grants access only after signature, provider order, merchant reference, amount, currency and terminal status match the immutable purchase snapshot.
- Price updates cannot mutate historical purchases or already-created hosted orders.
- Provider outage or ambiguous registration never grants access and never triggers an unsafe duplicate-charge retry.
- Refund callbacks accept only valid payment-backed state transitions and revoke only the purchase-linked grant.
- Hidden locations, sensitive coordinates, private/draft/archived records and unready media remain undiscoverable or unplayable after membership.
- Entitlement-varying responses must not share public cache entries. Use no-store/private behavior or keys that safely bind the response to the authorization class without user data in labels.
- Bereke callback request body, parameter count and field lengths are bounded before expensive parsing/provider lookup. Gateway limits supplement rather than replace the application limit.
- Pricing/admin mutations require active admin authorization, row locking/optimistic concurrency and audit events.
- Secrets, raw callback bodies, provider credentials and checkout URLs are not logged in public or audit metadata.

## Acceptance scenarios

1. Given an active DB offer, an anonymous buyer sees exactly its amount/currency from `/billing/offer`.
2. Given a verified eligible user, checkout snapshots the currently active DB offer and sends that exact snapshot to Bereke.
3. Given purchase A and a later price change, retry/callback for A still use A's original amount/currency; purchase B uses the new offer.
4. Given a stale admin revision or two concurrent price updates, only one succeeds and exactly one active offer remains.
5. Given an ambiguous template registration or a pre-migration purchase left in the old `creating` state, the purchase is quarantined as safely reconcilable and no automatic second provider order is created.
6. Given an unsigned, duplicate, mismatched, failed or infrastructure-ambiguous callback, no entitlement grant is activated.
7. Given a verified paid callback, one lifetime billing grant is active with no expiry and duplicate callbacks create neither a second grant nor a second activation.
8. Given an entitled member, every eligible members-only recording is present in sessions, search and collections, appears unlocked in Atlas/Popular Locations, resolves by detail, receives a playback grant when rendition-ready, and is usable in favorites/history.
9. Given an anonymous or free account, members-only detail remains not found/denied according to the existing contract and playback remains unavailable.
10. Given an entitled member, draft, archived, private, hidden-location and unready recordings remain excluded or fail closed.
11. Given a verified full refund within the valid lifecycle, only the grant linked to that purchase is revoked; another paid/admin grant preserves access.
12. Given a new self-service refund request after 14 calendar days, the API returns a typed conflict; retrying a request accepted within the window returns that existing request, while an explicitly authorized support/admin path remains separate and audited.
13. Given an oversized or over-parameterized callback request, the application rejects it before full unbounded buffering or provider lookup.
14. Given payment completion in the browser, membership state and entitlement-varying catalog data refresh without stale locks or a public cache leak.

## Verification plan

- Narrow regression tests: offer repository/service, purchase snapshot across price change, creating/ambiguous retries, callback transitions, provenance-aware refund, 14-day boundary and callback request bounds.
- Backend unit/contract checks: `python -m pytest orna_atlas/app/tests/test_billing.py orna_atlas/app/tests/test_sprint8_auth_membership.py orna_atlas/app/tests/test_account_library.py` plus new collection/search entitlement tests.
- Disposable dependency/integration checks: migration cycle, unique active offer under concurrency, checkout locking, callback/grant idempotency and paid/refund transitions using disposable PostgreSQL.
- Frontend checks: `cd web && npm run api:check && npm run test:unit && npm run typecheck && npm run lint && npm run build`.
- Browser checks: callback/payment-return fixture followed by unlocked Atlas/search/collection/detail/playback/library journey; free and refunded negative journeys; mobile/keyboard/accessibility states.
- Full local checks: `python -m pytest`, `python -m ruff check .`, frontend required suite.
- Integration checks: `RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration` and `cd web && npm run test:e2e` with disposable dependencies.
- Migration checks: inspect the disposable target, then `alembic upgrade head`, `alembic check`, repository migration-cycle command and explicit downgrade/upgrade verification.

## Rollout, rollback and observability

1. Add/backfill offer and entitlement-grant schema while old reads and callback writers remain compatible: preserve legacy `creating` rows for lazy fail-closed quarantine, and install the purchase/grant compatibility trigger under a writer lock before completing the grant backfill.
2. Deploy callback/grant and purchase-snapshot logic with new checkout disabled; retain the compatibility trigger while any previous callback process may still run.
3. Backfill every existing active membership conservatively as an independent legacy grant, because the old row cannot prove payment ownership; separately backfill eligible paid purchases as payment grants and verify paid/refunded purchase-grant reconciliation.
4. Activate entitlement-aware reads and account-safe cache behavior.
5. Configure one active production offer through the audited admin path.
6. Run sandbox/reconciliation, fiscal-receipt and complete member-journey smoke checks before enabling checkout.

Rollback may disable new checkout and retain callbacks/reconciliation. It must not drop offer, purchase, event or grant history. A migration downgrade must fail clearly when data cannot be represented safely. Metrics use bounded labels for offer-version activation, checkout state, callback outcome, reconciliation need and entitlement-grant outcome; no user IDs, prices as unbounded labels, secrets or provider payloads.

## Documentation and decisions

- Add a superseding ADR for DB-authoritative versioned pricing, immutable purchase snapshots, ambiguous-provider behavior and entitlement provenance; do not rewrite accepted ADR rationale.
- Update `../docs/DOMAIN_RULES.md` with DB-owned active offer and grant-based revocation rules.
- Update `../docs/CURRENT_STATE.md` only after migration/contracts/tests prove the behavior.
- Update `../docs/UX_FUNNEL_SPEC_RU.md`, Terms/refund/support disclosures and operational rollout documentation.
- Mark the earlier fixed-price spec superseded only after this spec is accepted; until then it remains evidence of current implemented behavior.

## Open questions

None for implementation. ADR-0016 fixes the initial supported currencies/minor-unit policy, fail-closed ambiguous-provider behavior, 14-day self-service refund window, single-admin optimistic mutation and conservative legacy-grant backfill. A future provider reconciliation API or dual-approval policy requires a separate accepted change.

## Implementation handoff

Primary owner: backend for offer/purchase/grant models, migrations, transactions and Bereke failure handling. Frontend owns generated contracts, entitlement-aware transport/cache behavior and truthful unlocked UI. Security reviews callbacks, admin pricing mutations, provenance, privacy and cache separation. Test owns migration/concurrency, provider ambiguity and complete callback-to-catalog acceptance evidence. Documentation owns the superseding ADR and reconciliation of domain/current-state/legal text.

Implementation order is schema and failing tests, offer/admin flow, immutable checkout snapshot and provider ambiguity handling, grant provenance/refunds, entitlement-aware read surfaces, frontend unlocked states, full integration/browser verification, then documentation and rollout.