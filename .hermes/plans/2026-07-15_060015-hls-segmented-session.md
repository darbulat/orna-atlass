# Segmented Session HLS Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Allow one ORNA Atlas recording session to use six ordered WAV objects already stored in S3, process them without creating a combined WAV, and play them as one private, seekable HLS VOD stream.

**Architecture:** Add an explicit `RecordingSegment` aggregate beneath `RecordingSession`; each segment points to an immutable source `MediaAsset` and has an ordered timeline offset. A session-level HLS pipeline materializes and transcodes one WAV at a time into a single versioned fMP4/AAC HLS rendition, uploads immutable objects under one S3 prefix, verifies the complete inventory, then atomically activates the manifest asset. Playback uses an authenticated same-origin HLS media gateway: a grant sets a short-lived HttpOnly cookie, the manifest contains relative gateway URLs, and each init/media request validates the cookie then redirects to a short-lived S3 URL.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Alembic, RQ/Redis, boto3/S3/MinIO, ffmpeg/ffprobe, Prometheus, Next.js/React, hls.js, Playwright, pytest.

---

## Main-branch review baseline

Re-reviewed after switching to `main` and fast-forwarding from `origin/main` to commit `f921e6f` on 2026-07-15. The worktree contains only the untracked `.hermes/` plan directory after the pull.

The current implementation changes the plan in these important ways:

- `MediaAsset` has partial unique indexes for one active source and one active `streaming_rendition` per session; segmented sources require an explicit migration rather than reuse of `create_asset_for_session()`.
- `ProcessingJob` is asset-scoped (`asset_id NOT NULL`) and only accepts `audio_pipeline`; use a separate session-scoped HLS job model rather than attaching the job to an arbitrary segment.
- `process_media_asset()` creates a copied-WAV rendition and runs BirdNET. Segmented HLS is a parallel orchestration path, not conditional complexity inside that legacy function.
- `StorageCleanupJob` deletes one key. HLS cleanup needs an inventory-based prefix cleanup job and must not overload that contract.
- `ObjectStorageClient` already covers the basic S3 operations; additions should be narrow typed inventory helpers.
- `Dockerfile.worker` already installs ffmpeg. Add readiness/version verification, not another install path.
- Existing direct-file playback remains an explicit compatibility branch.
- Schema changes must regenerate `web/openapi.json` and `web/lib/api/generated.ts` using the existing frontend script.

---

## Scope and accepted decisions

### In scope

- One logical recording session with an ordered list of WAV source segments.
- Existing S3 objects are registered by managed `sessions/` keys; they are not uploaded again.
- Continuous timeline; `start_offset_seconds` is calculated from authoritative ffprobe durations.
- One audio-only HLS VOD rendition per source revision set.
- AAC-LC, 48 kHz, source channel count capped at stereo, 160 kbit/s for stereo (96 kbit/s mono), 10-second fMP4 segments.
- BirdNET remains per source WAV; its local intervals are shifted by the segment offset.
- Private/public/members-only authorization remains fail-closed.
- Existing single-file sessions remain playable during migration.

### Out of scope for the first release

- Adaptive bitrate variants and a master playlist.
- Live HLS.
- User-selectable codecs/bitrates.
- Crossfade or invented silence between non-contiguous recordings.
- Public S3 ACLs.
- CDN signed cookies; the gateway boundary is designed so it can later be replaced by a CDN.

### Product invariants

1. Segment order and offsets are immutable within a processing revision.
2. A session-level HLS rendition becomes active only after every referenced object is uploaded and verified.
3. A failed retry cannot replace the last ready rendition.
4. The manifest and segments use versioned immutable keys; publish the manifest last.
5. Playback is denied when the session is unauthorized, rendition is not ready, inventory is incomplete, or storage is unavailable.
6. Public DTOs expose sequence, duration, and readiness but never S3 keys or exact coordinates.
7. Repositories never call `commit()`; services own transaction boundaries.
8. Only one active HLS build exists for a session source-set fingerprint.

---

## Target data and storage shape

```text
recording_sessions
  └── recording_segments
        ├── sequence_number
        ├── start_offset_ms
        ├── duration_ms
        └── source_asset_id -> media_assets(kind=source_audio)

media_assets(kind=hls_rendition)
  storage_key = sessions/{session_id}/hls/{rendition_id}/index.m3u8
  metadata = {
    "format": "hls-fmp4-aac",
    "source_fingerprint": "sha256:...",
    "init_key": ".../init.mp4",
    "segment_prefix": ".../",
    "segment_count": 4320,
    "inventory_sha256": "...",
    "target_duration_seconds": 10
  }
```

Suggested playlist:

```m3u8
#EXTM3U
#EXT-X-VERSION:7
#EXT-X-TARGETDURATION:10
#EXT-X-PLAYLIST-TYPE:VOD
#EXT-X-MAP:URI="init.mp4"
#EXTINF:10.000,
segment_000000.m4s
...
#EXT-X-ENDLIST
```

