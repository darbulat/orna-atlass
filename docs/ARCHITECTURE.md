# ORNA Atlas project architecture

## 1. Product goal

ORNA Atlas is a map-first audio platform where every recording is attached to a real natural location. The user explores a planet-scale atlas, follows the moving sunrise line, discovers active points, and enters long-form ORNA Sessions: uninterrupted recordings of forests, wetlands, deserts, mountains, coasts, rain, wind, dawn, dusk, and night.

The system must preserve three product principles:

1. **Place before track:** audio is organized around real locations, coordinates, habitat, local time, and field context.
2. **Trust and purity:** every session includes recording provenance, quality flags, human-noise policy, and technical metadata.
3. **Atlas experience:** APIs must support fast map exploration, dawn-line discovery, session playback, and rich editorial presentation.

## 2. Target stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend application | Next.js / React + TypeScript | Atlas UI, session pages, playback shell, membership flows |
| Map and globe rendering | Three.js or MapLibre GL | 3D planet, 2D atlas, dawn terminator, location markers |
| API application | FastAPI | Public API, admin API, auth, domain orchestration |
| Database | PostgreSQL + PostGIS | Source of truth for users, locations, sessions, geo queries, metadata |
| Cache | Redis | Hot map data, session cards, signed URL metadata, rate limits, background job state |
| Object storage | S3-compatible storage | Audio masters, streaming renditions, images, waveform assets, transcripts/annotations |
| Background workers | RQ with Redis broker | Audio processing, waveform generation, metadata extraction, cache warming |
| Migrations | Alembic | Versioned schema evolution |
| Observability | OpenTelemetry + structured logs | Request traces, latency, worker diagnostics, playback URL monitoring |

## 3. High-level system diagram

```mermaid
flowchart LR
    Web[Web client / ORNA Atlas UI] --> API[FastAPI application]
    Mobile[Future mobile app] --> API
    Admin[Editorial admin] --> API

    API --> PG[(PostgreSQL + PostGIS)]
    API --> Redis[(Redis cache)]
    API --> S3[(S3 audio and media storage)]

    API --> Worker[Background workers]
    Worker --> Redis
    Worker --> PG
    Worker --> S3

    S3 --> CDN[CDN]
    CDN --> Web
```

## 4. Frontend architecture

The frontend is a first-class part of ORNA Atlas. The product is not a generic audio catalog; it is an immersive atlas interface where the user discovers recordings through geography, time, light, and sound. The frontend should therefore be designed around rendering performance, audio continuity, and a calm cinematic interaction model.

Recommended frontend stack:

| Area | Recommendation | Notes |
| --- | --- | --- |
| Application framework | Next.js with App Router | Server-rendered editorial pages, client-heavy atlas experience |
| Language | TypeScript | Shared API contracts and safer UI state |
| Styling | Tailwind CSS plus design tokens | Fast implementation with strict visual system |
| 3D globe | Three.js / React Three Fiber | Hero planet, dawn terminator, atmospheric effects |
| 2D map mode | MapLibre GL | Detailed atlas exploration, clustering, viewport queries |
| Data fetching | TanStack Query or SWR | Cache atlas payloads, sessions, collections, playback grants |
| State | Zustand | Global player state, selected location, UI mode |
| Audio | HTMLAudioElement or Web Audio API wrapper | Long-form playback, cross-fades later, waveform sync |
| Animation | Framer Motion | Enter-place transitions, cards, panels, route transitions |
| Testing | Playwright + Vitest | Core journeys and component behavior |

### 4.1 Frontend application layout

Recommended package layout:

