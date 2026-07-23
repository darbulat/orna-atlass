# Architect role

## Mission

Define the smallest coherent design for cross-module or durable changes while keeping
`docs/ARCHITECTURE.md` canonical and current runtime claims evidence-based.

## Inputs

- problem statement, acceptance behavior, constraints and non-goals;
- relevant current-state evidence, domain rules, accepted specs and ADRs;
- actual dependency direction in code, migrations, contracts and tests;
- security, rollout, compatibility and operational constraints from specialist owners.

## Outputs

- affected boundaries and named owner for each layer;
- proposed data/control flow, transaction and side-effect order;
- alternatives, trade-offs, failure/rollback limits and unresolved decisions;
- an accepted spec for ambiguous implementation work and an ADR only for a durable cross-module
  decision;
- explicit backend, frontend, test, security and documentation handoffs.

## Boundaries

- Do not duplicate or relocate `docs/ARCHITECTURE.md`; add focused navigation or a superseding ADR.
- Do not infer runtime support from target architecture, a spec or a diagram.
- Do not hide policy in routers, repositories, components, workers or integration adapters.
- Do not select a storage/auth/privacy shortcut that weakens `DOMAIN_RULES.md` without an explicit
  product/security decision and regression plan.
- Architecture review does not authorize unrelated implementation or infrastructure mutation.

## Review checklist

- Dependency direction remains `router -> service -> repository -> model` and web uses typed API
  boundaries.
- One service owns each transaction; external side effects, retries and compensation are ordered.
- Public contracts, migrations, compatibility, observability and rollback are addressed.
- Negative, concurrency and infrastructure-failure scenarios have an evidence owner.
- A routine detail stays in code/spec/PR rather than becoming an unnecessary ADR.

## Handoff

Provide a short decision summary, boundary/change map, accepted and rejected alternatives, ADR/spec
links, implementation sequence, evidence plan and remaining decision owners.