The stored S3 manifest stays relative and contains no credentials. The API gateway parses and validates it, then serves a rewritten gateway manifest whose object URIs remain relative beneath the authenticated rendition route.

---

### Task 1: Record the durable HLS and authorization decision

**Objective:** Make the segmented-source, immutable-HLS, authenticated-gateway design explicit before schema/code changes.

**Files:**
- Create: `docs/adr/0005-segmented-hls-playback.md`
- Modify: `docs/adr/README.md`
- Modify: `docs/DOMAIN_RULES.md`

**Steps:**

1. Write ADR status `Accepted`, context, decision, consequences, rejected alternatives, and rollback path.
2. Explicitly reject public HLS prefixes and embedding thousands of presigned URLs in manifests.
3. Add domain rules for segment ordering, source-set fingerprinting, full-inventory verification, manifest-last upload, and fail-closed gateway access.
4. Review wording against `docs/adr/0002-fail-closed-playback.md`, `0003-versioned-media-assets.md`, and `0004-service-owned-transactions.md`.
5. Commit:

```bash
git add docs/adr/0005-segmented-hls-playback.md docs/adr/README.md docs/DOMAIN_RULES.md
git commit -m "docs: define segmented HLS playback architecture"
```

---

### Task 2: Add recording-segment and HLS domain types

**Objective:** Establish typed values and validation before persistence.

**Files:**
- Modify: `orna_atlas/app/core/domain_types.py`
- Modify: `orna_atlas/app/modules/media/schemas.py`
- Test: `orna_atlas/app/tests/test_hls_segment_schemas.py`

**Step 1: Write failing schema tests**

Cover:

- sequence must be positive;
- `storage_key` must remain under `sessions/` via the existing service validator;
- manifest accepts one or more ordered items;
- duplicate sequence numbers are rejected;
- null required fields are rejected;
- admin reads may expose `storage_key`; public reads may not;
- `MediaKind.HLS_RENDITION` serializes as `hls_rendition`.

Target contracts:

```python
class RecordingSegmentCreate(BaseModel):
    sequence_number: int = Field(ge=1)
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str = "audio/wav"
    checksum: str | None = None

class RecordingSegmentBatchCreate(BaseModel):
    segments: list[RecordingSegmentCreate] = Field(min_length=1, max_length=100)
    enqueue_processing: bool = True
```

**Step 2: Verify RED**

```bash
python -m pytest orna_atlas/app/tests/test_hls_segment_schemas.py -q
```

Expected: collection/import failures because types do not exist.

**Step 3: Implement minimal enums/schemas**

Add `hls_rendition` to `MediaKind`; add create/read/admin-read schemas and deterministic duplicate/order validation.

**Step 4: Verify GREEN**

```bash
python -m pytest orna_atlas/app/tests/test_hls_segment_schemas.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orna_atlas/app/core/domain_types.py orna_atlas/app/modules/media/schemas.py orna_atlas/app/tests/test_hls_segment_schemas.py
git commit -m "feat: define segmented HLS contracts"
```

---

### Task 3: Persist ordered recording segments

**Objective:** Store multiple source assets per logical session without weakening version/integrity rules.

**Files:**
- Modify: `orna_atlas/app/modules/media/models.py`
- Modify: `orna_atlas/app/modules/sessions/models.py`
- Create: `orna_atlas/app/migrations/versions/0013_segmented_hls_sources.py`
- Test: `tests/integration/test_segmented_hls_migration.py`

**Schema:**

```text
recording_segments:
  id uuid pk
  session_id uuid not null fk recording_sessions on delete cascade
  source_asset_id uuid not null unique fk media_assets on delete restrict
  sequence_number integer not null check > 0
  start_offset_ms bigint null check >= 0
  duration_ms bigint null check > 0
  source_revision integer not null check > 0
  created_at timestamptz not null
  unique(session_id, sequence_number, source_revision)

hls_processing_jobs:
  id uuid pk
  session_id uuid not null fk recording_sessions on delete cascade
  source_fingerprint varchar(128) not null
  status / attempt_count / stage_states / request_id / queue_job_id
  error fields / heartbeats / timestamps
  partial unique(session_id, source_fingerprint) where status in ('queued','running')

hls_cleanup_jobs:
  id uuid pk
  rendition_asset_id uuid nullable fk media_assets on delete set null
  manifest_key varchar(512) not null unique
  inventory_key varchar(512) not null
  status / lease / retry / retention / error / timestamps
```

Migration actions:

