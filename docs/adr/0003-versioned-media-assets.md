# ADR-0003: Versioned media assets

- Status: accepted
- Date: 2026-07-12

## Decision

Media masters and derived renditions use immutable revisioned object keys. Activating a new revision is a database state transition after upload verification; cleanup requires an explicit archive followed by purge and never deletes an active revision.

## Rationale and consequences

Immutable keys make retries and concurrent workers safe and avoid stale CDN/browser content. Partial unique indexes enforce one active source, rendition and processing job; a scheduled retention policy remains future operational work.
