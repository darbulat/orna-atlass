# Spec: Responsive post-purchase profile billing UX

- Status: implemented
- Owner: frontend
- Last updated: 2026-08-04
- Related issue/PR: [#78](https://github.com/darbulat/orna-atlass/pull/78)
- Related ADRs: `../docs/adr/0011-bereke-hosted-checkout.md`

## Problem and outcome

The authenticated `/membership` profile renders the lifetime-purchase panel as a sales card even
after payment. In the user-supplied narrow-screen screenshot, the paid purchase's unbroken merchant
reference expands the billing grid beyond the viewport. The account page hides overflow, so the
heading, explanatory copy, order value and refund action are visibly clipped rather than reflowed.
The paid state also gives the destructive refund action the strongest visual emphasis, uses an
ambiguous English numeric date, retains pre-checkout disclosure language, and exposes an internal-
sounding `Test checkout price` label without presenting test mode as an environment-level state.

The outcome is a responsive, accessible purchase summary that keeps every visible and interactive
billing element inside narrow viewports, makes active lifetime access and payment facts the primary
information, preserves truthful test-mode disclosure, and makes a full refund an explicit confirmed
secondary action.

## Context and evidence

- Current-state section: `../docs/CURRENT_STATE.md` — Lifetime membership billing; Authentication
  and membership.
- Domain rules/invariants: `../docs/DOMAIN_RULES.md` — purchase-confirmed lifetime grants,
  provider-confirmed refund behavior, the 14-calendar-day self-service refund window, and mandatory
  buyer-visible billing test mode.
- Relevant code and contract entry points:
  - `web/app/membership/page.tsx` composes the authenticated account dashboard and billing panel.
  - `web/components/membership-billing-panel.tsx` renders offer, purchase, refund and disclosure
    states.
  - `web/app/styles.css` owns `.account-page`, `.billing-panel` and `.billing-purchase-card` layout.
  - `web/lib/api/billing.ts` consumes generated `BillingOfferRead`, `PurchaseRead` and
    `RefundRequestRead` types.
  - `web/e2e/auth.spec.ts` covers the authenticated account route and payment states.
- Existing evidence:
  - `.account-page` uses `overflow: hidden`, which can conceal descendants wider than the viewport.
  - the mobile billing grid becomes `1fr`, while the paid merchant reference has no bounded display
    or forced wrapping;
  - the current mobile geometry canary exercises the unpaid/checkout-unavailable fixture, not a paid
    purchase with a maximum-length merchant reference;
  - the paid card keeps default paragraph margins in addition to grid gap, producing excessive
    vertical separation.

## Scope

### In scope

- Make the complete authenticated account and billing layout reflow without hidden clipping at
  viewport widths of 320 px and 390 px, including a maximum-length merchant reference and browser
  text enlargement.
- Ensure the billing panel, purchase card, text, links and controls have bounded grid/flex sizing;
  long user-visible values must wrap or use a deliberately shortened display form.
- Replace the paid-state sales treatment with a compact purchase summary whose primary outcome is
  active lifetime access.
- Show the immutable purchase amount/currency, unambiguous localized payment date, and a shortened
  merchant reference with a keyboard-accessible copy action. Keep post-purchase and refund-status
  copy provider-neutral; name Bereke Bank only at the external checkout handoff and in legal or
  support information where identifying the processor is relevant.
- Keep the full merchant reference available to copy and to assistive technology without exposing it
  as an unbroken layout constraint.
- Remove redundant sales copy from the paid state. Preserve no-renewal and digital-purchase copy in
  the pre-checkout state where it informs the decision.
- Replace the internal-sounding `Test checkout price` line with an explicit buyer-facing `Test
  payment mode` treatment only when the configured fixed KZT 2.00 test offer is active. It must not
  appear for a production offer and must not imply that test payment proves production readiness.
- Reduce paid-card vertical whitespace by normalizing paragraph/list margins and using a compact,
  consistently aligned definition-list treatment.
- Render refund as a secondary/destructive action, disclose the 14-calendar-day self-service window,
  and require an explicit second-step confirmation that names the full refund and resulting access
  consequences before making the existing mutation request.
- Replace the action with a non-interactive `Refund requested` status after a successful request;
  retries and API failures must remain truthful and must not display a confirmed state prematurely.
- Use state-specific legal copy: pre-checkout agreement language before purchase and payment/refund
  information after purchase.
- Preserve the existing ORNA palette, light-on-dark composition, typography roles, legal links and
  practical 44 px minimum touch-target guideline.
- Add deterministic Playwright coverage for paid, refund-confirmation, refund-requested and narrow-
  viewport geometry states.

### Non-goals

- Changing the lifetime product, price source, currency policy, no-renewal promise or entitlement
  rules.
- Changing Bereke checkout, callback verification, purchase persistence, refund transaction order or
  the 14-calendar-day refund policy.
- Adding partial refunds, recurring billing, receipts, invoices or purchase-history pagination.
- Redesigning the complete account dashboard, global navigation or unauthenticated membership flow.
- Hiding configured test mode from a buyer; domain rules require it to remain explicit.
- Adding a new backend field solely for presentation when the accepted UI can be derived truthfully
  from the existing generated purchase and offer contracts.

## Design and boundaries

`web/app/membership/page.tsx` continues to compose the account route. Purchase-state presentation and
interaction stay in `web/components/membership-billing-panel.tsx`; transport remains in
`web/lib/api/billing.ts`; responsive styling stays in `web/app/styles.css`.

The component has three explicit presentation modes:

1. **Pre-checkout:** offer price, one-payment/no-renewal disclosure, digital-product disclosure,
   verification/availability state and the secure-checkout action.
2. **Paid:** active lifetime-access heading plus a compact purchase summary for amount, paid date and
   shortened/copyable order reference. Refund policy and the secondary refund action belong below the
   summary; internal processor details do not.
3. **Refund requested:** purchase facts remain visible, the mutation action is absent, and a
   provider-neutral status message states that refund confirmation is pending. Access remains derived
   from the membership API; the frontend must not revoke or promise revocation by itself.

The refund interaction is a local two-step disclosure, not an immediate mutation. The first action
reveals a clearly titled confirmation region with `Keep membership` and `Confirm full refund`
actions. Focus moves into that region; cancellation returns focus to the initiating action. Only the
explicit confirmation calls `requestPurchaseRefund`. The server remains authoritative for refund
eligibility and idempotency.

The order reference is visually abbreviated with a stable beginning and ending segment, while its
full value is the copy payload and accessible description. Copy success/failure is announced without
changing purchase state. No reference value is written to logs or analytics.

The payment date uses `Intl.DateTimeFormat` with an unambiguous day/month-name/year format and the
active document/user locale rather than a hard-coded ambiguous numeric English format. The refund
window date is derived from the authoritative `paid_at` timestamp and the existing 14-calendar-day
rule for explanatory display; an apparent client-side window never overrides a server rejection.

Responsive containment must be achieved through bounded children (`min-width: 0`), a zero-minimum
single-column track, safe wrapping/abbreviation and normal document reflow. `overflow: hidden` is not
accepted as evidence that descendants fit.

## Contract and data changes

None expected. The accepted design uses existing generated fields:

- `PurchaseRead.amount_minor`
- `PurchaseRead.currency`
- `PurchaseRead.paid_at`
- `PurchaseRead.merchant_reference`
- `PurchaseRead.status`
- existing offer fields and the configured fixed KZT 2.00 test-mode sentinel

No database schema, Alembic migration, backend router/service/repository behavior or generated
OpenAPI/TypeScript schema change is in scope. If implementation proves that a truthful refund-window
or test-mode state cannot be represented from these fields, stop and amend this accepted spec before
introducing a contract field.

## Security, privacy and failure behavior

- Authentication, ownership and refund authorization remain enforced by the existing backend.
- The frontend must never infer entitlement from payment copy; membership API state remains
  authoritative.
- The full merchant reference is rendered/copyable only for its authenticated owning user and must
  not be added to analytics, console output or error telemetry.
- Clipboard denial or an unavailable Clipboard API produces a bounded inline failure message and
  does not alter purchase/refund state.
- Opening or cancelling refund confirmation has no backend side effect.
- The confirm action is disabled while its request is in flight to prevent duplicate UI submission;
  backend idempotency remains authoritative.
- A failed, late or ambiguous refund response leaves the last server-confirmed purchase/access state
  visible and announces the error. It must not show `Refund requested` unless the request succeeds or
  a refreshed purchase already has that status.
- Test mode remains conspicuous when active and absent otherwise. Presentation changes must not turn
  test checkout into evidence of production-provider readiness.
- Terms and Refund Policy links remain keyboard reachable with visible focus.

## Acceptance scenarios

1. Given an authenticated paid user with a maximum-length merchant reference, when `/membership` is
   rendered at 320 px and 390 px widths, then the document, billing panel, purchase card, all visible
   text and every interactive control remain inside the viewport with no hidden clipping.
2. Given the same paid state with enlarged browser text, when the page reflows, then purchase values
   wrap or abbreviate without overlap and every control remains reachable with a practical minimum
   44 px target height.
3. Given a confirmed paid purchase, when the billing panel renders, then it leads with active lifetime
   access and shows amount/currency, an unambiguous localized paid date and a shortened order reference
   instead of checkout-oriented sales copy or the internal payment-processor name.
4. Given the shortened order reference, when a keyboard or pointer user activates Copy, then the full
   reference is sent to the clipboard and success is announced without exposing it in logs or
   analytics; clipboard failure is announced without changing purchase state.
5. Given a production offer, when pre-checkout or paid UI renders, then no test-mode label appears.
6. Given the configured fixed KZT 2.00 test offer, when pre-checkout or paid UI renders, then a clear
   `Test payment mode` disclosure appears and does not claim production readiness.
7. Given a paid purchase inside the self-service window, when the page renders, then refund is a
   secondary action and the 14-calendar-day deadline is stated with an unambiguous date.
8. Given a user activates the refund action, when confirmation opens, then no request has been sent,
   the full-refund/access consequence is named, focus enters the confirmation region, and cancelling
   restores the non-mutating state.
9. Given confirmation is open, when the user explicitly selects `Confirm full refund`, then exactly
   one UI request is made while busy; success removes the action and shows `Refund requested`, while
   failure keeps the paid summary and announces the server error.
10. Given a purchase already has `refund_requested` status, when the page loads or refreshes, then the
    refund action is absent, pending refund confirmation is stated without naming the processor, and
    membership/access text continues to come from the membership response.
11. Given a paid purchase, when legal disclosure renders, then it links the Refund Policy without
    repeating the processor name or saying `By continuing`; given pre-checkout state, agreement
    language and one explicit hosted-checkout processor disclosure are retained.
12. Given existing unpaid, entitled-without-purchase and checkout-unavailable fixtures, when the
    component changes, then their truthful actions and fail-closed status remain unchanged.

## Verification plan

- Narrow RED/GREEN browser regressions in `web/e2e/auth.spec.ts`:
  - paid maximum-length reference geometry at 320 px and 390 px;
  - explicit descendant bounding-box checks in addition to document `scrollWidth`;
  - text-enlargement/reflow containment;
  - purchase-summary fields and state-specific disclosure;
  - test-mode versus production-offer labeling;
  - copy success/failure announcement with a stubbed Clipboard API;
  - refund confirmation, cancellation, one-request busy guard, success, failure and already-requested
    states.
- Frontend checks: `cd web && npm run test:unit && npm run typecheck && npm run lint && npm run build`.
- Generated contract check: `cd web && npm run api:check`; expected unchanged and green.
- Browser suite: `cd web && npm run test:e2e` after the narrow canaries pass.
- Manual visual evidence: recapture `/membership` at approximately 390 x 844 and 1440 x 900 for paid
  and refund-requested states; inspect focus, clipping, typography and vertical rhythm.
- Backend unit/contract checks: not required for the intended frontend-only change; run targeted
  billing tests only if implementation changes shared transport behavior.
- Disposable dependency/integration checks: not applicable without backend or provider changes.
- Migration upgrade/downgrade checks: not applicable; no schema change.
- Required repository checks remain `python -m pytest`, `python -m ruff check .`, frontend typecheck
  and lint before final delivery; report any environment blocker rather than skipping silently.

## Rollout, rollback and observability

Deploy as a frontend-only change after browser and build checks pass. No data migration or feature flag
is required. Rollback restores the previous frontend bundle without affecting purchases, grants,
refund requests or callbacks.

Do not add merchant references or clipboard payloads to analytics. Existing bounded billing API status
and error observability remains unchanged. Production smoke must verify the profile route through the
public gateway and confirm that the production offer does not display the test-mode treatment unless
test mode is deliberately configured.

## Documentation and decisions

- Keep this spec `accepted` until implementation and verification are complete; then mark it
  `implemented` and link the PR.
- Update `specs/README.md` to index this accepted change.
- Update `docs/CURRENT_STATE.md` only after browser evidence proves the responsive paid/refund UX.
- No domain-rule, architecture or ADR update is expected because product, entitlement and refund
  semantics do not change.

## Open questions

None. The user approved implementation of the complete audit recommendation set; this spec resolves
its presentation, responsive, localization, test-mode and refund-confirmation behavior without
changing billing domain semantics.

## Implementation handoff

Primary roles are frontend and test, with documentation reconciliation at completion. Start with a
paid maximum-length-reference Playwright canary that fails for the observed clipping, then implement
the smallest containment fix and re-run adjacent viewport checks. Continue as separate RED/GREEN
slices for purchase-summary semantics, localization/copy behavior, test-mode presentation, refund
confirmation/status, and state-specific legal copy. Preserve all billing authorization, entitlement,
provider and refund-policy behavior. Freeze the final candidate only after the narrow tests, complete
frontend suite, repository checks, desktop/mobile screenshots and final diff review are complete.