1. Add `hls_rendition` to `ck_media_assets_kind`.
2. Replace `uq_media_assets_active_source` with uniqueness suitable for legacy unsegmented masters only. Preferred predicate: active source uniqueness applies only when `metadata->>'recording_segment_id' IS NULL`; segmented sources are made unique by `recording_segments.source_asset_id` and sequence constraints.
3. Keep `uq_media_assets_active_rendition` for legacy `streaming_rendition`; add a separate active `hls_rendition` partial unique index per session.
4. Create dedicated session-scoped HLS job and inventory-based prefix-cleanup tables; do not make legacy `ProcessingJob.asset_id` nullable or change single-key `StorageCleanupJob` semantics.
5. Do not backfill legacy sessions as segments; preserve their current playback path.
6. Downgrade is supported only when no segment/HLS feature data exists. Abort clearly instead of silently deleting user data; test successful empty downgrade and guarded refusal against disposable PostgreSQL.

**TDD/verification:**

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration/test_segmented_hls_migration.py -q
alembic upgrade head
alembic downgrade 0012
alembic upgrade head
```

Assertions: duplicate sequence fails, negative offset fails, duplicate source linkage fails, six segmented sources coexist, legacy active-source uniqueness still holds, one active HLS rendition per session.

**Commit:**

```bash
git add orna_atlas/app/modules/media/models.py orna_atlas/app/modules/sessions/models.py orna_atlas/app/migrations/versions/0013_segmented_hls_sources.py tests/integration/test_segmented_hls_migration.py
git commit -m "feat: persist ordered recording segments"
```

---

### Task 4: Add S3 object metadata and safe range primitives

**Objective:** Support registration, inventory verification, and later gateway redirects without exposing raw boto3 calls in services.

**Files:**
- Modify: `orna_atlas/app/integrations/s3.py`
- Test: `orna_atlas/app/tests/test_s3_storage.py`
- Test: `tests/integration/test_s3_storage_integration.py`

**Step 1: Add failing tests** for:

- `head_object()` returning size, ETag, content type, and metadata;
- prefix inventory listing with pagination;
- object existence in explicit bucket;
- proper propagation of non-404 S3 failures;
- presigning an immutable HLS child key.

**Step 2: Add typed result:**

```python
@dataclass(frozen=True)
class ObjectMetadata:
    bucket: str
    key: str
    size_bytes: int
    etag: str | None
    content_type: str | None
```

Add `head_object_metadata()` and paginated `list_objects()` to `ObjectStorageClient`. Do not add a generic public-prefix method.

**Step 3: Run:**

```bash
python -m pytest orna_atlas/app/tests/test_s3_storage.py -q
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration/test_s3_storage_integration.py -q
```

**Step 4: Commit:**

```bash
git add orna_atlas/app/integrations/s3.py orna_atlas/app/tests/test_s3_storage.py tests/integration/test_s3_storage_integration.py
git commit -m "feat: add verified S3 inventory primitives"
```

---

### Task 5: Register a batch of existing S3 WAV segments atomically

**Objective:** Let an admin attach the six existing objects to one session without uploading/copying them.

**Files:**
- Modify: `orna_atlas/app/modules/media/repository.py`
- Modify: `orna_atlas/app/modules/media/service.py`
- Modify: `orna_atlas/app/modules/admin/router.py`
- Test: `orna_atlas/app/tests/test_segment_registration.py`

**Endpoint:**

```http
POST /api/v1/admin/sessions/{session_id}/recording-segments
Idempotency-Key: <uuid>
```

**Service sequence:**

1. Lock the recording session.
2. Validate all keys through the existing managed `sessions/` namespace rule.
3. Require each object to exist in the configured private bucket.
4. Require WAV MIME/extension for this release; do not trust client size/duration.
5. Create all six source assets and segment rows in one transaction.
6. Persist S3-reported size/ETag; mark duration/offset unknown until probe.
7. Return the existing batch for a repeated idempotency key or identical source fingerprint.
8. Enqueue one session HLS job only after commit.
9. On any S3 error, roll back all records and return a typed service-unavailable error.

**Tests:** unauthorized caller, arbitrary bucket/key rejected, missing object fails closed, partial DB writes roll back, duplicate sequence rejected, identical replay is idempotent, six valid keys persist in order, no S3 key appears in public DTO.

```bash
python -m pytest orna_atlas/app/tests/test_segment_registration.py -q
```

**Commit:**

```bash
git add orna_atlas/app/modules/media/repository.py orna_atlas/app/modules/media/service.py orna_atlas/app/modules/admin/router.py orna_atlas/app/tests/test_segment_registration.py
git commit -m "feat: register existing S3 recording segments"
```

---

### Task 6: Add a deterministic ffprobe/ffmpeg HLS boundary

**Objective:** Generate one HLS VOD while materializing only one source WAV at a time and never creating a combined WAV.

**Files:**
- Create: `orna_atlas/app/modules/media/hls.py`
- Create: `orna_atlas/app/tests/test_hls_transcoder.py`
- Create: `orna_atlas/app/tests/fixtures/audio/README.md`

**Design:**

- Use `subprocess.run`/`Popen` argument arrays; never `shell=True`.
- Resolve `ffmpeg` and `ffprobe` with `shutil.which`; fail with a typed configuration error.
- Probe each WAV first and reject missing audio, non-positive duration, unsupported channel count, or corrupt data.
- Normalize every input to AAC-LC/fMP4. Do not use stream copy.
- Transcode each source independently into temporary fMP4 HLS, upload and verify its normalized objects, delete that source WAV and local output, then continue to the next source.
- Assemble the final playlist from parsed child playlists, inserting `#EXT-X-DISCONTINUITY` and a source-specific `#EXT-X-MAP` at every boundary. Renumber all init/media filenames under the immutable rendition prefix.
- Do not use ffmpeg's concat demuxer in production: it requires all paths to remain available and defeats the one-source-at-a-time disk bound.
- Rename output media files deterministically (`segment_000000.m4s`, etc.).
- Parse the generated playlist; never accept absolute paths, `..`, URI schemes, keys, or encryption tags.

