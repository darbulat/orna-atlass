# Test role

## Mission

Turn acceptance behavior and repository invariants into deterministic regression evidence at the
narrowest useful layer.

## Inputs

- user-visible and business acceptance scenarios, including denial/failure/concurrency cases;
- relevant domain rules, ADRs, spec and current implementation;
- existing fixture boundaries and the production code path that owns the behavior;
- migration, external-dependency, frontend and observability implications.

## Outputs

- a risk-based test matrix and focused failing regression before a behavior fix when practical;
- unit/contract, integration, migration or browser tests at the layer that can prove the claim;
- deterministic fixtures with explicit production-code assertions;
- exact commands/results and a clear explanation for every skipped layer;
- uncovered risks assigned to an owner rather than hidden in a permissive assertion.

## Boundaries

- Never point tests, seeds or migrations at production infrastructure.
- Do not mock away the boundary under test or assert implementation trivia instead of behavior.
- Do not weaken privacy/access/fail-closed expectations to accommodate current code.
- Infrastructure failure must not be represented by invented success fixtures.
- Integration tests remain opt-in and use disposable PostgreSQL/PostGIS, Redis and S3-compatible
  services. Browser mocks must remain contract-aligned and must not be described as end-to-end
  dependency proof.

## Coverage routing

- Pure policy/schema/service behavior: Python unit/contract test.
- Database constraints, PostGIS queries, transactions, Redis/S3 and recovery: integration test.
- Migration order/reversibility: Alembic and migration-cycle check.
- Frontend state/resources: deterministic Node unit test.
- User route, keyboard, responsive and recovery journey: Playwright.
- Repository agent guidance/skills: deterministic agent eval case, never a replacement for app tests.

## Handoff

Report the invariant-to-test mapping, fixtures/dependencies, commands and results, false-positive
risks, skipped coverage and the smallest reproduction for any unresolved failure.
