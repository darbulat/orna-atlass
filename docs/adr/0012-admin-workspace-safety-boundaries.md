# ADR-0012: Admin workspace uses fail-closed authorization and aggregate concurrency

- Status: accepted
- Date: 2026-07-30

## Context

The administrative workspace exposes sensitive coordinates, account membership data, media lifecycle controls and operational audit details. Ordinary public projections and last-write-wins mutations are insufficient: stale administrative writes can lose editorial relationships, cookie-backed mutations need an origin boundary, and a revoked administrator must not retain an indefinitely usable privileged view.

The workspace is being merged as an internal baseline while release-level browser, audit and gateway verification remains explicitly tracked in `../ADMIN_WORKSPACE_FOLLOW_UP.md`.

## Decision

All `/api/v1/admin` operations require the server-resolved administrator identity and return no-store responses. Cookie-authenticated mutations require a trusted `Origin`; the decision is based on the authentication mode established by the server, never on the mere presence of a caller-controlled authorization header.

Mutable administrative aggregates expose strong ETags. Protected mutations require `If-Match`, return typed `428` when it is missing and typed `412` when it is stale, and validate the revision while holding the responsible row lock. Collection revisions include ordered relationship changes. User and membership state share one aggregate revision, while last-admin transitions additionally serialize through a PostgreSQL advisory transaction lock.

Admin services own transactions and write structured audit events in the same atomic database phase as the domain change. Public DTOs remain separate allowlists and never inherit admin revisions, exact coordinates or private operational metadata.

The SSR workspace validates privileged DTOs fail-closed. Sensitive searches remain transient and are excluded from URLs and notices. A client guard periodically revalidates the administrator identity and removes privileged content after authorization loss or revalidation failure. Account administration remains independently feature-gated.

## Consequences

Administrative writes may fail with explicit precondition errors and clients must re-read before retrying. Locking adds bounded database contention but prevents silent stale overwrites and last-admin races. Audit unavailability fails the corresponding atomic mutation rather than creating unaudited state.

The baseline is not production-ready merely because these boundaries exist. Full audit-event acceptance coverage, browser revocation/stale-write scenarios, disposable dependency checks, exact-candidate review, HTTPS gateway routing and production smoke remain mandatory before the workspace is enabled for operational use.