**Per-source command profile represented as an argument list:**

```text
ffmpeg -nostdin -hide_banner -loglevel error -y
  -i source.wav -map 0:a:0 -vn
  -c:a aac -profile:a aac_low -b:a <96k|160k> -ar 48000 -ac <1|2>
  -f hls -hls_time 10 -hls_playlist_type vod
  -hls_segment_type fmp4 -hls_fmp4_init_filename init_<source>.mp4
  -hls_flags independent_segments+temp_file
  -hls_segment_filename source_segment_%06d.m4s source_index.m3u8
```

**Tests:** use tiny generated WAV fixtures, paths with spaces, mono/stereo normalization, corrupt WAV rejection, deterministic ordering, VOD/endlist, relative URI validation, no giant combined WAV, subprocess cancellation, stderr truncation.

```bash
python -m pytest orna_atlas/app/tests/test_hls_transcoder.py -q
```

Expected: PASS only when local ffmpeg is installed; otherwise mark with an explicit skip marker used only for developer environments, not CI worker-image checks.

**Commit:**

```bash
git add orna_atlas/app/modules/media/hls.py orna_atlas/app/tests/test_hls_transcoder.py orna_atlas/app/tests/fixtures/audio/README.md
git commit -m "feat: add bounded HLS transcoder"
```

---

### Task 7: Add the session-level HLS processing job

**Objective:** Build, upload, verify, and atomically activate HLS with retry and recovery semantics.

**Files:**
- Modify: `orna_atlas/app/modules/media/models.py`
- Modify: `orna_atlas/app/modules/media/repository.py`
- Modify: `orna_atlas/app/modules/media/service.py`
- Modify: `orna_atlas/app/workers/audio_pipeline.py`
- Modify: `orna_atlas/app/workers/pipeline_recovery.py`
- Modify: `orna_atlas/app/core/config.py`
- Modify: `orna_atlas/app/migrations/versions/0013_segmented_hls_sources.py`
- Test: `orna_atlas/app/tests/test_hls_pipeline.py`

**Job identity:** introduce a dedicated session-scoped `HlsProcessingJob`, keyed by session and source fingerprint. Do not make legacy `ProcessingJob.asset_id` nullable and do not attach a six-input job to the first source asset.

**Stages:**

```text
source_verify
probe
segment_offsets
transcode
inventory_upload
inventory_verify
manifest_upload
manifest_verify
activate
bird_analysis (per source, independently retryable)
```

**Source fingerprint:** SHA-256 over ordered tuples of `(source_asset_id, revision, checksum-or-etag)`. Store it on the job and rendition. Before activation, lock and recompute; if changed, mark the build superseded.

**Upload protocol:**

1. Create inactive `hls_rendition` with immutable rendition UUID.
2. Upload `init*.mp4` and `.m4s` files with correct content types and cache headers.
3. Persist a bounded inventory summary and SHA-256; do not store thousands of keys in a DB JSON field.
4. Verify exact count and size/ETag for every local inventory entry against S3.
5. Upload `index.m3u8` last as `application/vnd.apple.mpegurl` with no-cache.
6. Verify the manifest object and parse its referenced inventory.
7. Under DB locks, verify the source fingerprint and activate the rendition; archive the prior HLS rendition and schedule durable prefix cleanup after retention.
8. On failure, retain the last successful rendition and mark the incomplete new prefix for cleanup.

**Configuration:** bitrate, sample rate, channels policy, HLS duration, ffmpeg timeout, max input duration, and worker temp directory; validate bounds in `Settings` rather than accepting arbitrary API values.

**Tests:** stage persistence, idempotent retry, upload manifest last, one missing segment blocks activation, source replacement supersedes build, previous rendition survives failure, stale job recovery, temporary files removed, no repository commits.

```bash
python -m pytest orna_atlas/app/tests/test_hls_pipeline.py -q
```

**Commit:**

```bash
git add orna_atlas/app/modules/media/models.py orna_atlas/app/modules/media/repository.py orna_atlas/app/modules/media/service.py orna_atlas/app/workers/audio_pipeline.py orna_atlas/app/workers/pipeline_recovery.py orna_atlas/app/core/config.py orna_atlas/app/migrations/versions/0013_segmented_hls_sources.py orna_atlas/app/tests/test_hls_pipeline.py
git commit -m "feat: process segmented sessions into verified HLS"
```

