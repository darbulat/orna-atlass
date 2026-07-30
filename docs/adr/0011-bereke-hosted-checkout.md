# ADR-0011: Bereke hosted checkout for lifetime membership

- Status: accepted
- Date: 2026-07-30

## Context

ORNA needs a one-time USD 10.00 lifetime membership purchase. Handling card or Google Pay credentials
directly would expand PCI scope, while Bereke Bank offers a hosted internet-acquiring checkout.

## Decision

ORNA creates an immutable local purchase reference and redirects to Bereke's hosted checkout. Only a
verified server callback with matching order, amount and currency may activate membership. Browser
return parameters are informational. Provider-specific transport stays behind an integration adapter.

Refund requests originate in ORNA, while completion remains provider-authoritative. New checkout can
be disabled independently without disabling callback and reconciliation handling.

## Consequences

ORNA does not store payment credentials and cannot fabricate success during provider failure. Checkout
requires Bereke merchant configuration, sandbox approval and a separately verified online
cash-register/fiscal receipt flow. The database retains purchase and event history for idempotency
and support; its purchase record is not represented as a fiscal receipt.
