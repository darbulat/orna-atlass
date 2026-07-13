# ORNA Atlas: current implementation

Last verified: 2026-07-13. This document describes code that exists now. `ARCHITECTURE*.md` and `IMPLEMENTATION_PLAN_rus.md` may also describe target behavior; when they disagree, code, migrations and tests are authoritative.

## Capability matrix

| Area | State | Evidence / limitation |
|---|---|---|
| Public atlas, sessions and collections | Implemented | FastAPI routers and Next.js pages exist; hidden locations are excluded by one shared public-discovery policy across location, atlas, session and collection flows. |
| PostgreSQL persistence | Implemented | Async SQLAlchemy and Alembic; many tests still mock repositories. |
| Domain state constraints | Implemented | Shared string enums validate API input and Alembic CHECK constraints reject unknown visibility, access, processing, media/job states and invalid numeric intervals. |
| Redis cache and RQ | Implemented with limits | Redis integration and persistent jobs exist; concurrent processing needs stronger exclusion. |
| S3-compatible audio | Implemented with limits | MinIO compose setup, uploads and presigned URLs exist; lifecycle/versioning remains incomplete. |
| Playback | Implemented | Grants fail closed without a ready stored rendition; members-only sessions require an active entitlement and successful grants are audited. |
| Coordinate privacy | Implemented with limits | Visibility fields, approximate projection and a shared hidden-location predicate cover current public flows; database enum/check constraints remain planned. |
| Authentication and membership | Implemented | Short-lived signed access tokens, rotating server-side refresh tokens, secure cookies, self-service contracts and RBAC are present. Entitled users can discover and render members-only session list/detail records. |
| Admin authentication | Implemented with local compatibility | Production uses admin-role tokens and has an audited one-time first-admin command. The local header defaults off, is accepted only when explicitly enabled in local/development, and is rejected elsewhere. |
| BirdNET analysis | Implemented with limits | Worker integration exists; failure and last-successful-result policy needs hardening. |
| Frontend tests | Smoke baseline | Playwright suite verifies public navigation; detailed player races and accessibility remain uncovered. |
| Frontend API contracts | Generated baseline | `web/openapi.json` and `web/lib/api/generated.ts` are generated from FastAPI and checked for drift in CI; collections consume generated schemas while remaining clients are migrated incrementally. |
| Dependency integration tests | Opt-in baseline | `tests/integration` verifies PostgreSQL migration state, Redis and S3 round trip against disposable services. |
| Observability | Baseline | API emits JSON request logs with request ID, status and duration; distributed tracing and metrics backend are planned. |

## Runtime entry points

- API: `orna_atlas.app.main:app`.
- Worker: `python -m orna_atlas.app.workers.audio_pipeline worker`.
- Migrations: `alembic upgrade head`.
- Web: `web/package.json` scripts (`dev`, `build`, `test:e2e`).
- Local orchestration: `docker-compose.yml`.

## Known high-risk gaps

Weak job concurrency protection and remaining manually duplicated session client aliases are active debt. Auth uses a project-local HS256 implementation and should move to centrally managed signing keys/JWKS before multi-service deployment. Local admin mode must remain disabled outside development.

Repositories flush and query but do not commit. Services own transaction boundaries and perform cache invalidation only after a successful commit. Audio byte parsing/waveform generation and frontend listening/timeline calculations live outside their orchestration components; further visual component extraction remains incremental cleanup.

## Updating this document

Move a capability to “Implemented” only when code plus an appropriate test proves it. Mention limitations explicitly. Planned product behavior belongs in architecture/plan documents, not in this current-state matrix.