---

### Task 8: Shift BirdNET events onto the session timeline

**Objective:** Preserve per-WAV analysis while exposing one global timeline.

**Files:**
- Modify: `orna_atlas/app/modules/media/service.py`
- Modify: relevant BirdNET model/schema if segment provenance is not currently representable
- Test: `orna_atlas/app/tests/test_bird_analysis_pipeline.py`

**Rules:**

- Store `recording_segment_id` as provenance.
- Keep provider-local interval in internal metadata if useful for audit.
- Public `start_seconds`/`end_seconds` equal local values plus `start_offset_ms / 1000`.
- Reject any shifted result outside the total session duration rather than clamping it.
- A failed source analysis does not erase prior successful results for that segment or poison HLS playback.

**Verification:**

```bash
python -m pytest orna_atlas/app/tests/test_bird_analysis_pipeline.py -q
```

Include a regression where an event in the third source appears after the summed durations of sources one and two.

**Commit:**

```bash
git add orna_atlas/app/modules/media/service.py orna_atlas/app/tests/test_bird_analysis_pipeline.py
git commit -m "feat: map segmented BirdNET results to session time"
```

---

### Task 9: Implement authenticated HLS grants and media gateway

**Objective:** Serve a private playlist and all child objects without making the S3 prefix public.

**Files:**
- Modify: `orna_atlas/app/modules/sessions/schemas.py`
- Modify: `orna_atlas/app/modules/sessions/service.py`
- Modify: `orna_atlas/app/modules/sessions/router.py`
- Create: `orna_atlas/app/modules/media/hls_gateway.py`
- Create: `orna_atlas/app/modules/media/hls_router.py`
- Modify: `orna_atlas/app/main.py`
- Modify: `orna_atlas/app/core/config.py`
- Test: `orna_atlas/app/tests/test_hls_playback_gateway.py`

**Grant contract:** preserve `stream_url` for compatibility and add explicit transport metadata:

```json
{
  "session_id": "...",
  "stream_url": "/api/v1/media/hls/<rendition-id>/index.m3u8",
  "stream_type": "hls",
  "expires_at": "...",
  "refresh_after_seconds": 600
}
```

**Cookie:** signed, short-lived, HttpOnly, Secure outside local development, SameSite=Lax, narrow path `/api/v1/media/hls/`. Claims: session ID, rendition ID, user/anonymous grant identity, access level, issued/expiry, nonce. Use a dedicated rotating HLS signing key configuration rather than S3 credentials.

**Gateway routes:**

```http
GET /api/v1/media/hls/{rendition_id}/index.m3u8
GET /api/v1/media/hls/{rendition_id}/{object_name}
```

Manifest route:

1. Validate cookie and exact rendition claim.
2. Recheck active/ready rendition and session access lifecycle where feasible; short TTL limits stale entitlement exposure.
3. Fetch and parse the stored manifest.
4. Reject unsupported tags and unsafe URIs.
5. Rewrite child URIs to gateway-relative names.
6. Return HLS content type, no-store, and CORS/credentials headers for configured web origin.

Child route:

1. Validate cookie, exact rendition, and basename against parsed/verified inventory.
2. Generate a short S3 presigned GET URL.
3. Return `307 Temporary Redirect`; do not proxy media bytes through FastAPI.
4. Set no-store and never include S3 keys in error bodies/logs.

Authorization tests must cover anonymous public, active member, expired member, private, draft, archived, missing rendition, stale rendition cookie, traversal, unknown child, tampered/expired cookie, storage outage, and audit event creation only on successful grants.

```bash
python -m pytest orna_atlas/app/tests/test_hls_playback_gateway.py orna_atlas/app/tests/test_sprint8_auth_membership.py -q
```

**Commit:**

```bash
git add orna_atlas/app/modules/sessions/schemas.py orna_atlas/app/modules/sessions/service.py orna_atlas/app/modules/sessions/router.py orna_atlas/app/modules/media/hls_gateway.py orna_atlas/app/modules/media/hls_router.py orna_atlas/app/main.py orna_atlas/app/core/config.py orna_atlas/app/tests/test_hls_playback_gateway.py
git commit -m "feat: authorize private HLS playback"
```

---

### Task 10: Add HLS playback to the React player

**Objective:** Play HLS in Safari natively and other supported browsers through hls.js while preserving current race/refresh behavior.

**Files:**
- Modify: `web/package.json`
- Modify: `web/components/audio/playerResources.ts`
- Modify: `web/components/audio/playerMachine.ts`
- Modify: `web/components/audio/PlayerProvider.tsx`
- Modify: `web/components/audio/playerMachine.test.cjs`
- Create: `web/components/audio/hlsResource.ts`
- Create: `web/components/audio/hlsResource.test.cjs`

