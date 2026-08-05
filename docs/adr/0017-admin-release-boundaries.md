# ADR-0017: Admin release uses an outer no-store boundary and loopback-only direct smoke

- Status: accepted
- Date: 2026-08-05

## Context

ADR-0012 defines the admin workspace authorization, concurrency, audit and fail-closed browser boundaries. Production acceptance also depends on two cross-layer properties that cannot be owned by an individual route: every admin response must remain non-cacheable even when an exception escapes route handling, and the deployed frontend must be verifiable independently from the public nginx path without exposing an additional public listener.

A handler or dependency that decorates only successful responses cannot cover all framework-generated errors or an unhandled `500`. Likewise, checking only nginx can hide a stale frontend build, while publishing the Next.js port on every interface would unnecessarily widen the production attack surface. Account-management controls must also remain absent unless the production environment explicitly enables the independently reviewed gate.

## Decision

The application enforces `Cache-Control: no-store` for every `/api/v1/admin/**` outcome at the outer response boundary, including authentication failures, validation and precondition errors, explicit empty responses and unhandled server errors. Route handlers and dependencies may retain local headers, but they are not the authoritative no-store boundary.

The production Compose overlay publishes the Next.js service only on `127.0.0.1:3000`. This loopback listener is an independent release-smoke path, not a second public ingress. Public traffic continues to enter through nginx on HTTP/HTTPS, and the direct and gateway `/admin` checks are separate blocking assertions.

The frontend receives `ADMIN_ACCOUNT_MANAGEMENT_ENABLED` from the server environment with a fail-closed default of `false`. Enabling it is an explicit production configuration action after exact-candidate security review and green CI; deployment does not infer enablement from the existence of admin routes.

Production smoke verifies HTTPS with the configured hostname and certificate validation, resolving that hostname to loopback only for the host-local probe. Optional member/admin credentials are accepted only from the environment, written to mode-`0600` temporary curl configuration, omitted from URLs and command arguments, and removed after the bounded read-only checks.

## Consequences

Unhandled admin failures cannot become cacheable merely because they bypass normal route response construction. Operators can distinguish a frontend packaging/readiness failure from an nginx routing failure while port `3000` remains unreachable off-host. A single-replica frontend recreation can still create a short real `502` warm-up window; release completion therefore waits for direct readiness before judging the gateway result.

The direct port and feature-gate environment become deployment-contract surfaces that require Compose validation and production smoke. Gateway `404`/`502`, a missing direct listener after readiness, absent no-store headers, certificate-validation bypass, or accidental public publication of port `3000` blocks the release.
