# ORNA Atlas: current implementation

Last verified: 2026-07-14. This document describes code that exists now. `ARCHITECTURE*.md` and `IMPLEMENTATION_PLAN_rus.md` may also describe target behavior; when they disagree, code, migrations and tests are authoritative.

## Capability matrix

| Area | State | Evidence / limitation |
|---|---|---|
| Public atlas, sessions and collections | Implemented | One public-location projection is used by location, atlas, search, session and collection flows. A migration-backed API test proves hidden exclusion and exact-coordinate non-disclosure across all of them. |
| PostgreSQL/PostGIS persistence | Implemented | Alembic revisions `0008`–`0012` add generated exact/public `geometry(Point,4326)`, GiST indexes, tombstones, cleanup jobs, pipeline state/leases and seed-link ownership. Bbox, anti-meridian and low-zoom clustering use PostGIS; dawn selection uses bounded KNN GiST scans across the target and adjacent wrapped meridians. A 100k-row integration test verifies bounded DB aggregation and spatial-index use. |
| Domain state constraints | Implemented | Shared enums validate API input and DB checks reject unknown states, invalid intervals and `approximate_public` locations without a public coordinate pair. Domain services raise transport-independent errors mapped at the FastAPI boundary. |
| Redis cache and RQ | Implemented | Mixed search has one stable SQL page; corrupt cache payloads are evicted. Invalidation is centralized after commit. Processing jobs persist stage status/attempt/error, request/RQ correlation IDs and heartbeats; RQ timeout/retry scales by declared duration, unknown-duration jobs use the safe maximum, and a recovery worker replaces stale queued/running jobs through RQ. |
| S3-compatible audio | Implemented | Masters/renditions are versioned and activation follows upload plus object verification. Archive creates a durable retention job with lease/backoff; the cleanup worker performs idempotent deletion and records the storage tombstone. Real MinIO tests cover partial upload recovery and cleanup. |
| Playback | Implemented | Grants fail closed without an active ready stored rendition; blocking boto3 work runs off the async event loop. Members-only sessions require an active entitlement and grants are audited. The reducer-based player aborts stale requests, pauses on switch, refreshes expiring URLs and preserves position/state. |
| Coordinate privacy | Implemented | Exact and policy-derived public geometries are distinct; hidden rows have no public geometry. Public DTOs omit exact/public storage columns, internal metadata and service timestamps, while the admin DTO exposes editorial coordinates explicitly. |
| Authentication and membership | Implemented | Short-lived HS256 or RS256 access tokens, rotation-ready JWKS verification/publication, rotating server-side refresh tokens, secure cookies, self-service contracts and RBAC are present. Entitled users can discover and render members-only sessions. |
| Admin authentication | Implemented with local compatibility | Production uses admin-role tokens and has an audited one-time first-admin command. The local header defaults off, is accepted only when explicitly enabled in local/development, and is rejected elsewhere. |
| BirdNET analysis | Implemented | Provider output rejects non-finite/out-of-range intervals and confidence. A failed attempt preserves `last_successful`; a real PostgreSQL savepoint test proves an integrity failure does not poison the surrounding pipeline transaction. |
| Seed safety | Implemented | Seed requires explicit `--force` in local/test, takes a PostgreSQL advisory lock, claims only the exact owner marker, mutates only owned rows/links and never promotes a session without a ready stored rendition. Legacy manifest rows are adopted only with `--adopt-legacy-seed`; links are never inferred or claimed. |
| Frontend tests | Implemented baseline | Four Node-20 reducer/resource tests and twelve deterministic Playwright scenarios cover navigation, typed errors, membership, grant refresh, switch/abort races, seek, cleanup and keyboard/ARIA behavior. |
| Frontend API contracts | Implemented | Sessions, atlas, dawn, auth, playback and collections consume `components["schemas"]` from generated OpenAPI types; CI regenerates and rejects drift. Typed errors distinguish auth, forbidden, not-found, conflict, 5xx, invalid response and network outage without invented fallback data. |
| Dependency integration tests | Implemented opt-in | Disposable PostgreSQL/PostGIS, Redis and MinIO tests cover migrations, constraints, 100k geospatial aggregation, public privacy/cache invalidation, mixed search pages, pipeline concurrency/partial failure/recovery, BirdNET savepoints, seed ownership and storage cleanup. |
| Observability | Implemented baseline | Structured request/worker logs carry request, processing-job and RQ-job IDs. API `/metrics` exposes bounded-label HTTP metrics; the worker serves fork-safe multiprocess queue, outcome and per-stage metrics on port `9101`. A hosted metrics backend and distributed tracing are deployment concerns, not implemented runtime claims. |
| Deployment | Implemented | API and ML worker use separate Dockerfiles. The API image installs neither development nor TensorFlow/BirdNET dependencies; CI builds and inspects both images. Compose gates API/workers on a one-shot successful migration service and gives long-running workers restart policies. |

## Runtime entry points

- API: `orna_atlas.app.main:app`.
- Worker: `python -m orna_atlas.app.workers.audio_pipeline worker`.
- Storage retention: `python -m orna_atlas.app.workers.storage_cleanup worker`.
- Stale pipeline recovery: `python -m orna_atlas.app.workers.pipeline_recovery worker`.
- Migrations: `alembic upgrade head`.
- Web: `web/package.json` scripts (`dev`, `build`, `test:e2e`).
- Local orchestration: `docker-compose.yml`.

## Known high-risk gaps

Cache invalidation is centralized and happens after commit, but remains best-effort rather than a durable outbox; a Redis outage can leave an entry stale until its short TTL. Repositories flush/query without committing and services own transaction boundaries.

The recorded 1–6 hour benchmark covers checksum/metadata and streaming waveform work on sparse 8 kHz PCM. It does not measure BirdNET, real S3 latency or production 44.1/48 kHz recordings; those measurements remain mandatory before defining production SLOs. Streaming renditions are still copied WAV files rather than HLS.

Playwright is deterministic and uses a mock API by default. `E2E_API_URL` can point it at a real stack, but CI does not yet run browser-to-database/media fixtures, an axe scan or real codec/network playback.

`media/service.py`, `AtlasExplorer.tsx` and global `styles.css` remain large. The session-detail schema still contains a substantial ORM hydration validator. Pure audio/player utilities and the shared required-null validator have been extracted; further component/pipeline/style decomposition is maintainability work, not a hidden production claim. `ARCHITECTURE.md` is canonical and `ARCHITECTURE_rus.md` is its translation.

## Updating this document

Move a capability to “Implemented” only when code plus an appropriate test proves it. Mention limitations explicitly. Planned product behavior belongs in architecture/plan documents, not in this current-state matrix.