**Implementation:**

1. Add a pinned `hls.js` dependency.
2. Select native HLS when `audio.canPlayType('application/vnd.apple.mpegurl')` succeeds.
3. Otherwise create one `Hls` instance with `xhrSetup`/fetch credentials enabled for the gateway cookie.
4. Attach media, load the manifest URL, and only call `play()` after the manifest/media is ready.
5. On grant refresh, request a new cookie/grant, preserve global time, reload the source, seek after metadata, and resume only if previously playing.
6. Destroy Hls and detach audio on session switch, route cleanup, stale request, and errors.
7. Map fatal network/media errors to typed player states; use bounded hls.js recovery, never an invented fallback stream.
8. Keep legacy direct-file playback for existing `stream_type` absent or `file`.

**Tests:** resource destruction, switch races, expired grant refresh, preserved seek, native path, hls.js path, fatal error, no stale callback updates.

```bash
cd web && npm install
cd web && npm run test:unit
cd web && npm run typecheck
cd web && npm run lint
```

**Commit:**

```bash
git add web/package.json web/package-lock.json web/components/audio/playerResources.ts web/components/audio/playerMachine.ts web/components/audio/PlayerProvider.tsx web/components/audio/playerMachine.test.cjs web/components/audio/hlsResource.ts web/components/audio/hlsResource.test.cjs
git commit -m "feat: play authenticated HLS sessions"
```

---

### Task 11: Synchronize OpenAPI and admin/public UI status

**Objective:** Expose segmented processing status safely and keep generated frontend contracts authoritative.

**Files:**
- Modify: `orna_atlas/app/modules/sessions/schemas.py`
- Modify: `orna_atlas/app/modules/media/schemas.py`
- Modify: `web/components/sessions/ProcessingStatusPanel.tsx`
- Generated: `web/openapi.json`
- Generated: `web/lib/api/generated.ts`
- Test: `orna_atlas/app/tests/test_sprint3_contracts.py`

**Public contract:** segment count, total duration, ready/failed counts, and playback availability; no storage keys, internal inventory, stage errors, or source ETags.

**Admin contract:** ordered segment IDs, storage keys, exact probe duration, offsets, source processing status, HLS job stages, and safe error messages.

**Verification:**

```bash
python -m pytest orna_atlas/app/tests/test_sprint3_contracts.py -q
cd web && npm run api:generate
cd web && npm run typecheck && npm run lint
```

Inspect generated diff and confirm public schemas do not expose `storage_key`.

**Commit:**

```bash
git add orna_atlas/app/modules/sessions/schemas.py orna_atlas/app/modules/media/schemas.py web/components/sessions/ProcessingStatusPanel.tsx web/openapi.json web/lib/api/generated.ts orna_atlas/app/tests/test_sprint3_contracts.py
git commit -m "feat: expose segmented HLS processing contracts"
```

---

### Task 12: Extend cleanup, metrics, and operational limits

**Objective:** Ensure versioned HLS prefixes are observable and eventually removed safely.

**Files:**
- Modify: `orna_atlas/app/modules/media/repository.py`
- Modify: `orna_atlas/app/workers/storage_cleanup.py`
- Modify: `orna_atlas/app/workers/audio_pipeline.py`
- Modify: `orna_atlas/app/core/metrics.py`
- Modify: `Dockerfile.worker`
- Test: `orna_atlas/app/tests/test_hls_operations.py`

**Requirements:**

- Cleanup job represents a verified prefix inventory, not a dangerous unrestricted recursive delete.
- Delete only immutable keys recorded for the archived rendition and then delete manifest last.
- Idempotently tolerate already missing children.
- Metrics: build outcome, stage duration, input bytes, output bytes, media-segment count, source count, ffmpeg exit category, gateway grant/manifest/redirect outcomes. Keep labels bounded; never label by session or key.
- Structured logs carry request ID, processing job ID, rendition ID, source fingerprint; never log cookies, presigned URLs, or raw S3 keys.
- Worker startup runs `ffmpeg -version` and `ffprobe -version` readiness checks or exposes a clear health failure.
- Configure a worker temp-volume capacity requirement and reject a job before download when known input size exceeds policy.

```bash
python -m pytest orna_atlas/app/tests/test_hls_operations.py -q
docker build -f Dockerfile.worker -t orna-atlas-worker:hls .
docker run --rm --entrypoint ffmpeg orna-atlas-worker:hls -version
```

**Commit:**

```bash
git add orna_atlas/app/modules/media/repository.py orna_atlas/app/workers/storage_cleanup.py orna_atlas/app/workers/audio_pipeline.py orna_atlas/app/tests/test_hls_operations.py Dockerfile.worker
git commit -m "feat: operate and clean versioned HLS renditions"
```

---

### Task 13: Add real MinIO and browser integration coverage

**Objective:** Prove the complete upload, verification, authorization, redirect, and playback lifecycle.

