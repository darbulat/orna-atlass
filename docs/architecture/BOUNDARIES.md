# Repository boundaries

This companion maps change ownership and dependency direction. It does not replace the target
architecture in [`../ARCHITECTURE.md`](../ARCHITECTURE.md), and it does not establish current
capability claims; use [`../CURRENT_STATE.md`](../CURRENT_STATE.md) for those.

## Dependency direction

```text
web route -> web component -> typed API wrapper -> HTTP API
                                              |
FastAPI router -> application service -> repository -> SQLAlchemy model / database
                              |          -> integration adapter -> external service
                              `----------> worker/job boundary
```

Dependencies point toward the layer that owns the rule. HTTP, queue and storage details must not
become domain policy.

| Boundary | Owns | May call | Must not own or bypass |
| --- | --- | --- | --- |
| `orna_atlas/app/main.py` | application assembly, middleware, health/metrics wiring | routers and core infrastructure | domain use cases |
| `modules/*/router.py` | HTTP validation, authentication dependency, status/error translation | the same domain's service | transactions, direct persistence, storage orchestration |
| `modules/*/service.py` | use cases, authorization orchestration, ownership of each transaction and explicit durable phases | repositories, explicit integrations, job enqueue after durable state | HTTP response concerns, repository commits or undocumented phase boundaries |
| `modules/*/repository.py` | bounded queries, adds and flushes | models and database session | `commit()`, caller policy or invented fallback data |
| `modules/*/models.py` | persisted shape and database relationships | shared database types | public serialization or migration history |
| `integrations/` | adapters for Redis, S3, sunrise and BirdNET | external clients | hidden domain fallback behavior |
| `workers/` | leased/idempotent background orchestration and recovery | application services, repositories and integrations through explicit boundaries | activating unverified/obsolete output |
| `app/migrations/` | ordered, reversible database evolution | database DDL/data migration operations | application runtime policy |
| `web/app/` | route composition and server/client boundary | components and API wrappers | duplicated API/domain policy |
| `web/components/` | interactive UI, accessible state and persistent audio controls | typed props and API wrappers | private API shapes or coordinate reconstruction |
| `web/lib/api/` | transport, generated DTO types and narrow view-model mapping | generated OpenAPI contracts | hand-maintained copies of backend schemas |

`modules/admin` is an HTTP surface, not an alternative domain layer. Publishing, uploads, role
changes and cleanup still travel through the responsible service.

## Cross-cutting invariants

Some rules need more than one owner and therefore require end-to-end regression coverage:

- Public location privacy: database query/projection, DTO, nested API flows and UI state.
- Playback access: entitlement, publication, rendition verification, grant/gateway and player
  refresh behavior.
- Media lifecycle: immutable keys, processing-job state, verified inventory, activation and cleanup.
- Authentication: token/cookie boundary, refresh rotation, role policy and account UI recovery.
- Contracts: Pydantic schema, exported OpenAPI, generated TypeScript and frontend wrapper behavior.

Route these changes through the architect and security roles as applicable, then assign backend,
frontend and test ownership explicitly.

## Change map

| Change | Required context | Likely evidence |
| --- | --- | --- |
| Public API field or endpoint | domain rule, relevant ADR/spec, backend and frontend contracts | contract/unit test, OpenAPI check, frontend typecheck |
| Database column/constraint/index | model, repository query, migration chain | upgrade/downgrade, `alembic check`, integration test |
| Auth/privacy/playback behavior | `DOMAIN_RULES.md`, security role, ADRs 0001/0002 | denial and success-path regression tests |
| Worker/media pipeline | media rules, job/asset models, integration adapters | idempotency/recovery and real-dependency tests |
| Interactive UI/player | generated DTO, player state machine, accessibility fallback | unit reducer/resource tests and Playwright |
| Durable cross-module direction | canonical architecture, current code, alternatives | accepted spec and/or new ADR |

If a proposed shortcut crosses a boundary, change the design or record an explicit architecture
decision; do not hide the dependency in a router, component or fixture.
