"""Real PostgreSQL/S3 coverage for partial and concurrent pipeline execution."""

from __future__ import annotations

import asyncio
import io
import os
import struct
import wave
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orna_atlas.app.integrations.s3 import ObjectStorageClient, ObjectStorageConfig
from orna_atlas.app.integrations.bird_analysis import (
    ANALYSIS_MODEL_VERSION,
    ANALYSIS_PROVIDER,
    BirdDetection,
)
from orna_atlas.app.modules.admin.models import AuditEvent  # noqa: F401
from orna_atlas.app.modules.auth.models import RefreshToken  # noqa: F401
from orna_atlas.app.modules.collections.models import (  # noqa: F401
    Collection,
    CollectionLocation,
    CollectionSession,
)
from orna_atlas.app.modules.locations.models import Location  # noqa: F401
from orna_atlas.app.modules.memberships.models import Membership  # noqa: F401
from orna_atlas.app.modules.media import audio as media_audio
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media import storage as media_storage
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob  # noqa: F401
from orna_atlas.app.modules.sessions.models import (  # noqa: F401
    BirdVocalPart,
    RecordingSession,
)
from orna_atlas.app.modules.users.models import User  # noqa: F401
from orna_atlas.app.workers import pipeline_recovery

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use disposable PostgreSQL/S3 services",
    ),
]


def _storage_client() -> ObjectStorageClient:
    return ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            public_endpoint_url=os.getenv("S3_PUBLIC_ENDPOINT_URL"),
            region=os.getenv("S3_REGION", "us-east-1"),
            private_bucket=os.environ["S3_PRIVATE_BUCKET"],
            public_bucket=os.getenv("S3_PUBLIC_BUCKET", "orna-media-public"),
            access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        )
    )


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        wav_file.writeframes(struct.pack("<h", 500) * 8_000)
    return output.getvalue()


async def _insert_pipeline_fixture(
    session: AsyncSession,
    *,
    storage_key: str,
) -> tuple[UUID, UUID, UUID, UUID]:
    location_id, recording_id, asset_id, job_id = (uuid4() for _ in range(4))
    suffix = uuid4().hex
    await session.execute(
        text(
            """
            INSERT INTO locations (
                id, slug, name, exact_latitude, exact_longitude,
                coordinate_visibility, sensitivity_level, timezone,
                metadata, created_at, updated_at
            ) VALUES (
                :id, :slug, 'Pipeline integration', 10, 20,
                'exact_public', 'none', 'UTC', '{}'::jsonb, now(), now()
            )
            """
        ),
        {"id": location_id, "slug": f"pipeline-location-{suffix}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO recording_sessions (
                id, location_id, slug, title, recorded_at, access_level,
                publication_status, processing_status, is_featured,
                metadata, created_at, updated_at
            ) VALUES (
                :id, :location_id, :slug, 'Pipeline integration', now(), 'private',
                'draft', 'queued', false, '{}'::jsonb, now(), now()
            )
            """
        ),
        {
            "id": recording_id,
            "location_id": location_id,
            "slug": f"pipeline-session-{suffix}",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO media_assets (
                id, session_id, kind, storage_key, mime_type, processing_status,
                revision, is_active, metadata, created_at
            ) VALUES (
                :id, :session_id, 'source_audio', :storage_key, 'audio/wav', 'queued',
                1, true, '{}'::jsonb, now()
            )
            """
        ),
        {"id": asset_id, "session_id": recording_id, "storage_key": storage_key},
    )
    await session.execute(
        text(
            """
            INSERT INTO processing_jobs (
                id, asset_id, job_type, status, attempt_count, stage_states,
                request_id, created_at, updated_at
            ) VALUES (
                :id, :asset_id, 'audio_pipeline', 'queued', 0, '{}'::jsonb,
                'integration-request', now(), now()
            )
            """
        ),
        {"id": job_id, "asset_id": asset_id},
    )
    await session.commit()
    return location_id, recording_id, asset_id, job_id


async def _wait_for_running_job(session_factory, job_id: UUID) -> None:
    for _ in range(500):
        async with session_factory() as session:
            job_status = await session.scalar(
                text("SELECT status FROM processing_jobs WHERE id = :id"),
                {"id": job_id},
            )
        if job_status == "running":
            return
        await asyncio.sleep(0.002)
    raise AssertionError("pipeline job never entered running state")


