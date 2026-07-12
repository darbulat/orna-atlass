# ADR-0003: Versioned media assets

- Status: proposed
- Date: 2026-07-12

## Decision

Media masters and derived renditions will use immutable revisioned object keys. Activating a new revision is a database state transition after upload verification; cleanup is asynchronous and never deletes the active or last-known-good revision.

## Rationale and consequences

Immutable keys make retries and concurrent workers safe and avoid stale CDN/browser content. A migration and lifecycle job are required before this ADR can become accepted.

