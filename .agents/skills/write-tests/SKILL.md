---
name: write-tests
description: "Add or improve ORNA Atlas regression coverage. Use for backend unit and API contract tests, disposable-dependency integration tests, frontend reducer tests, Playwright journeys, concurrency cases, or bug reproductions."
---

# Write ORNA Tests

## Choose the narrowest proof

1. Read the affected invariant in `docs/DOMAIN_RULES.md` and confirm current behavior in `docs/CURRENT_STATE.md`.
2. Place pure and contract coverage in `orna_atlas/app/tests/`, real dependency coverage in `tests/integration/`, and browser behavior in `web/e2e/`.
3. Reproduce the failure before changing production code and assert externally visible behavior rather than implementation details.
4. Reuse nearby fixtures and test vocabulary; avoid introducing a second harness for the same boundary.

## Cover ORNA failure modes

- Assert public coordinate allowlists and hidden-location exclusion across nested flows.
- Assert publication, access, entitlement, and rendition readiness independently for session and playback cases.
- Assert one service owner and one commit per atomic database phase. For multi-phase workflows,
  assert external-side-effect ordering, idempotent retries, partial-failure recovery and cache
  invalidation after the relevant commit.
- Assert malformed responses and PostgreSQL, Redis, S3, SMTP, provider, or media failures as truthful failures without fabricated success.
- Assert stale-response, duplicate-action, lease, retry, and concurrent-update ordering where shared state is involved.
- Assert API schema allowlists when changing public DTOs and regenerate OpenAPI types when the contract changes.

## Keep tests safe and deterministic

- Use only disposable PostgreSQL, Redis, and S3-compatible instances; never point fixtures or seed commands at production.
- Fix clocks, random identifiers, ordering, and provider outputs where nondeterminism is irrelevant.
- Avoid live network calls in the default suite.
- Keep integration tests opt-in with the existing `integration` marker and `RUN_INTEGRATION_TESTS=1` gate.
- Keep Playwright deterministic with the mock API unless explicitly validating a disposable real stack.

## Verify

1. Run the new test alone and confirm that it fails before the fix and passes after it.
2. Run `python -m pytest` and `python -m ruff check .` for backend changes.
3. Run `RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration` only against inspected disposable services.
4. Run `cd web && npm run typecheck && npm run lint && npm run test:e2e` for frontend behavior.
5. Report skipped dependency coverage explicitly instead of implying that it passed.