```text
web/
  app/
    layout.tsx
    page.tsx
    atlas/
      page.tsx
    sessions/
      [slug]/
        page.tsx
    collections/
      [slug]/
        page.tsx
    about/
      page.tsx
    membership/
      page.tsx
  components/
    atlas/
      AtlasShell.tsx
      GlobeView.tsx
      MapView.tsx
      DawnTerminator.tsx
      LocationMarker.tsx
      LocationDrawer.tsx
    audio/
      GlobalPlayer.tsx
      SessionPlayer.tsx
      WaveformTimeline.tsx
      BirdPartsTimeline.tsx
      PlaybackGrantBoundary.tsx
    sessions/
      SessionHero.tsx
      RecordingIntegrity.tsx
      AnnotationTimeline.tsx
    layout/
      Header.tsx
      Navigation.tsx
      PageTransition.tsx
  lib/
    api/
      client.ts
      atlas.ts
      sessions.ts
      playback.ts
    audio/
      playerStore.ts
      usePlaybackGrant.ts
    geo/
      dawnTerminator.ts
      projections.ts
    design/
      tokens.ts
  tests/
```

### 4.2 Main frontend routes

| Route | Purpose | Rendering mode |
| --- | --- | --- |
| `/` | Cinematic landing page with live globe, current dawn, featured sessions | Server shell + client globe |
| `/atlas` | Full interactive atlas with globe/map toggle, filters, dawn mode | Client-heavy |
| `/sessions/[slug]` | Deep session page with player, metadata, annotations, integrity notes | Server-rendered content + client player |
| `/collections/[slug]` | Editorial collection pages | Server-rendered |
| `/membership` | Membership value, sign-in, access rules | Server-rendered |
| `/about` | Manifesto, recording principles, ecological commitments | Server-rendered |

### 4.3 Core UI concepts

#### Atlas shell

The atlas shell owns the map/globe viewport, selected location, active time mode, filters, and side panels. It calls `GET /api/v1/atlas/points` for visible points and `GET /api/v1/atlas/dawn/current` for the current dawn experience.

`GET /api/v1/atlas/points` must accept `bbox`, `zoom`, habitat filters, time mode, and a response limit. At low zoom levels the backend may return clusters or aggregate points; at high zoom levels it returns individual locations. The contract must handle the anti-meridian and provide a stable Redis cache key.

#### Dawn terminator

The frontend should render a moving dawn line visually, but the backend remains authoritative for which locations are considered active near dawn. This keeps visual motion smooth while preserving consistent product logic for featured dawn sessions.

#### Enter the place transition

Selecting a point should not feel like opening a track. The interaction should zoom or glide toward the marker, dim surrounding UI, reveal local time and coordinates, and then open a session drawer or route.

#### Global audio player

Playback should continue across route transitions. A global player store should hold current session, playback state, current time, duration, signed URL expiry, and visible mini-player/full-player mode.

The player lifecycle must be explicit: `idle -> requesting_grant -> ready -> playing -> paused -> refreshing_grant -> stalled -> ended -> error`. If a signed URL is about to expire during playback, the frontend moves into `refreshing_grant`, requests a new playback grant, and continues playback without changing user context. The real audio element should live in the root layout/provider; route-level components only control state and subscriptions.

#### Bird parts in the player

The player should show each bird's vocal parts on the recording timeline. These data are not calculated on the frontend: the backend returns intervals, species, confidence, and additional metadata from PostgreSQL. The user should be able to see which bird is audible at a given moment, jump between parts, and filter the timeline by species or confidence level.

#### Recording integrity UI

Each session page should expose provenance and quality data: no loops, no studio layers, human-noise level, microphone setup, recording duration, date, local time, weather, and habitat. This is a core trust feature, not secondary metadata.

### 4.4 Frontend data flow

```mermaid
sequenceDiagram
    participant UI as Frontend UI
    participant API as FastAPI
    participant Redis as Redis cache
    participant PG as PostgreSQL
    participant S3 as S3/CDN

    UI->>API: GET /api/v1/atlas/dawn/current
    API->>Redis: Read atlas:dawn:now
    Redis-->>API: Cached dawn payload
    API-->>UI: Dawn locations + session cards

    UI->>API: POST /api/v1/sessions/{id}/playback-grants
    API->>PG: Check session access and membership
    API->>S3: Create signed playback URL
    API-->>UI: Playback grant + signed URL
    UI->>S3: Stream audio through CDN or signed URL
```

### 4.5 Frontend performance requirements

Initial targets:

