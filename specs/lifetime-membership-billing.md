# Spec: Lifetime membership billing

- Status: implemented
- Owner: backend/frontend
- Last updated: 2026-07-30
- Related issue/PR: direct user request
- Related ADRs: `../docs/adr/0011-bereke-hosted-checkout.md`

## Problem and outcome

ORNA exposes membership entitlements but currently states that pricing and checkout are unavailable.
Offer one truthful digital product: Lifetime Member Access for a single USD 10.00 payment, with no
renewal or expiry, through Bereke Bank's hosted checkout.

## Context and evidence

- Current-state section: authentication and membership; public legal information.
- Domain rules/invariants: membership entitlement and service-owned transaction rules.
- Relevant code: membership service, account page, generated API contract.

## Scope

### In scope

- Public offer and legal/support disclosures.
- Authenticated checkout creation, purchase status/history, refund request, and verified callback.
- Lifetime membership activation after confirmed payment.
- An explicit KZT 2.00 hosted-template test mode while authenticated merchant API access is pending.

### Non-goals

- Recurring billing, physical delivery, card-data handling, partial refunds, or multiple products.

## Design and boundaries

Billing follows router -> service -> repository -> model. Provider HTTP and signature details stay in
the Bereke integration adapter. A local pending purchase is committed before the external checkout
request. A later verified callback atomically records the terminal payment and activates membership.

## Contract and data changes

Add the public offer endpoint and authenticated checkout, purchase, refund-request endpoints. Add a
provider callback. Persist purchases, callback event identifiers, and refund requests. Regenerate the
OpenAPI and TypeScript contracts.

## Security, privacy and failure behavior

The server owns price and currency. Checkout requires an active account with a verified email.
Callback signatures, event replay, order identity, amount and currency are verified. Raw provider
payloads, checkout URLs and wallet credentials are not logged or stored as public metadata. Provider
outage never grants access.

## Acceptance scenarios

1. A verified free user receives a Bereke hosted URL for exactly USD 10.00.
2. An unsigned, duplicate, mismatched or failed callback does not activate membership.
3. A verified paid callback activates lifetime membership exactly once.
4. A confirmed full refund revokes payment-backed access unless another valid entitlement exists.
5. Public pages show product, operator, support, refund and no-renewal information in English.
6. Test mode truthfully displays KZT 2.00, creates one provider order per purchase, and never presents
   itself as production USD checkout.

## Verification plan

- Backend service, signature, schema and OpenAPI tests.
- Disposable PostgreSQL migration/concurrency checks.
- Frontend typecheck, lint, build and Playwright membership journey.
- Bereke sandbox validation remains required before enabling production checkout.
- The Kazakhstan online cash-register/fiscal receipt flow must be contracted, integrated and tested
  before accepting production payments.

## Rollout, rollback and observability

Deploy schema and callback first with billing disabled. Enable only after sandbox verification, a
working support mailbox and an operational online cash-register/fiscal receipt flow. Rollback
disables new checkout but keeps callbacks, purchase records and refunds.
Metrics use bounded statuses without user or provider secrets.

## Documentation and decisions

Update domain rules, current state, UX funnel, Terms, Privacy, refund and support pages.

## Open questions

None. The exact Bereke wire mapping is supplied by the merchant onboarding package and must match the
adapter contract before billing is enabled.
