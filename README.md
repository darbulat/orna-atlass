# ORNA Atlas

ORNA Atlas is a living sound atlas of natural places: long-form field recordings linked to exact locations, local time, sunrise movement, habitat metadata, and high-quality audio assets.

This repository currently contains the product, frontend, and backend architecture for the first production version of ORNA Atlas.

## Core stack

- **API:** FastAPI
- **Database:** PostgreSQL with PostGIS
- **Cache and jobs:** Redis
- **Audio storage:** S3-compatible object storage
- **Frontend:** Next.js / React, TypeScript, WebGL map/globe layer, audio-first interaction design
- **Primary domain:** locations, audio sessions, dawn line discovery, playback metadata, memberships, and editorial collections

## Documentation

- [Project architecture](docs/ARCHITECTURE.md)
- [Implementation plan (RU)](docs/IMPLEMENTATION_PLAN_rus.md)
