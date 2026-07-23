---
name: review-change
description: "Review an ORNA Atlas local diff, commit, branch, or pull request for actionable defects. Use for correctness, privacy, security, transaction, contract, migration, concurrency, performance, test, and documentation review."
---

# Review an ORNA Change

## Establish scope

1. Read `AGENTS.md`, `docs/CURRENT_STATE.md`, relevant domain rules, and applicable ADRs.
2. Inspect the requested diff plus affected callers and tests; distinguish the change from unrelated worktree files.
3. Identify the invariant each changed path must preserve and trace cross-layer effects through backend, workers, storage, generated contracts, and web consumers.
4. Treat plans as intentions and code, migrations, and tests as runtime evidence.

## Hunt for concrete defects

- Check public projections for exact coordinates, hidden-location discovery, internal metadata, object keys, tokens, and service timestamps.
- Check session publication, caller access, entitlement, readiness, grant expiry, and successful-grant auditing independently.
- Check router, service, and repository responsibilities; reject repository commits. Accept multiple
  service commits only as explicit durable phases with tested side-effect ordering, idempotency and
  partial-failure recovery.
- Check retries, idempotency, rollback, stale responses, leases, cache invalidation after commit, and partial infrastructure failures.
- Check HLS inventory gating, immutable revision keys, publish-last ordering, and exact-inventory cleanup.
- Check schema changes for Alembic upgrade and downgrade paths and API changes for regenerated web contracts.
- Check error paths for fabricated fallback data, leaked secrets, unbounded metrics labels, and production-only escape hatches.
- Check tests for the affected invariant at the narrowest useful level, including negative and concurrent cases.

## Validate and report

1. Run focused read-only checks and tests when feasible; do not modify the change unless explicitly asked.
2. Report only actionable findings, ordered by severity, with an exact file and line plus the failure scenario and impact.
3. Separate confirmed defects from questions and residual risks.
4. State "no findings" when no defect is supported, then list any checks that could not run.
5. Avoid style-only comments and avoid restating the diff.