@pytest.mark.asyncio
async def test_partial_upload_retry_and_concurrent_worker_converge(monkeypatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = _storage_client()
    source_key = f"sessions/integration/{uuid4()}/source.wav"
    location_id: UUID | None = None
    original_upload = media_service._upload_streaming_rendition
    storage.put_bytes(source_key, _wav_bytes(), content_type="audio/wav")
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_audio, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_storage, "get_object_storage_client", lambda: storage)
    # This test exercises orchestration/concurrency, not the optional ML model.
    monkeypatch.setattr(media_service, "_detect_bird_parts", lambda *_args, **_kwargs: [])
    try:
        async with session_factory() as session:
            location_id, recording_id, asset_id, job_id = await _insert_pipeline_fixture(
                session,
                storage_key=source_key,
            )

        def fail_upload(*_args) -> None:
            raise TimeoutError("injected S3 upload timeout")

        monkeypatch.setattr(media_service, "_upload_streaming_rendition", fail_upload)
        async with session_factory() as session:
            with pytest.raises(TimeoutError, match="injected S3 upload timeout"):
                await media_service.process_media_asset(session, asset_id)

        async with session_factory() as session:
            failed = (
                await session.execute(
                    text(
                        """
                        SELECT status, attempt_count, stage_states
                        FROM processing_jobs WHERE id = :id
                        """
                    ),
                    {"id": job_id},
                )
            ).mappings().one()
            failed_renditions = await session.scalar(
                text(
                    """
                    SELECT count(*) FROM media_assets
                    WHERE session_id = :session_id
                      AND kind = 'streaming_rendition'
                      AND processing_status = 'failed'
                      AND is_active = false
                    """
                ),
                {"session_id": recording_id},
            )
            failed_cleanup_jobs = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM storage_cleanup_jobs AS cleanup
                    JOIN media_assets AS rendition ON rendition.id = cleanup.asset_id
                    WHERE rendition.session_id = :session_id
                      AND rendition.kind = 'streaming_rendition'
                      AND rendition.processing_status = 'failed'
                    """
                ),
                {"session_id": recording_id},
            )
        assert failed["status"] == "failed"
        assert failed["attempt_count"] == 1
        assert failed["stage_states"]["rendition_upload"]["status"] == "failed"
        assert failed_renditions == 1
        assert failed_cleanup_jobs == 1

        monkeypatch.setattr(
            media_service,
            "_upload_streaming_rendition",
            original_upload,
        )

        async def run_first_worker() -> None:
            async with session_factory() as session:
                await media_service.process_media_asset(session, asset_id)

        first_worker = asyncio.create_task(run_first_worker())
        await _wait_for_running_job(session_factory, job_id)
        async with session_factory() as second_session:
            await media_service.process_media_asset(second_session, asset_id)
        await first_worker

        async with session_factory() as session:
            completed = (
                await session.execute(
                    text(
                        """
                        SELECT status, attempt_count, stage_states
                        FROM processing_jobs WHERE id = :id
                        """
                    ),
                    {"id": job_id},
                )
            ).mappings().one()
            active_renditions = await session.scalar(
                text(
                    """
                    SELECT count(*) FROM media_assets
                    WHERE session_id = :session_id
                      AND kind = 'streaming_rendition'
                      AND processing_status = 'ready'
                      AND is_active = true
                      AND archived_at IS NULL
                    """
                ),
                {"session_id": recording_id},
            )
        assert completed["status"] == "succeeded"
        assert completed["attempt_count"] == 2
        assert completed["stage_states"]["rendition_upload"]["attempt_count"] == 2
        assert active_renditions == 1
    finally:
        monkeypatch.setattr(media_service, "_upload_streaming_rendition", original_upload)
        object_keys: list[str] = [source_key]
        if location_id is not None:
            async with session_factory() as session:
                object_keys.extend(
                    (
                        await session.execute(
                            text(
                                """
                                SELECT storage_key
                                FROM media_assets
                                WHERE session_id IN (
                                    SELECT id FROM recording_sessions WHERE location_id = :id
                                )
                                """
                            ),
                            {"id": location_id},
                        )
                    ).scalars()
                )
                await session.execute(
                    text(
                        """
                        DELETE FROM storage_cleanup_jobs
                        WHERE asset_id IN (
                            SELECT asset.id
                            FROM media_assets AS asset
                            JOIN recording_sessions AS recording
                              ON recording.id = asset.session_id
                            WHERE recording.location_id = :id
                        )
                        """
                    ),
                    {"id": location_id},
                )
                await session.execute(
                    text("DELETE FROM locations WHERE id = :id"),
                    {"id": location_id},
                )
                await session.commit()
        for key in set(object_keys):
            storage.delete_object(key)
        await engine.dispose()


@pytest.mark.asyncio
async def test_archived_object_cleanup_is_durable_and_idempotent(monkeypatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = _storage_client()
    source_key = f"sessions/integration/{uuid4()}/cleanup.wav"
    location_id: UUID | None = None
    storage.put_bytes(source_key, _wav_bytes(), content_type="audio/wav")
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)
    try:
        async with session_factory() as session:
            location_id, _recording_id, asset_id, _job_id = await _insert_pipeline_fixture(
                session,
                storage_key=source_key,
            )
        async with session_factory() as session:
            await media_service.archive_asset(session, asset_id)
            await media_service.purge_archived_asset(session, asset_id)

        assert not storage.object_exists(source_key)
        async with session_factory() as session:
            cleanup = (
                await session.execute(
                    text(
                        """
                        SELECT id, status, attempt_count
                        FROM storage_cleanup_jobs
                        WHERE asset_id = :asset_id
                        """
                    ),
                    {"asset_id": asset_id},
                )
            ).mappings().one()
            deleted_at = await session.scalar(
                text("SELECT storage_deleted_at FROM media_assets WHERE id = :id"),
                {"id": asset_id},
            )
            repeated = await media_service.process_storage_cleanup_job(
                session,
                cleanup["id"],
            )
        assert cleanup["status"] == "succeeded"
        assert cleanup["attempt_count"] == 1
        assert deleted_at is not None
        assert repeated is True
    finally:
        if location_id is not None:
            async with session_factory() as session:
                await session.execute(
                    text("DELETE FROM locations WHERE id = :id"),
                    {"id": location_id},
                )
                await session.commit()
        storage.delete_object(source_key)
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_archive_schedules_one_cleanup_job() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage_key = f"sessions/integration/{uuid4()}/concurrent-cleanup.wav"
    location_id: UUID | None = None
    try:
        async with session_factory() as session:
            location_id, _recording_id, asset_id, _job_id = await _insert_pipeline_fixture(
                session,
                storage_key=storage_key,
            )

        async def schedule() -> None:
            async with session_factory() as session:
                asset = await session.get(MediaAsset, asset_id)
                assert asset is not None
                await media_service.repository.schedule_storage_cleanup(
                    session,
                    [asset],
                    retain_until=media_service._retention_deadline(),
                )
                await session.commit()

        await asyncio.gather(schedule(), schedule())

        async with session_factory() as session:
            count = await session.scalar(
                text(
                    """
                    SELECT count(*) FROM storage_cleanup_jobs
                    WHERE storage_key = :storage_key
                    """
                ),
                {"storage_key": storage_key},
            )
        assert count == 1
    finally:
        async with session_factory() as session:
            await session.execute(
                text("DELETE FROM storage_cleanup_jobs WHERE storage_key = :storage_key"),
                {"storage_key": storage_key},
            )
            if location_id is not None:
                await session.execute(
                    text("DELETE FROM locations WHERE id = :id"),
                    {"id": location_id},
                )
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_bird_integrity_failure_rolls_back_only_real_savepoint(monkeypatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    location_id: UUID | None = None
    try:
        async with session_factory() as session:
            location_id, recording_id, asset_id, _job_id = await _insert_pipeline_fixture(
                session,
                storage_key=f"sessions/integration/{uuid4()}/bird.wav",
            )
            await session.execute(
                text(
                    """
                    INSERT INTO bird_vocal_parts (
                        id, session_id, species_code, species_common_name,
                        starts_at_seconds, ends_at_seconds, confidence, call_type,
                        analysis_provider, analysis_model_version, metadata, created_at
                    ) VALUES (
                        :id, :session_id, 'existing_bird', 'Existing bird',
                        1, 2, 0.8, 'call', :provider, :model, '{}'::jsonb, now()
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "session_id": recording_id,
                    "provider": ANALYSIS_PROVIDER,
                    "model": ANALYSIS_MODEL_VERSION,
                },
            )
            await session.commit()

        invalid_detection = BirdDetection(
            species_code="invalid_confidence",
            species_common_name="Invalid confidence",
            species_scientific_name=None,
            starts_at_seconds=3,
            ends_at_seconds=4,
            confidence=2.0,
        )
        monkeypatch.setattr(
            media_service,
            "_detect_bird_parts",
            lambda *_args, **_kwargs: [invalid_detection],
        )
        async with session_factory() as session:
            asset = await media_service.repository.get_asset(session, asset_id)
            assert asset is not None
            await media_service._analyze_and_store_bird_parts(session, asset)
            # A separate outer-transaction mutation must still be committable.
            asset.session.weather = "outer transaction survived"
            await session.commit()

        async with session_factory() as session:
            parts = (
                await session.execute(
                    text(
                        """
                        SELECT species_code FROM bird_vocal_parts
                        WHERE session_id = :session_id
                          AND analysis_provider = :provider
                          AND analysis_model_version = :model
                        """
                    ),
                    {
                        "session_id": recording_id,
                        "provider": ANALYSIS_PROVIDER,
                        "model": ANALYSIS_MODEL_VERSION,
                    },
                )
            ).scalars().all()
            recording = (
                await session.execute(
                    text(
                        """
                        SELECT weather, metadata FROM recording_sessions WHERE id = :id
                        """
                    ),
                    {"id": recording_id},
                )
            ).mappings().one()
        assert parts == ["existing_bird"]
        assert recording["weather"] == "outer transaction survived"
        assert recording["metadata"]["bird_analysis"]["latest_attempt"]["status"] == "failed"
        assert (
            recording["metadata"]["bird_analysis"]["latest_attempt"]["error_code"]
            == "IntegrityError"
        )
    finally:
        if location_id is not None:
            async with session_factory() as session:
                await session.execute(
                    text("DELETE FROM locations WHERE id = :id"),
                    {"id": location_id},
                )
                await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["running", "queued"])
