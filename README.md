# ORNA Atlas

ORNA Atlas is a living sound atlas of natural places: long-form field recordings linked to exact locations, local time, sunrise movement, habitat metadata, and high-quality audio assets.

The implemented capabilities and current limitations are tracked in `docs/CURRENT_STATE.md`.

## Core stack

- **API:** FastAPI
- **Database:** PostgreSQL with PostGIS
- **Cache and jobs:** Redis
- **Audio processing:** RQ worker, persistent processing jobs, waveform metadata
- **Audio storage:** S3-compatible object storage (MinIO in local compose) with presigned playback URLs
- **Frontend:** Next.js / React, TypeScript, WebGL map/globe layer, audio-first interaction design
- **Primary domain:** locations, audio sessions, dawn line discovery, playback metadata, memberships, and editorial collections

## Local development

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start the stack:

```bash
docker compose up --build
```

The compose stack first runs `alembic upgrade head`, then starts the API,
frontend, PostgreSQL, Redis, the audio worker, and the resilient
storage-cleanup/pipeline-recovery workers.

3. Add local atlas test data:

```bash
docker compose exec -e APP_ENVIRONMENT=local api python -m orna_atlas.app.seed_atlas --force
```

Existing pre-ownership demo rows are never claimed implicitly. For a deliberate
one-time local/test migration of known manifest rows already marked `seed=true`,
add `--adopt-legacy-seed`; collection/session links are still left untouched.

4. Open the frontend at <http://localhost:3000> and the API at <http://localhost:8000>.

## Backend checks

```bash
pip install '.[dev,worker]'
python -m ruff check .
python -m pytest
alembic upgrade head
alembic check
APP_ENVIRONMENT=test RUN_MIGRATION_CYCLE_CHECK=1 \
  python -m orna_atlas.app.scripts.verify_migration_cycle
```

Real dependency smoke tests are opt-in and must target disposable local services:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
```

Frontend checks and browser smoke tests:

```bash
cd web
npm ci
npm run api:check
npm run test:unit
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

## Audio pipeline

Admin uploads create a `MediaAsset`, persist an `audio_pipeline` processing job, enqueue it on
Redis/RQ, and expose status through:

```http
POST /api/v1/admin/sessions/{session_id}/assets
GET /api/v1/admin/sessions/{session_id}/processing
POST /api/v1/admin/media-assets/{asset_id}/process
```

The worker can also be run directly:

```bash
python -m orna_atlas.app.workers.audio_pipeline worker
python -m orna_atlas.app.workers.storage_cleanup worker
python -m orna_atlas.app.workers.pipeline_recovery worker
```

Pipeline job timeouts scale with declared recording duration; jobs with unknown
duration receive the configured maximum timeout. Every stage persists its own
status/attempt/error, and stale queued or running jobs are failed and re-enqueued
through RQ after their heartbeat lease. See `docs/PERFORMANCE_BASELINE.md` for the
1–6 hour stage benchmark.

API/queue Prometheus metrics are exposed at `http://localhost:8000/metrics`; the
RQ worker exposes fork-safe pipeline/stage metrics at
`http://localhost:9101/metrics`. RS256 deployments publish sanitized verification
keys at `/.well-known/jwks.json`; configure signing material through the documented
`AUTH_*` environment variables rather than baking keys into an image.

## First production administrator

Keep `LOCAL_ADMIN_ENABLED=false` outside explicit local/development environments. After migrations,
register the intended owner as a normal user, then run this command once against the production
database from a secured application shell:

```bash
python -m orna_atlas.app.scripts.bootstrap_admin --email owner@example.com
```

The command takes a PostgreSQL transaction lock, refuses to run if any administrator already
exists, and writes an audit event. Further role changes must use the authenticated admin API.

## Documentation

- [Project architecture](docs/ARCHITECTURE.md)
- [Implementation plan (RU)](docs/IMPLEMENTATION_PLAN_rus.md)
- [Current implementation](docs/CURRENT_STATE.md)
- [Domain rules](docs/DOMAIN_RULES.md)
- [Architecture decisions](docs/adr/README.md)
- [Performance baseline](docs/PERFORMANCE_BASELINE.md)
- [Contribution guide](CONTRIBUTING.md)
- [Developer and LLM guide](AGENTS.md)