**Files:**
- Create: `tests/integration/test_hls_pipeline_integration.py`
- Create: `web/e2e/hls-playback.spec.ts`
- Modify: `web/e2e/mock-api.mjs` only for deterministic non-integration coverage
- Modify: test fixture/bootstrap scripts as needed

**Backend integration scenarios:**

1. Put three tiny WAVs in disposable MinIO.
2. Register them in one session.
3. Run HLS processing synchronously.
4. Assert object content types, relative manifest URIs, inventory, manifest-last behavior, and active rendition.
5. Fetch grant cookie, manifest, init redirect, and media redirect.
6. Delete one media object and assert playback/build verification fails closed.
7. Retry and assert exactly one active rendition.
8. Archive and run cleanup twice; assert idempotent deletion.

**Browser scenarios:**

- HLS begins playback and seeking updates global time.
- Grant refresh preserves position and resumes.
- Session switch destroys stale HLS work.
- Members-only stream requires entitlement.
- Missing child object produces visible playback error.
- Legacy direct-file sessions still play.

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration/test_hls_pipeline_integration.py -q
cd web && E2E_API_URL=http://localhost:8000 npm run test:e2e -- hls-playback.spec.ts
```

**Commit:**

```bash
git add tests/integration/test_hls_pipeline_integration.py web/e2e/hls-playback.spec.ts web/e2e/mock-api.mjs
git commit -m "test: cover end-to-end HLS lifecycle"
```

---

### Task 14: Add an idempotent import command for the six production-like objects

**Objective:** Provide a reviewable, dry-run-first command to attach existing S3 WAVs without ad-hoc database edits.

**Files:**
- Create: `orna_atlas/app/scripts/register_segmented_session.py`
- Create: `orna_atlas/app/tests/test_register_segmented_session_script.py`
- Create: `docs/runbooks/segmented-hls-import.md`

**CLI:**

```bash
python -m orna_atlas.app.scripts.register_segmented_session \
  --manifest /safe/path/session-segments.json \
  --dry-run
