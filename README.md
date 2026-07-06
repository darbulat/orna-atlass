# ORNA Atlas

ORNA Atlas is a living sound atlas of natural places: long-form field recordings linked to exact locations, local time, sunrise movement, habitat metadata, and high-quality audio assets.

This repository contains the Sprint 1 production foundation for the first version of ORNA Atlas.

## Core stack

- **API:** FastAPI
- **Database:** PostgreSQL with PostGIS
- **Cache and jobs:** Redis
- **Audio storage:** S3-compatible object storage wrapper
- **Frontend:** Next.js / React, TypeScript, WebGL map/globe layer, audio-first interaction design
- **Primary domain:** locations, audio sessions, dawn line discovery, playback metadata, memberships, and editorial collections

## Local development

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start the stack:

```bash
docker compose up --build
```

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

## Documentation

- [Project architecture](docs/ARCHITECTURE.md)
- [Implementation plan (RU)](docs/IMPLEMENTATION_PLAN_rus.md)
