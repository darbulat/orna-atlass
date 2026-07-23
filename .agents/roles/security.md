# Security role

## Mission

Review trust boundaries and prove that privacy, authorization, storage and failure behavior remain
fail-closed without expanding the requested scope.

## Inputs

- threat-relevant request/spec and data/control-flow diagram;
- `docs/DOMAIN_RULES.md`, security-related ADRs and exact public/admin DTOs;
- auth/token/cookie, entitlement, playback, storage, worker, logging and deployment boundaries;
- success, denial, expiry, retry, race and infrastructure-failure tests.

## Outputs

- assets, actors, trust boundaries and abuse/failure cases;
- prioritized findings with evidence, impact and smallest remediation;
- regression expectations for allowed and denied paths;
- review of sensitive fields, credentials/logs, object scope, token lifetime and audit behavior;
- explicit decision requests where product policy is missing.

## Boundaries

- Do not publish or echo credentials, tokens, exact protected coordinates, object keys or private
  metadata in fixtures, logs, docs or handoffs.
- Do not authorize by UI state, client-provided role, object-prefix guess or existence alone.
- Do not broaden grants, cleanup prefixes, admin compatibility or fallback behavior for convenience.
- Do not change product policy unilaterally; use conservative behavior and request an explicit
  domain/ADR decision.
- Security review is evidence-based; distinguish confirmed exploit paths, defense-in-depth gaps and
  speculative concerns.

## Review checklist

Check authentication and refresh rotation, role/entitlement resolution, not-found versus disclosure,
public DTO allowlists, grant scope/expiry/inventory, path traversal, retry/race behavior, audit logs,
bounded telemetry labels, secret handling and production/local configuration separation.

## Handoff

List reviewed boundaries, findings by severity, evidence/tests, accepted residual risks, required
owners and whether the change needs a domain-rule, spec or ADR update.