async def test_recovery_worker_requeues_stale_job_through_real_redis(
    monkeypatch,
    initial_status: str,
) -> None:
    from redis import Redis
    from rq import Queue
    from rq.job import Job

    from orna_atlas.app.workers.audio_pipeline import AUDIO_QUEUE_NAME

    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = _storage_client()
    source_key = f"sessions/integration/{uuid4()}/stale.wav"
    location_id: UUID | None = None
    queue_job_id: str | None = None
    redis = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue(AUDIO_QUEUE_NAME, connection=redis)
    storage.put_bytes(source_key, _wav_bytes(), content_type="audio/wav")
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_audio, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_storage, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_service, "_detect_bird_parts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(pipeline_recovery, "AsyncSessionLocal", session_factory)
    try:
        async with session_factory() as session:
            location_id, recording_id, asset_id, job_id = await _insert_pipeline_fixture(
                session,
                storage_key=source_key,
            )
            await session.execute(
                text(
                    """
                    UPDATE processing_jobs
                    SET status = CAST(:status AS varchar), attempt_count = 1,
                        started_at = now() - interval '8 hours',
                        heartbeat_at = CASE
                            WHEN CAST(:status AS varchar) = 'running'
                            THEN now() - interval '8 hours'
                            ELSE NULL
                        END,
                        updated_at = now() - interval '8 hours'
                    WHERE id = :id
                    """
                ),
                {"id": job_id, "status": initial_status},
            )
            await session.execute(
                text(
                    """
                    UPDATE media_assets SET processing_status = 'processing' WHERE id = :id
                    """
                ),
                {"id": asset_id},
            )
            await session.execute(
                text(
                    """
                    UPDATE recording_sessions
                    SET processing_status = 'processing' WHERE id = :id
                    """
                ),
                {"id": recording_id},
            )
            await session.commit()

        recovered, failed = await pipeline_recovery.run_once(limit=25)

        async with session_factory() as session:
            jobs = (
                await session.execute(
                    text(
                        """
                        SELECT id, status, attempt_count, heartbeat_at,
                               queue_job_id, error_code
                        FROM processing_jobs
                        WHERE asset_id = :asset_id
                        ORDER BY created_at
                        """
                    ),
                    {"asset_id": asset_id},
                )
            ).mappings().all()
        assert recovered >= 1
        assert failed == 0
        assert len(jobs) == 2
        assert jobs[0]["id"] == job_id
        assert jobs[0]["status"] == "failed"
        assert jobs[0]["error_code"] == "stale_lease_reconciled"
        assert jobs[1]["status"] == "queued"
        queue_job_id = jobs[1]["queue_job_id"]
        assert queue_job_id in queue.job_ids

        # Simulate the queued worker, then prove a delayed duplicate RQ delivery
        # observes the terminal DB job and does not execute the stages twice.
        async with session_factory() as session:
            await media_service.process_media_asset(session, asset_id)
        async with session_factory() as session:
            await media_service.process_media_asset(session, asset_id)
        async with session_factory() as session:
            completed = (
                await session.execute(
                    text(
                        """
                        SELECT status, attempt_count, heartbeat_at
                        FROM processing_jobs
                        WHERE asset_id = :asset_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"asset_id": asset_id},
                )
            ).mappings().one()
            object_keys = (
                await session.execute(
                    text(
                        "SELECT storage_key FROM media_assets WHERE session_id = :id"
                    ),
                    {"id": recording_id},
                )
            ).scalars().all()
        assert completed["status"] == "succeeded"
        assert completed["attempt_count"] == 1
        assert completed["heartbeat_at"] is not None
    finally:
        if location_id is not None:
            async with session_factory() as session:
                await session.execute(
                    text("DELETE FROM locations WHERE id = :id"),
                    {"id": location_id},
                )
                await session.commit()
        for key in locals().get("object_keys", [source_key]):
            storage.delete_object(key)
        if queue_job_id is not None:
            queue.remove(queue_job_id)
            try:
                Job.fetch(queue_job_id, connection=redis).delete()
            except Exception:
                pass
        redis.close()
        await engine.dispose()