```

Manifest contains session ID and ordered managed keys, not credentials. Required behavior:

- default is dry-run;
- print target database host/database and S3 endpoint/bucket before mutation;
- require `--apply` plus a typed confirmation for non-local environments;
- head/probe every object and show ordered duration/size summary;
- validate continuous intended ordering but do not invent missing time;
- submit through the service layer;
- support an idempotency key and safe rerun;
- never delete/move original WAVs.

**Tests:** dry-run has no writes, wrong environment confirmation blocks, missing object blocks all, duplicate/reordered manifest blocks, rerun is idempotent, credentials/presigned URLs never appear in output.

```bash
python -m pytest orna_atlas/app/tests/test_register_segmented_session_script.py -q
```

**Commit:**

```bash
git add orna_atlas/app/scripts/register_segmented_session.py orna_atlas/app/tests/test_register_segmented_session_script.py docs/runbooks/segmented-hls-import.md
git commit -m "feat: add safe segmented session import command"
```

---

### Task 15: Benchmark real-size behavior and define deployment capacity

**Objective:** Prove the implementation handles approximately six 2 GB/two-hour WAVs without memory growth or host restart.

**Files:**
- Create: `scripts/benchmark_hls_pipeline.py`
- Create: `docs/benchmarks/hls-large-session.md`
- Modify: deployment documentation/config examples

**Method:**

1. Run only against a non-production bucket/database.
2. Measure RSS, temp-disk high-water mark, input/output bytes, wall time, S3 transfer time, ffmpeg CPU, and retry behavior.
3. Test one-worker sequential processing first; do not enable parallel segment transcodes until measured.
4. Interrupt during media upload, manifest upload, and activation; verify convergence and last-good preservation.
5. Verify browser seek near start, a source boundary, and near end.
6. Record actual WAV sample rate/channel/bit depth; do not generalize from sparse 8 kHz benchmarks.
7. Define worker memory request/limit, ephemeral disk request/limit, RQ timeout, retry/backoff, and max concurrent jobs from measured results.

```bash
python scripts/benchmark_hls_pipeline.py --help
# Execute only after reviewing its explicit non-production target output.
```

No production SLO is accepted until this benchmark is completed with representative files and real S3 latency.

**Commit:**

```bash
git add scripts/benchmark_hls_pipeline.py docs/benchmarks/hls-large-session.md
git commit -m "perf: benchmark large segmented HLS sessions"
```

---

### Task 16: Update current-state documentation and run release gates

**Objective:** Make only verified capability claims and complete all repository checks.

**Files:**
- Modify: `docs/CURRENT_STATE.md`
- Modify: `.env.example` if new non-secret settings were added
- Modify: deployment docs identified during implementation

**Documentation:**

- Move HLS from planned to implemented only after unit, MinIO integration, and browser tests pass.
- Document the authenticated media gateway and its deployment same-site/CORS requirement.
- State measured limitations: codec, bitrate, source count/duration caps, worker disk, and lack of ABR/CDN.
- Document rollback: preserve legacy rendition, disable HLS enqueue, and continue direct-file playback.

**Full validation:**

```bash
python -m pytest
python -m ruff check .
cd web && npm run test:unit && npm run typecheck && npm run lint && npm run api:check
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
cd web && npm run test:e2e
```

Then inspect:

```bash
git status --short
git diff --check
git diff --stat
```

Expected: all checks pass, no `.env`, generated audio, database dumps, `.next`, `node_modules`, model cache, cookies, credentials, or presigned URLs are staged.

**Commit:**

```bash
git add docs/CURRENT_STATE.md .env.example
git commit -m "docs: document verified HLS session support"
```

---

## Files likely to change

| Area | Paths |
|---|---|
| Domain/database | `orna_atlas/app/modules/media/models.py`, `sessions/models.py`, migration `0013_*` |
| Contracts/API | `media/schemas.py`, `sessions/schemas.py`, `admin/router.py`, `sessions/router.py` |
| Processing | `media/hls.py`, `media/service.py`, `workers/audio_pipeline.py`, `workers/pipeline_recovery.py` |
| Storage/security | `integrations/s3.py`, `media/hls_gateway.py`, `media/hls_router.py`, `workers/storage_cleanup.py` |
| Frontend | `PlayerProvider.tsx`, `hlsResource.ts`, player machine/resources, `package.json` |
| Tests | unit tests under `orna_atlas/app/tests/`, MinIO tests under `tests/integration/`, Playwright under `web/e2e/` |
| Docs/ops | ADR 0005, domain rules, import runbook, benchmark, current state |

## Acceptance criteria

- [ ] Six ordered existing S3 WAVs can be registered atomically under one session.
- [ ] The worker never creates one combined WAV and processes with bounded memory.
- [ ] One failed/retried build never destroys the last ready rendition.
- [ ] HLS media objects are immutable, verified, and activated only after manifest-last publication.
- [ ] Public, members-only, private, draft, and archived authorization behavior remains correct.
- [ ] No S3 prefix is public and no credentials appear in stored playlists.
- [ ] Browser playback supports start, pause, seek, grant refresh, switch, end, and cleanup.
- [ ] BirdNET events use the global session timeline with segment provenance.
- [ ] Legacy direct-WAV rendition playback remains compatible during rollout.
- [ ] Migration upgrade/downgrade passes against disposable PostgreSQL.
- [ ] Unit, lint, type, OpenAPI drift, MinIO integration, and Playwright gates pass.
- [ ] Representative six-file benchmark demonstrates acceptable RSS/temp-disk behavior before production rollout.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Huge temporary disk use | One-at-a-time materialization, measured high-water mark, preflight capacity policy, one job per worker initially |
| HLS child authorization | Same-origin HttpOnly grant cookie + gateway validation + per-child S3 redirects; never public bucket |
| Cookie/CORS incompatibility | Explicit configured web origin, credentialed requests, native Safari and hls.js integration tests |
| Partial S3 publication | Immutable version prefix, media/init first, manifest last, complete inventory verification |
| Long retry repeats all work | Idempotent stage state and immutable output; later optimize resumable media upload only after correctness |
| Source replacement during build | Ordered source-set fingerprint rechecked under lock before activation |
| Boundary timestamp discontinuity | ffprobe-derived millisecond offsets; HLS discontinuities where needed; browser boundary test |
| AAC unsuitable for scientific analysis | Preserve WAV masters; BirdNET reads source WAV, HLS is playback-only |
| API gateway load | Redirect media bytes to S3; API serves only small manifests and authorization redirects; CDN remains future boundary |
| Thousands of cleanup objects | Recorded verified inventory and idempotent batched cleanup with bounded retries |

## Open questions to resolve before Task 9

1. What is the production web/API origin topology? The cookie path/domain and CORS policy depend on whether they are same-site.
2. Which S3-compatible provider is used in production, and does it support required redirect/range behavior consistently?
3. Are the six WAVs truly contiguous, or do they have real clock gaps that must be represented explicitly?
4. Are they mono or stereo, and what sample rate/bit depth do they use? This affects the normalization profile and benchmark.
5. Is 160 kbit/s AAC acceptable for public/member listening, while WAV remains the scientific master?
6. What maximum session duration/source count should configuration enforce for the first release?
7. Is a CDN planned soon? If yes, retain the gateway interface but evaluate CDN signed cookies before production traffic.

## Recommended rollout

1. Deploy schema and code with HLS enqueue disabled.
2. Verify legacy sessions and playback.
3. Enable HLS for one local/MinIO fixture.
4. Run the representative six-WAV benchmark in a non-production environment.
5. Import one private editorial session and verify all boundaries.
6. Enable member/public playback only after authorization and browser tests pass.
7. Keep old active rendition through the configured retention window and retain a feature flag to return to direct-file playback.
