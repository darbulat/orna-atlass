# Change specifications

Specs turn an ambiguous change into reviewable scope and acceptance behavior. They are repository
context, not runtime truth: a capability becomes current only after code, migrations/contracts and
tests support it and `docs/CURRENT_STATE.md` is reconciled.

## When to write one

Create a spec from [`TEMPLATE.md`](TEMPLATE.md) when a change:

- crosses backend/frontend/worker or several domain modules;
- changes a public contract, schema, privacy/access rule or data lifecycle;
- needs rollout, migration, compatibility or rollback design;
- has several plausible interpretations or acceptance paths;
- will be split across contributors or specialist roles.

Routine bug fixes and isolated refactors can keep acceptance notes in the issue or PR. Do not create
a spec merely to restate code.

## Lifecycle

Use one of these statuses at the top of each spec: `draft`, `accepted`, `implemented`,
`superseded`, or `rejected`.

1. Copy the template to a descriptive, lowercase, hyphenated filename.
2. Link relevant current-state sections, domain rules and ADRs; verify code references.
3. Resolve material open questions and obtain review before marking it `accepted`.
4. Keep acceptance scenarios stable while implementing. Record intentional scope changes.
5. Mark `implemented` only when the listed evidence passes and authoritative docs are current.
6. Keep superseded/rejected specs for rationale, linking their replacement where applicable.

Do not edit a spec to conceal implementation drift. Describe the deviation and review the changed
decision.

## Index

- [`admin-workspace-v1.md`](admin-workspace-v1.md) — draft admin-only workspace for editorial
  browsing/mutations, processing operations, audit review and separately gated account management.
- [`oauth-account-linking.md`](oauth-account-linking.md) — accepted explicit linking flow after a
  verified OAuth email conflicts with an existing account.
- [`lifetime-membership-billing.md`](lifetime-membership-billing.md) — implemented one-time USD
  10.00 lifetime membership through Bereke hosted checkout.
- [`database-configured-lifetime-membership-access.md`](database-configured-lifetime-membership-access.md)
  — accepted replacement contract for database-configured lifetime pricing, immutable purchase
  snapshots, provenance-safe refunds and complete eligible member-catalog access.
- [`profile-billing-mobile-ux.md`](profile-billing-mobile-ux.md) — accepted responsive paid-purchase
  summary, localized payment facts, explicit test-mode treatment and confirmed secondary refund flow.

`TEMPLATE.md` is scaffolding and does not describe an implemented or accepted feature.