- Landing page largest contentful paint under 2.5 seconds on a typical broadband connection.
- Atlas first usable interaction under 3 seconds after route load.
- Globe and map interactions at 45-60 FPS on modern laptops.
- Audio start after playback grant under 1 second when S3/CDN latency is normal.
- Session page metadata should render before the audio player requests protected media.

Optimization priorities:

1. Lazy-load the 3D globe and heavy map libraries.
2. Use simplified marker payloads for atlas views.
3. Keep high-resolution imagery behind responsive image sizes.
4. Defer waveform and annotation loading until the player is visible.
5. Avoid blocking route transitions on signed playback URL generation.

### 4.6 Frontend accessibility and fallback requirements

The atlas should be immersive but not dependent on WebGL-only interaction. Required fallbacks:

- A list mode for locations and collections as a first-class `/atlas?view=list` option, not a secondary fallback.
- Keyboard-accessible cards, markers, drawers, and player controls.
- Reduced-motion mode for globe transitions and dawn-line animation.
- Text equivalents for location, time, weather, and recording integrity.
- Basic playback support without the full 3D globe.

### 4.7 Frontend-to-backend contract

Use generated TypeScript types from the OpenAPI schema produced by FastAPI. The frontend should not duplicate API shapes manually. Recommended flow:

1. FastAPI exposes `/openapi.json`.
2. CI generates `web/lib/api/generated.ts`.
3. Frontend API wrappers convert generated DTOs into UI-friendly view models only where necessary.
4. Breaking API changes are caught by TypeScript and frontend tests.

## 5. Backend service boundaries

The first version can be a modular monolith. FastAPI should be split by domain modules instead of by technical layers only. This keeps deployment simple while preserving clear boundaries for future service extraction.

Recommended package layout:

```text
orna_atlas/
  app/
    main.py
    core/
      config.py
      security.py
      logging.py
      errors.py
    db/
      session.py
      base.py
      migrations/
    modules/
      auth/
      users/
      locations/
      sessions/
      media/
      atlas/
      collections/
      memberships/
      admin/
    workers/
      audio_pipeline.py
      cache_warming.py
    integrations/
      s3.py
      redis.py
      sunrise.py
      bird_analysis.py
    tests/
```

Each domain module should use the same internal layers:

```text
modules/<domain>/
  router.py        # HTTP endpoints only
  schemas.py       # Pydantic request/response DTOs
  service.py       # use cases and orchestration
  repository.py    # database queries
  models.py        # SQLAlchemy models
  permissions.py   # authorization decisions
  events.py        # domain events and worker triggers
```

Admin endpoints must not bypass domain services. `modules/admin` contains only HTTP wrappers and admin-specific schemas; publishing, archiving, asset uploads, and audit events are executed through the relevant domain services.

## 6. Domain model

### 6.1 Main entities

#### User

Represents listener, member, admin, editor, or field recordist.

Important fields:

- `id`
- `email`
- `display_name`
- `role`: listener, member, editor, admin, recordist
- `membership_status`
- `created_at`
- `last_login_at`

#### Location

A real geographic place in the atlas.

Important fields:

- `id`
- `slug`
- `title`
- `subtitle`
- `country`
- `region`
- `coordinates`: PostGIS geography point
- `elevation_m`
- `habitat_type`: forest, wetland, mountain, coast, desert, tundra, river, grassland
- `timezone`
- `description`
- `conservation_notes`
- `is_public`
- `created_at`
- `updated_at`

#### AudioSession

A continuous recording connected to a location.

Important fields:

- `id`
- `location_id`
- `slug`
- `title`
- `format`: dawn, day, dusk, night, rain, wind, marsh, forest, ocean, expedition
- `starts_at_utc`
- `starts_at_local`
- `duration_seconds`
- `processing_status`: uploaded, processing, ready, failed
- `publication_status`: draft, published, unpublished, archived
- `access_policy`: public_preview, members_only, private
- `human_noise_level`: none_detected, minimal, present, unknown
- `purity_notes`
- `weather_summary`
- `temperature_c`
- `wind_mps`
- `humidity_percent`
- `moon_phase`
- `is_featured`
- `is_public`

