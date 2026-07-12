# ADR-0001: Public coordinate projection

- Status: accepted
- Date: 2026-07-12

## Decision

All public routes use one explicit public location projection. Exact, approximate and hidden behavior follows `docs/DOMAIN_RULES.md`; nested collection/session responses cannot bypass it. Admin projections are separate types.

## Rationale and consequences

Coordinate sensitivity is a cross-route privacy invariant. Central projection reduces accidental ORM serialization and makes tests reusable. Existing routes that construct their own public shape must migrate incrementally and keep regression tests for all visibility modes.

