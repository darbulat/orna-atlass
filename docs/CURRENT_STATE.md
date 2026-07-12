# ORNA Atlas: current implementation

Last verified: 2026-07-12. This document describes code that exists now. `ARCHITECTURE*.md` and `IMPLEMENTATION_PLAN_rus.md` may also describe target behavior; when they disagree, code, migrations and tests are authoritative.

## Capability matrix

| Area | State | Evidence / limitation |
|---|---|---|
| Public atlas, sessions and collections | Implemented | FastAPI routers and Next.js pages exist; public projection rules are not yet centralized. |
| PostgreSQL persistence | Implemented | Async SQLAlchemy and Alembic; many tests still mock repositories. |
| Redis cache and RQ | Implemented with limits | Redis integration and persistent jobs exist; concurrent processing needs stronger exclusion. |
| S3-compatible audio | Implemented with limits | MinIO compose setup, uploads and presigned URLs exist; lifecycle/versioning remains incomplete. |
| Playback | Implemented with prototype fallback | A missing real rendition can still produce mock silence in some flows; this is not production-ready behavior. |
| Coordinate privacy | Partially implemented | Visibility fields and approximate projection exist, but every public collection/location flow is not proven consistent. |
| Admin authentication | Development-only | Static local header exists; it is not a production identity system. |
| BirdNET analysis | Implemented with limits | Worker integration exists; failure and last-successful-result policy needs hardening. |
| Frontend tests | Smoke baseline | Playwright suite verifies public navigation; detailed player races and accessibility remain uncovered. |
| Dependency integration tests | Opt-in baseline | `tests/integration` verifies PostgreSQL migration state, Redis and S3 round trip against disposable services. |
| Observability | Baseline | API emits JSON request logs with request ID, status and duration; distributed tracing and metrics backend are planned. |

## Runtime entry points

- API: `orna_atlas.app.main:app`.
- Worker: `python -m orna_atlas.app.workers.audio_pipeline worker`.
- Migrations: `alembic upgrade head`.
- Web: `web/package.json` scripts (`dev`, `build`, `test:e2e`).
- Local orchestration: `docker-compose.yml`.

## Known high-risk gaps

The static admin bypass, fail-open mock playback, inconsistent public projection, weak job concurrency protection and manually duplicated frontend contracts must be treated as active debt. Do not build new features on these behaviors as if they were stable contracts.

## Updating this document

Move a capability to “Implemented” only when code plus an appropriate test proves it. Mention limitations explicitly. Planned product behavior belongs in architecture/plan documents, not in this current-state matrix.