The technical recording lifecycle and editorial publication lifecycle must be separate. `processing_status` represents media pipeline readiness, `publication_status` represents editorial state, and `access_policy` represents playback access rules. A session can be `ready` but not `published`, and it can be published as a public preview or members-only content.

#### MediaAsset

A file in S3 related to a session or location.

Important fields:

- `id`
- `owner_type`: location, session, collection
- `owner_id`
- `asset_type`: audio_master, audio_stream, image, waveform, spectrogram, ambient_video
- `s3_bucket`
- `s3_key`
- `content_type`
- `size_bytes`
- `duration_seconds`
- `checksum`
- `processing_status`
- `created_at`

Polymorphic ownership through `owner_type` + `owner_id` is acceptable for the MVP, but services must validate owner existence and prevent dangling assets. A stricter future schema can replace this with nullable foreign keys `location_id`, `session_id`, and `collection_id` plus a CHECK constraint that exactly one owner is set.

#### SessionAnnotation

Timeline events inside a session.

Examples: first bird call, rain begins, dawn chorus peak, wind gust, insect layer, distant thunder.

Important fields:

- `id`
- `session_id`
- `offset_seconds`
- `duration_seconds`
- `label`
- `annotation_type`: species, weather, acoustic_event, editorial_note
- `confidence`
- `metadata_json`

#### BirdVocalPart

A detected vocal part of a specific bird within a recording. Part metadata is stored in PostgreSQL and used by the player to render the species timeline. The calculation is performed by an external audio analysis service, while the backend stores the normalized result.

Important fields:

- `id`
- `session_id`
- `species_code`
- `species_common_name`
- `species_scientific_name`
- `starts_at_seconds`
- `ends_at_seconds`
- `confidence`
- `channel`
- `call_type`: song, call, alarm, drumming, unknown
- `analysis_provider`
- `analysis_model_version`
- `metadata_json`
- `created_at`

#### Collection

Editorial grouping of locations or sessions.

Examples: Dawn Archive, Wetlands, Northern Forests, Rain After Dusk, No Human Noise.

Important fields:

- `id`
- `slug`
- `title`
- `description`
- `cover_asset_id`
- `is_public`
- `sort_order`

Collection membership should be stored in separate `collection_locations` and `collection_sessions` tables with `sort_order`, so editorial ordering and mixed collections do not require duplicating entities.

#### PlaybackGrant

Short-lived access record for protected audio playback.

Important fields:

- `id`
- `user_id`
- `session_id`
- `expires_at`
- `signed_url_hash`
- `created_at`

## 7. PostgreSQL schema strategy

Use PostgreSQL as the source of truth. Add PostGIS for location and distance queries.

Recommended extensions:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

Sensitive ecological objects need separate coordinate fields:

- `exact_coordinates`: exact point, visible only to admins/editors with permission.
- `public_coordinates`: public point, which may be approximate.
- `coordinate_visibility`: `exact_public`, `approximate_public`, `hidden_public`.
- `sensitivity_level`: `none`, `low`, `medium`, `high`.

Public atlas APIs return only `public_coordinates` when `coordinate_visibility` is not `exact_public`.

Core indexing strategy:

- GiST index on `locations.coordinates` for map viewport and distance queries.
- B-tree indexes on slugs, status fields, and foreign keys.
- Composite indexes for public atlas queries, for example `(is_public, habitat_type)`.
- Trigram indexes for location search by title, region, and country.
- Partial indexes for published sessions only.

## 8. Redis usage

Redis should not be a source of truth. Use it for speed and coordination.

Recommended keys:

| Key pattern | TTL | Purpose |
| --- | --- | --- |
| `atlas:viewport:{hash}` | 30-120s | Cached map points for a viewport and zoom level |
| `atlas:dawn:now` | 30-60s | Current dawn-line candidates |
| `session:card:{session_id}` | 5-30m | Public card payload for high-traffic pages |
| `playback:url:{session_id}:{user_id}` | 1-10m | Cached signed playback metadata |
| `rate:user:{user_id}` | short | API rate limiting |
| `job:audio:{asset_id}` | until completion | Audio processing job state |

