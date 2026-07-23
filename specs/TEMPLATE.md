# Spec: <short outcome>

- Status: draft
- Owner: <name or role>
- Last updated: YYYY-MM-DD
- Related issue/PR: <link or identifier>
- Related ADRs: <links or none>

## Problem and outcome

Describe the observed problem, who is affected, and the measurable outcome. Separate current
evidence from assumptions.

## Context and evidence

- Current-state section:
- Domain rules/invariants:
- Relevant code, migration and contract entry points:
- Existing tests or production evidence:

## Scope

### In scope

- <behavior or deliverable>

### Non-goals

- <explicitly excluded behavior>

## Design and boundaries

Describe the responsible modules/layers, dependency direction and transaction/side-effect order.
Explain any backend, frontend, worker or integration handoff. Link the canonical architecture rather
than copying it.

## Contract and data changes

List API request/response/error changes, generated frontend types, schema/index changes, migration
and compatibility expectations. Write `None` when genuinely unaffected.

## Security, privacy and failure behavior

Cover authorization, sensitive fields, logging, storage/object scope, abuse/rate limits, dependency
outages, retries, concurrency and idempotency. State fail-closed behavior explicitly where relevant.

## Acceptance scenarios

1. Given <precondition>, when <action>, then <observable result>.
2. Given <denied/failure/concurrent condition>, when <action>, then <safe observable result>.

Include boundary and negative cases, not only the success path.

## Verification plan

- Narrow regression test:
- Backend unit/contract checks:
- Disposable dependency/integration checks:
- Frontend unit/type/build checks:
- Browser/accessibility checks:
- Migration upgrade/downgrade checks:
- Governance/agent evals, if developer-platform context changes:

For each non-applicable or skipped layer, state why.

## Rollout, rollback and observability

Describe ordering, feature/data compatibility, metrics/logs, recovery and the exact rollback limit.
Do not claim rollback is safe if the migration or external side effect is irreversible.

## Documentation and decisions

List `CURRENT_STATE`, domain-rule, architecture companion, ADR and user/developer documentation
updates. Identify any durable decision that needs a separate ADR.

## Open questions

- <owner>: <question and decision deadline>

## Implementation handoff

Summarize affected layers, specialist roles, sequencing constraints, acceptance evidence and known
risks so another contributor can continue without the originating conversation.
