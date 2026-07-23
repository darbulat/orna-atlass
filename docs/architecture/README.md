# Architecture context index

[`../ARCHITECTURE.md`](../ARCHITECTURE.md) is the one canonical target architecture. This
directory contains focused navigation and boundary companions; it must not become a second
architecture specification. Runtime truth remains in
[`../CURRENT_STATE.md`](../CURRENT_STATE.md).

## Read by question

| Question | Read |
| --- | --- |
| What is implemented or limited now? | [`../CURRENT_STATE.md`](../CURRENT_STATE.md), then code/migrations/tests |
| What are the product and target system directions? | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Which business/privacy/lifecycle rule must hold? | [`../DOMAIN_RULES.md`](../DOMAIN_RULES.md) |
| Which layer owns a change and which direction may it depend? | [`BOUNDARIES.md`](BOUNDARIES.md) |
| How is developer/agent context selected and verified? | [`CONTEXT_SUPPLY_CHAIN.md`](CONTEXT_SUPPLY_CHAIN.md) |
| Why was a durable cross-module choice made? | [`../adr/README.md`](../adr/README.md) |
| What are this change's scope and acceptance scenarios? | [`../../specs/README.md`](../../specs/README.md) |

## Read by change

- Public location, atlas, search, collection or session response: coordinate/publication rules,
  ADR-0001, responsible module and public contract tests.
- Playback, membership or authentication: access rules, ADR-0002, security role, API/player tests.
- Database shape/query: boundaries, ADR-0004, model/repository, migration chain and integration
  evidence.
- Media pipeline, HLS or cleanup: media/processing rules, ADRs 0003 and 0005, worker/integration
  boundaries and recovery tests.
- Cross-layer frontend/API behavior: generated OpenAPI contract, backend/frontend roles and browser
  acceptance scenarios.
- Durable developer-platform governance: ADR-0006, context supply chain, roles, skills and eval
  registry.

## Maintenance rule

Add a companion only when it answers a stable navigation or boundary question more clearly than the
canonical document. Link to authoritative sections instead of copying target architecture or
current-state claims. New durable decisions belong in ADRs; task-level acceptance belongs in specs.