Invalidation rules:

- Publishing or hiding a location/session invalidates affected session cards, viewport caches, and nearby dawn cache entries.
- Changing coordinates or timezone invalidates viewport, dawn, and search projections.
- Replacing media assets invalidates session detail, waveform/spectrogram payloads, and CDN objects when public.
- Revoking membership or changing access policy invalidates playback grant cache for affected users/sessions.

## 9. S3 object storage design

Use private buckets for masters and controlled public/CDN access for derived assets.

Recommended bucket layout:

```text
orna-audio-private/
  sessions/{session_id}/master/original.wav
  sessions/{session_id}/processed/stream_320.mp3
  sessions/{session_id}/processed/stream_hls/master.m3u8
  sessions/{session_id}/processed/waveform.json
  sessions/{session_id}/processed/spectrogram.webp

orna-media-public/
  locations/{location_id}/cover.webp
  locations/{location_id}/gallery/{asset_id}.webp
  collections/{collection_id}/cover.webp
```

Access rules:

- Audio masters are always private.
- Stream renditions can be private with signed URLs for members-only sessions.
- Public previews can be distributed through CDN.
- S3 keys are stored in `media_assets`; never store full signed URLs in PostgreSQL.

Long-form playback must be designed as rendition-based from day one. The MVP may start playback from `stream_320.mp3`, but the asset model, API, and storage layout must remain compatible with HLS (`stream_hls/master.m3u8`) without a domain migration.

## 10. Audio processing pipeline

When an editor uploads a new master recording:

1. API creates `MediaAsset` with `processing_status=uploaded`.
2. Worker validates file type, checksum, duration, and loudness range.
3. Worker extracts technical metadata.
4. Worker creates streaming renditions.
5. Worker generates waveform and optional spectrogram.
6. Worker sends the recording or a derived audio segment to the external bird analysis service.
7. Worker stores detected `BirdVocalPart` records in PostgreSQL.
8. Worker stores derived files in S3.
9. Worker updates `AudioSession.processing_status=ready` if required assets exist; publication remains a separate editorial action.
10. Worker warms Redis cache for session cards, bird parts payloads, and atlas views.

Bird analysis service integration:

- The external service is a compute source, not a source of truth.
- The backend stores normalized bird parts in `bird_vocal_parts`.
- Re-analysis of the same recording should update parts by `analysis_provider` and `analysis_model_version` idempotently.
- The player reads parts only through the ORNA Atlas API, not directly from the external service.

Failure handling:

- Processing steps must be idempotent.
- Failed jobs should store `error_code`, `error_message`, and retry count.
- Masters must never be deleted automatically after processing failure.
- Bird analysis failure should not block session publication if audio and required media assets are ready; in that case, the UI shows the recording without the bird parts timeline.

Processing state must be stored not only in Redis but also in a PostgreSQL `processing_jobs` table: `id`, `asset_id`, `job_type`, `status`, `attempt_count`, `error_code`, `error_message`, `started_at`, `finished_at`, `created_at`. Redis is used for operational state; PostgreSQL is used for audit, retries, and diagnostics.

Each pipeline step must have an idempotency rule: deterministic S3 keys for derived files, upserting analysis results by `session_id`, `analysis_provider`, and `analysis_model_version`, and safe waveform/rendition regeneration.

## 11. Dawn-line and local-time architecture

The dawn experience should be calculated from coordinates, date, and timezone. The backend should expose API-ready dawn candidates without forcing the frontend to calculate everything.

Recommended approach:

- Store each location timezone explicitly.
- Calculate sunrise/sunset and civil dawn windows using a deterministic astronomy library or internal service.
- Cache current dawn candidates in Redis.
- Update dawn cache every 1-5 minutes.
- Explicitly define the dawn window, for example `near_dawn_window_minutes_before=45` and `near_dawn_window_minutes_after=30`, so frontend and backend share the same `is_near_dawn_now` semantics.
- Derive a location timezone from coordinates at creation, allow editor override, validate it when coordinates change, and audit changes.

