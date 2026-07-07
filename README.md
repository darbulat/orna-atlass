# ORNA Atlas

ORNA Atlas is a living sound atlas of natural places: long-form field recordings linked to exact locations, local time, sunrise movement, habitat metadata, and high-quality audio assets.

This repository contains the Sprint 6 production foundation for the first version of ORNA Atlas.

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

The compose stack starts the API, frontend, PostgreSQL, Redis, and the audio processing worker.

3. Add local atlas test data:

```bash
docker compose exec api python -m orna_atlas.app.seed_atlas
```

4. Open the frontend at <http://localhost:3000> and the API at <http://localhost:8000>.

## Backend checks

```bash
pip install '.[dev]'
ruff check .
pytest
alembic upgrade head
alembic revision -m "empty migration"
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
```

## Documentation

- [Project architecture](docs/ARCHITECTURE.md)
- [Implementation plan (RU)](docs/IMPLEMENTATION_PLAN_rus.md)
