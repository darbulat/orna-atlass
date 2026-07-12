# ADR-0002: Playback authorization is fail-closed

- Status: accepted
- Date: 2026-07-12

## Decision

A playback grant requires authorization plus a ready rendition whose object exists. Missing media, processing state and storage failure return distinct unavailable/error responses. Silent mock audio is permitted only behind an explicit local-development setting.

## Rationale and consequences

Returning a playable-looking URL for unavailable content hides editorial and infrastructure failures. Clients must render an unavailable state and refresh expiring grants explicitly.