Important API concepts:

- `current_dawn_locations`: points where local dawn is happening now or within a configurable window.
- `next_dawn_locations`: upcoming points ordered by dawn start time.
- `follow_dawn`: ordered list of locations near the current terminator line.

## 12. API design

### Public atlas endpoints

```http
GET /api/v1/atlas/points
GET /api/v1/atlas/dawn/current
GET /api/v1/atlas/dawn/follow
GET /api/v1/locations/{slug}
GET /api/v1/sessions/{slug}
GET /api/v1/collections
GET /api/v1/collections/{slug}
GET /api/v1/search?q={query}
```

### Playback endpoints

```http
POST /api/v1/sessions/{session_id}/playback-grants
GET /api/v1/sessions/{session_id}/waveform
GET /api/v1/sessions/{session_id}/annotations
GET /api/v1/sessions/{session_id}/bird-parts
```

### Auth and membership endpoints

```http
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET /api/v1/users/me
GET /api/v1/memberships/me
```

### Admin endpoints

```http
POST /api/v1/admin/locations
PATCH /api/v1/admin/locations/{id}
POST /api/v1/admin/sessions
PATCH /api/v1/admin/sessions/{id}
POST /api/v1/admin/sessions/{id}/assets
POST /api/v1/admin/collections
PATCH /api/v1/admin/collections/{id}
```

List endpoints (`collections`, `search`, atlas views) must support `limit` and cursor/page parameters. Public detail endpoints may use `slug`, but protected playback mutations must use stable `session_id` values obtained from detail responses.

Standard API error shape:

```json
{
  "error": {
    "code": "playback_membership_required",
    "message": "Membership is required to play this session.",
    "request_id": "req_01JABC"
  }
}
```

## 13. Response examples

### Atlas point

```json
{
  "id": "loc_01HXYZ",
  "slug": "bialowieza-forest",
  "title": "Białowieża Forest",
  "country": "Belarus / Poland",
  "lat": 52.7001,
  "lng": 23.8662,
  "timezone": "Europe/Warsaw",
  "habitat_type": "old_growth_forest",
  "active_session": {
    "id": "ses_01HXYZ",
    "slug": "belarus-dawn",
    "title": "Belarus Dawn",
    "format": "dawn",
    "duration_seconds": 20820,
    "human_noise_level": "none_detected"
  },
  "dawn_state": {
    "is_near_dawn_now": true,
    "local_time": "05:42",
    "sunrise_at_local": "05:51"
  }
}
```

### Session detail

```json
{
  "id": "ses_01HXYZ",
  "slug": "belarus-dawn",
  "title": "Belarus Dawn",
  "location": {
    "title": "Białowieża Forest",
    "country": "Belarus / Poland",
    "coordinates": [23.8662, 52.7001]
  },
  "duration_seconds": 20820,
  "format": "dawn",
  "recording_integrity": {
    "human_noise_level": "none_detected",
    "post_processing": "No loops, no studio layers, no artificial ambience",
    "microphone_setup": "ORTF field pair",
    "recordist_notes": "Unattended recording before sunrise after light rain."
  }
}
```

### Bird parts

```json
{
  "session_id": "ses_01HXYZ",
  "analysis_provider": "external-bird-audio-service",
  "analysis_model_version": "2026-06",
  "parts": [
    {
      "id": "bird_part_01JABC",
      "species_code": "turdus_merula",
      "species_common_name": "Common blackbird",
      "species_scientific_name": "Turdus merula",
      "starts_at_seconds": 184.2,
      "ends_at_seconds": 191.8,
      "confidence": 0.93,
      "call_type": "song"
    }
  ]
}
```

## 14. Authentication and authorization

Recommended first-version model:

- JWT access token with short expiration.
- Refresh token stored server-side and issued to the client through secure httpOnly cookies with rotation.
- Role-based access control for admin/editor operations.
- Membership-based playback rules and entitlement checks for protected sessions.

Authorization rules:

