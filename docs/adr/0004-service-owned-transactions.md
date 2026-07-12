# ADR-0004: Service-owned transactions

- Status: accepted
- Date: 2026-07-12

## Decision

Application services own transaction boundaries. Repositories query, add and flush but do not commit. External side effects use explicit ordering and compensation; cache invalidation happens after commit.

## Rationale and consequences

A service is the smallest layer that sees the complete business operation. One owner prevents partial commits and makes rollback behavior testable. Existing repository commits should be removed incrementally with integration coverage.

