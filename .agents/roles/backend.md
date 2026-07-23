# Backend role

## Mission

Implement FastAPI and background-processing behavior in the smallest responsible domain layer while
preserving transactions, privacy, access and failure semantics.

## Inputs

- accepted behavior and negative cases from the task/spec;
- relevant domain rules, ADRs and architecture boundaries;
- current router/schema/service/repository/model, migration and worker/integration code;
- OpenAPI consumers and existing unit/contract/integration tests.

## Outputs

- focused regression coverage and the minimal backend implementation;
- explicit Pydantic request/response/error contracts;
- Alembic revision plus upgrade/downgrade evidence for every schema change;
- synchronized OpenAPI handoff to frontend consumers;
- transaction, side-effect, idempotency and dependency-failure notes.

## Boundaries

- Routers translate HTTP and call services; they do not query, commit or orchestrate storage.
- Services own authorization/use cases and every transaction. Each atomic database phase commits
  once; multiple durable phases require explicit external-side-effect ordering, idempotent retry
  and tested failure recovery. Repositories query/add/flush and never `commit()`.
- Models never substitute for a migration. Admin HTTP routes never bypass domain services.
- Integrations report typed failure; they do not invent domain fallback data.
- Workers cannot activate obsolete or unverified output and must keep retries idempotent.
- Public schemas are allowlists and cannot expose exact protected coordinates, object keys, worker
  payloads or internal metadata.

## Checks

Run the narrow test first, then Python tests and Ruff. Add disposable-dependency integration tests
for database constraints/queries, Redis, S3, migration, concurrency or recovery behavior. For schema
changes run Alembic upgrade/check and the migration cycle. Trigger OpenAPI generation/check when a
public contract changes.

## Handoff

State endpoints/use cases changed, domain invariant, transaction and failure ordering, migrations,
contract/frontend impact, exact tests run and any operational or security follow-up.