- Public users can browse public atlas points and public previews.
- Members can request signed playback grants for members-only sessions.
- Editors can create and edit draft locations and sessions.
- Admins can publish, archive, and manage users.

## 15. Performance requirements

Initial targets:

- Atlas point viewport response: under 150 ms from cache, under 500 ms from database.
- Session detail response: under 250 ms from cache, under 600 ms from database.
- Playback grant creation: under 300 ms excluding S3 latency.
- Dawn cache refresh: every 1-5 minutes.

Optimization priorities:

1. Cache map point payloads by viewport and zoom.
2. Precompute lightweight session cards.
3. Use CDN for images, waveform assets, and public previews.
4. Keep signed audio URL generation server-side.
5. Avoid sending heavy session metadata in atlas point responses.

## 16. Security and privacy

Required controls:

- Private S3 bucket for source audio.
- Signed URLs for protected playback.
- Strict admin role checks.
- Rate limiting on auth, search, and playback grant endpoints.
- Input validation with Pydantic schemas.
- No secrets in source code.
- Structured audit events for publishing, asset uploads, and admin changes.

Sensitive ecological locations require coordinate obfuscation through `coordinate_visibility`. Some protected habitats expose approximate coordinates or are hidden from the public atlas while exact coordinates remain visible only to admins and authorized editors.

## 17. Environment variables

```text
APP_ENV=local
APP_SECRET_KEY=change-me
DATABASE_URL=postgresql+asyncpg://orna:orna@postgres:5432/orna_atlas
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_REGION=eu-central-1
S3_PRIVATE_BUCKET=orna-audio-private
S3_PUBLIC_BUCKET=orna-media-public
CDN_BASE_URL=https://cdn.orna.example
JWT_ACCESS_TOKEN_TTL_SECONDS=900
JWT_REFRESH_TOKEN_TTL_SECONDS=2592000
```

## 18. Recommended implementation phases

### Phase 1: Architecture foundation

- Next.js frontend skeleton.
- FastAPI app skeleton.
- PostgreSQL + PostGIS setup.
- Redis connection.
- S3 integration wrapper.
- Alembic migrations.
- Health checks.

### Phase 2: Content model and minimal admin

- Locations CRUD.
- Sessions CRUD.
- Media assets model.
- Admin upload shell.
- Publication/access policy lifecycle.
- Audit events for publishing and asset changes.

### Phase 3: Public session and audio foundation

- Session detail endpoint.
- Session page frontend with global player.
- Playback lifecycle and grant refresh.
- S3 private master storage.
- Streaming rendition model.

### Phase 4: Atlas experience

- Public atlas points endpoint.
- Atlas frontend shell with `/atlas?view=list` fallback.
- Backend clustering/viewport contract.
- Search.

### Phase 5: Audio pipeline

- Background processing worker.
- Persistent `processing_jobs`.
- Waveform generation.
- Streaming renditions.
- External bird analysis service integration.
- Store `BirdVocalPart` metadata in PostgreSQL.

### Phase 6: Dawn experience

- Sunrise and local-time calculations.
- Current dawn endpoint.
- Follow-dawn endpoint.
- Frontend dawn terminator rendering.
- Redis cache warming.

### Phase 7: Membership and protected playback

- Auth.
- User roles.
- Membership state and entitlements.
- Signed playback grants.
- Rate limits and audit logs.

### Phase 8: Editorial polish

- Collections.
- Featured sessions.
- Recording integrity display.
- Bird parts timeline in the session player.
- Protected-coordinate mode for sensitive locations.

## 19. Accepted decisions

1. Use a rendition-based model for long-form playback; the MVP may start with an MP3 rendition, but storage/API must be HLS-ready.
2. Use a hybrid globe/map interface for the first release with a required list fallback.
3. Use RQ as the worker framework.
4. Use internal JWT auth with server-side refresh-token rotation through secure httpOnly cookies.
5. Exact coordinates are public only for `coordinate_visibility=exact_public`; sensitive locations use approximate or hidden public coordinates.
6. Memberships are implemented internally through membership state and entitlements, with room for a future billing provider integration.
