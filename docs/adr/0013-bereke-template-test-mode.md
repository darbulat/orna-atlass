# ADR-0013: Isolate Bereke template checkout as an explicit test mode

- Status: accepted
- Date: 2026-07-30

## Context

ADR-0011 fixes the production Lifetime Member Access contract at one USD 10.00 hosted Bereke
payment whose final state is independently verified through the authenticated merchant API. The
available merchant credential cannot currently register that order, while a bank-issued payment
template can register hosted orders at a fixed KZT 2.00 amount for pre-production validation.

Template registration generates a unique provider order and accepts an e-mail address, but it does
not accept ORNA's merchant reference or provide the authenticated order-status lookup used by the
normal adapter. The bank portal identifies the merchant environment as production, so a template
payment is a real KZT 2.00 charge even when ORNA treats the rollout as a test.

## Decision

ORNA may use the fixed template only behind the explicit conjunction of `BILLING_ENABLED=true` and
`BILLING_TEST_MODE=true`. Test mode publishes KZT 2.00 as the active offer, labels it as a test
checkout, registers a new provider order for each local purchase, and reconciles a symmetrically
signed callback against the provider order ID saved on that purchase.

Normal mode continues to use the USD 10.00 production contract, merchant credentials and independent
provider status verification required by ADR-0011. A template ID alone never enables checkout, test
mode never falls back to normal mode, and neither mode may infer payment success from the browser
return. Moving the template path to production requires a new decision and a bank-supported
authoritative status or reconciliation contract.

## Consequences

The test rollout can exercise hosted checkout, callback idempotency, entitlement activation and the
member journey without silently weakening the production path. Purchase records must support both
USD and KZT, while each record remains immutable in amount and currency and callbacks must match it
exactly.

Template callbacks have weaker independent verification than normal callbacks: integrity depends on
the configured symmetric callback secret and the saved provider order ID. Operators must therefore
keep test mode explicit, protect the callback secret, disclose the real KZT 2.00 charge, and disable
the mode after validation. This mode is not evidence that fiscal receipt operations or production
merchant onboarding are complete.
