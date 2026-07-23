from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_types import MediaKind
from orna_atlas.app.core.domain_errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from orna_atlas.app.core.logging import current_request_id
from orna_atlas.app.core.metrics import (
    PIPELINE_JOBS,
    PIPELINE_QUEUE_JOBS,
    PIPELINE_STAGE_DURATION,
)
from orna_atlas.app.integrations.bird_analysis import (
    ANALYSIS_MODEL_VERSION,
    ANALYSIS_PROVIDER,
    BirdDetection,
    analyze_audio_file,
)
from orna_atlas.app.integrations.redis import invalidate_atlas_cache
from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.modules.media import repository
from orna_atlas.app.modules.media.audio import (
    extract_audio_metadata,
    generate_waveform,
    int_or_none as _int_or_none,
    public_audio_metadata,
    streaming_rendition_key,
    upload_streaming_rendition as _upload_streaming_rendition,
)
from orna_atlas.app.modules.media.hls_pipeline import package_segmented_hls
from orna_atlas.app.modules.media.models import (
    HlsProcessingJob,
    MediaAsset,
    ProcessingJob,
    RecordingSegment,
    StorageCleanupJob,
)
from orna_atlas.app.modules.media.schemas import (
    MediaAssetCreate,
    ProcessingStatusRead,
    RecordingSegmentBatchCreate,
)
from orna_atlas.app.modules.media.segment_analysis import offset_segment_detections
from orna_atlas.app.modules.media.storage import materialize_storage
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.models import RecordingSession

PIPELINE_JOB_TYPE = "audio_pipeline"
SOURCE_AUDIO_KINDS = {"audio", "source_audio", "master_audio"}
STREAMING_RENDITION_KIND = "streaming_rendition"
CLEANUP_LEASE = timedelta(minutes=15)
PIPELINE_STAGES = (
    "metadata",
    "waveform",
    "rendition_upload",
    "rendition_verify",
    "rendition_activate",
    "bird_analysis",
)
logger = logging.getLogger(__name__)


class ObsoleteAssetRevisionError(RuntimeError):
    pass


def _job_is_stale(job: ProcessingJob, *, now: datetime | None = None) -> bool:
    status = getattr(job, "status", "running")
    reference = (
        getattr(job, "heartbeat_at", None)
        if status == "running"
        else getattr(job, "updated_at", None) or getattr(job, "created_at", None)
    )
    if status not in {"queued", "running"} or reference is None:
        return False
    current_time = now or datetime.now(UTC)
    return reference < current_time - timedelta(
        seconds=get_settings().pipeline_stale_after_seconds
    )


def validate_managed_storage_key(storage_key: str) -> None:
    path = PurePosixPath(storage_key)
    if (
        storage_key.startswith(("/", "file://", "s3://"))
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != "sessions"
    ):
        raise ValidationError("Storage key must be a managed relative sessions/ key")


async def require_asset(session: AsyncSession, asset_id: UUID) -> MediaAsset:
    asset = await repository.get_asset(session, asset_id)
    if asset is None:
        raise NotFoundError("Media asset not found")
    return asset


async def get_ready_hls_rendition(
    session: AsyncSession, asset_id: UUID
) -> MediaAsset | None:
    asset = await repository.get_asset(session, asset_id)
    metadata = asset.metadata_ if asset and isinstance(asset.metadata_, dict) else {}
    inventory = metadata.get("object_keys", [])
    if (
        asset is None
        or not asset.is_active
        or asset.processing_status != "ready"
        or metadata.get("format") != "hls"
        or not isinstance(inventory, list)
    ):
        return None
    return asset


async def register_recording_segments(
    session: AsyncSession,
    session_id: UUID,
    data: RecordingSegmentBatchCreate,
) -> tuple[list[RecordingSegment], HlsProcessingJob]:
    """Atomically register existing private S3 WAV objects as one logical recording."""
    recording = await sessions_service.require_session_for_admin(session, session_id)
    if await repository.list_recording_segments(session, session_id, for_update=True):
        raise ConflictError("Recording segments already exist for this session")

    storage = get_object_storage_client()
    if not storage.is_configured():
        raise ServiceUnavailableError("Object storage is not configured")
    for item in data.segments:
        validate_managed_storage_key(item.storage_key)
        if await repository.get_asset_by_storage_key(session, item.storage_key):
            raise ConflictError("Media asset storage key exists")
        try:
            exists = await asyncio.to_thread(storage.object_exists, item.storage_key)
        except Exception as exc:  # noqa: BLE001 - storage failure must not become missing data.
            raise ServiceUnavailableError("Unable to verify source audio in object storage") from exc
        if not exists:
            raise ValidationError(f"Source audio object does not exist: {item.storage_key}")

    segments: list[RecordingSegment] = []
    fingerprint = hashlib.sha256()
    for item in data.segments:
        fingerprint.update(f"{item.sequence_number}\0{item.storage_key}\0{item.checksum or ''}\n".encode())
        asset_data = MediaAssetCreate(
            kind=MediaKind.SOURCE_AUDIO,
            storage_key=item.storage_key,
            mime_type="audio/wav",
            checksum=item.checksum,
            metadata={"recording_segment": True, "sequence_number": item.sequence_number},
            enqueue_processing=False,
        )
        asset = await repository.create_media_asset(
            session,
            recording,
            asset_data,
            revision=item.sequence_number,
            is_active=True,
        )
        segments.append(
            await repository.create_recording_segment(
                session,
                recording=recording,
                source_asset=asset,
                sequence_number=item.sequence_number,
            )
        )

    job = await repository.create_hls_processing_job(
        session,
        session_id=session_id,
        source_fingerprint=fingerprint.hexdigest(),
    )
    recording.processing_status = "queued"
    await session.commit()
    try:
        from orna_atlas.app.workers.audio_pipeline import enqueue_hls_processing

        job.queue_job_id = await asyncio.to_thread(
            enqueue_hls_processing, job.id, request_id=current_request_id()
        )
        await session.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        job.error_message = str(exc)[:2000]
        job.finished_at = datetime.now(UTC)
        recording.processing_status = "failed"
        await session.commit()
        raise ServiceUnavailableError("Unable to enqueue HLS processing") from exc
    return segments, job


async def retry_hls_processing(session: AsyncSession, session_id: UUID) -> HlsProcessingJob:
    recording = await sessions_service.require_session_for_admin(session, session_id)
    job = await repository.latest_hls_processing_job(session, session_id, for_update=True)
    if job is None:
        raise NotFoundError("HLS processing job not found")
    if job.status in {"queued", "running", "succeeded"}:
        return job
    from orna_atlas.app.workers.audio_pipeline import enqueue_hls_processing

    job.status = "queued"
    job.error_code = None
    job.error_message = None
    job.finished_at = None
    recording.processing_status = "queued"
    await session.commit()
    try:
        job.queue_job_id = await asyncio.to_thread(
            enqueue_hls_processing, job.id, request_id=current_request_id()
        )
        await session.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        job.error_message = str(exc)[:2000]
        job.finished_at = datetime.now(UTC)
        recording.processing_status = "failed"
        await session.commit()
        raise ServiceUnavailableError("Unable to enqueue HLS processing") from exc
    return job


async def process_hls_job(session: AsyncSession, job_id: UUID) -> None:
    job = await repository.get_hls_processing_job(session, job_id, for_update=True)
    if job is None:
        raise NotFoundError("HLS processing job not found")
    if job.status == "succeeded":
        return
    segments = await repository.list_recording_segments(session, job.session_id)
    if not segments:
        raise ValidationError("Recording session has no segments")

    job.status = "running"
    job.attempt_count += 1
    job.started_at = job.started_at or datetime.now(UTC)
    job.heartbeat_at = datetime.now(UTC)
    job.stage_states = {**job.stage_states, "packaging": "running"}
    await session.commit()

    generation_id = uuid4()
    prefix = f"sessions/{job.session_id}/hls/{generation_id}"
    storage = get_object_storage_client()
    partial_inventory: list[str] = []
    try:
        packaged = await asyncio.to_thread(
            package_segmented_hls,
            storage,
            [segment.source_asset.storage_key for segment in segments],
            prefix,
            partial_inventory,
        )
    except Exception as exc:
        if partial_inventory:
            session.add(
                StorageCleanupJob(
                    storage_key=f"{prefix}/index.m3u8",
                    object_keys=list(partial_inventory),
                    retain_until=datetime.now(UTC),
                )
            )
        failed = await repository.get_hls_processing_job(session, job_id, for_update=True)
        if failed is not None:
            failed.status = "failed"
            failed.error_code = type(exc).__name__
            failed.error_message = str(exc)[:2000]
            failed.finished_at = datetime.now(UTC)
            failed.stage_states = {**failed.stage_states, "packaging": "failed"}
            recording = await sessions_service.require_session_for_admin(session, failed.session_id)
            recording.processing_status = "failed"
            await session.commit()
        raise

    job = await repository.get_hls_processing_job(session, job_id, for_update=True)
    if job is None:
        raise NotFoundError("HLS processing job disappeared")
    segments = await repository.list_recording_segments(session, job.session_id, for_update=True)
    offset = 0
    for segment, duration_ms in zip(segments, packaged.duration_ms, strict=True):
        segment.start_offset_ms = offset
        segment.duration_ms = duration_ms
        segment.processing_status = "ready"
        segment.source_asset.processing_status = "ready"
        offset += duration_ms

    recording = await sessions_service.require_session_for_admin(session, job.session_id)
    bird_succeeded, bird_failed = await _analyze_hls_segments(session, recording, segments)
    rendition = MediaAsset(
        session=recording,
        kind=MediaKind.STREAMING_RENDITION,
        storage_key=packaged.manifest_key,
        mime_type="application/vnd.apple.mpegurl",
        metadata_={
            "format": "hls",
            "generation_id": str(generation_id),
            "object_keys": list(packaged.object_keys),
            "source_count": len(segments),
            "duration_ms": offset,
        },
        processing_status="ready",
        revision=max((asset.revision for asset in recording.media_assets), default=0) + 1,
        is_active=False,
    )
    session.add(rendition)
    await session.flush()
    replaced = await repository.activate_rendition(session, rendition)
    if replaced:
        await repository.schedule_storage_cleanup(
            session, replaced, retain_until=_retention_deadline()
        )
    job.status = "succeeded"
    job.finished_at = datetime.now(UTC)
    job.heartbeat_at = datetime.now(UTC)
    job.stage_states = {
        **job.stage_states,
        "packaging": "succeeded",
        "bird_analysis": "succeeded" if bird_failed == 0 else "partially_failed",
        "bird_segments_succeeded": bird_succeeded,
        "bird_segments_failed": bird_failed,
        "activation": "succeeded",
    }
    recording.processing_status = "ready"
    recording.duration_seconds = max(1, round(offset / 1000))
    await session.commit()


async def _analyze_hls_segments(
    session: AsyncSession, recording: RecordingSession, segments: list[RecordingSegment]
) -> tuple[int, int]:
    """Analyze sources sequentially and commit each segment independently."""
    location = recording.location
    lat = getattr(location, "exact_latitude", None)
    lon = getattr(location, "exact_longitude", None)
    succeeded = 0
    failed = 0
    for segment in segments:
        segment.processing_status = "processing"
        segment.processing_attempt_count += 1
        segment.processing_error_code = None
        segment.processing_error_message = None
        await session.commit()
        try:
            local = await asyncio.to_thread(
                _detect_bird_parts,
                segment.source_asset,
                lat=lat,
                lon=lon,
                recorded_at=recording.recorded_at
                + timedelta(milliseconds=segment.start_offset_ms or 0),
            )
            detections = offset_segment_detections(
                local,
                offset_ms=segment.start_offset_ms or 0,
                sequence_number=segment.sequence_number,
            )
            savepoint = await session.begin_nested()
            try:
                await sessions_repository.replace_segment_bird_vocal_parts(
                    session,
                    recording.id,
                    segment.id,
                    detections,
                    analysis_provider=ANALYSIS_PROVIDER,
                    analysis_model_version=ANALYSIS_MODEL_VERSION,
                )
            except Exception:
                await savepoint.rollback()
                raise
            else:
                await savepoint.commit()
            segment.processing_status = "ready"
            succeeded += 1
            await session.commit()
        except Exception as exc:
            failed += 1
            await session.rollback()
            segment.processing_status = "failed"
            segment.processing_error_code = type(exc).__name__[:80]
            segment.processing_error_message = str(exc)[:2000]
            await session.commit()
            logger.exception("BirdNET analysis failed for segment %s", segment.id)
    return succeeded, failed


async def create_asset_for_session(
    session: AsyncSession, session_id: UUID, data: MediaAssetCreate
) -> MediaAsset:
    recording = await sessions_service.require_session_for_admin(session, session_id)
    validate_managed_storage_key(data.storage_key)
    if await repository.get_asset_by_storage_key(session, data.storage_key):
        raise ConflictError("Media asset storage key exists")

    revision = 1
    if data.kind in SOURCE_AUDIO_KINDS:
        previous_sources = await repository.active_source_assets_for_update(session, session_id)
        revision = max((item.revision for item in previous_sources), default=0) + 1
        await repository.archive_assets(session, previous_sources)
        await repository.schedule_storage_cleanup(
            session,
            previous_sources,
            retain_until=_retention_deadline(),
        )
    asset = await repository.create_media_asset(
        session,
        recording,
        data,
        revision=revision,
        is_active=data.kind in SOURCE_AUDIO_KINDS,
    )
    job = None
    if should_enqueue_audio_pipeline(data.kind, enqueue_processing=data.enqueue_processing):
        recording.processing_status = "queued"
        job = await repository.create_processing_job(
            session,
            asset,
            job_type=PIPELINE_JOB_TYPE,
            request_id=current_request_id(),
        )
    else:
        recording.processing_status = _recording_processing_status(recording)
    await session.commit()

    if job is not None:
        await _enqueue_or_mark_failed(session, asset, job)
    await session.refresh(asset, attribute_names=["processing_jobs"])
    return asset


def should_enqueue_audio_pipeline(kind: str, *, enqueue_processing: bool = True) -> bool:
    return enqueue_processing and kind in SOURCE_AUDIO_KINDS


async def processing_status_for_session(
    session: AsyncSession, session_id: UUID
) -> ProcessingStatusRead:
    recording = await sessions_service.require_session_for_admin(session, session_id)
    assets = await repository.list_assets_for_session(session, session_id)
    latest_job = _latest_job(assets)
    return ProcessingStatusRead(
        session_id=recording.id,
        processing_status=recording.processing_status,
        media_assets=assets,
        latest_job=latest_job,
    )


async def enqueue_asset_processing(
    asset_id: UUID,
    revision: int,
    *,
    request_id: str | None = None,
    processing_job_id: UUID | None = None,
    duration_seconds: int | None = None,
) -> str:
    from orna_atlas.app.workers.audio_pipeline import enqueue_audio_processing

    return await asyncio.to_thread(
        enqueue_audio_processing,
        asset_id,
        revision,
        request_id=request_id,
        processing_job_id=processing_job_id,
        duration_seconds=duration_seconds,
    )


async def retry_asset_processing(session: AsyncSession, asset_id: UUID) -> ProcessingStatusRead:
    asset = await repository.get_asset_for_processing(session, asset_id)
    if asset is None:
        raise NotFoundError("Media asset not found")
    if asset.kind not in SOURCE_AUDIO_KINDS:
        raise ValidationError("Audio processing can only be queued for source audio assets")
    if (getattr(asset, "metadata_", None) or {}).get("recording_segment") is True:
        raise ConflictError("Segment sources must be processed through the session HLS pipeline")
    active_job = await repository.active_processing_job(
        session, asset.id, job_type=PIPELINE_JOB_TYPE
    )
    if active_job is not None:
        return await processing_status_for_session(session, asset.session_id)
    if not asset.is_active or asset.archived_at is not None:
        raise ConflictError("Archived media revisions cannot be processed")
    asset.processing_status = "queued"
    asset.session.processing_status = "queued"
    job = await repository.create_processing_job(
        session,
        asset,
        job_type=PIPELINE_JOB_TYPE,
        request_id=current_request_id(),
    )
    await session.commit()
    await _enqueue_or_mark_failed(session, asset, job)
    return await processing_status_for_session(session, asset.session_id)


async def recover_stale_asset_processing(session: AsyncSession, asset_id: UUID) -> bool:
    """Replace an orphaned queued/running lease and put it back through RQ.

    Recovery deliberately does not execute the ML pipeline inline: the regular
    queue supplies the configured hard timeout, retry policy and worker metrics.
    """
    asset = await repository.get_asset_for_processing(session, asset_id)
    if asset is None:
        return False
    job = await repository.latest_processing_job(
        session,
        asset.id,
        job_type=PIPELINE_JOB_TYPE,
    )
    if job is None or not _job_is_stale(job):
        return False
    if not asset.is_active or asset.archived_at is not None:
        _mark_job_superseded(job, "Media asset revision is no longer active")
        await session.commit()
        return False

    now = datetime.now(UTC)
    stale_renditions = await repository.incomplete_streaming_renditions_for_recovery(
        session,
        asset,
    )
    if stale_renditions:
        await repository.archive_assets(session, stale_renditions)
        await repository.schedule_storage_cleanup(
            session,
            stale_renditions,
            retain_until=now,
        )
    job.status = "failed"
    job.error_code = "stale_lease_reconciled"
    job.error_message = "Orphaned pipeline lease was replaced by recovery"
    job.finished_at = now
    job.heartbeat_at = now
    asset.processing_status = "queued"
    asset.session.processing_status = "queued"
    replacement = await repository.create_processing_job(
        session,
        asset,
        job_type=PIPELINE_JOB_TYPE,
        request_id=getattr(job, "request_id", None),
    )
    await session.commit()
    await _enqueue_or_mark_failed(session, asset, replacement)
    return True


async def archive_asset(session: AsyncSession, asset_id: UUID) -> None:
    asset = await require_asset(session, asset_id)
    if asset.archived_at is None:
        await repository.archive_assets(session, [asset])
        retain_until = datetime.now(UTC) + timedelta(
            days=get_settings().media_retention_days
        )
        await repository.schedule_storage_cleanup(
            session,
            [asset],
            retain_until=retain_until,
        )
        asset.session.processing_status = _recording_processing_status(asset.session)
        await session.commit()
        await _clear_processing_caches(asset.session)


async def purge_archived_asset(session: AsyncSession, asset_id: UUID) -> None:
    asset = await require_asset(session, asset_id)
    if asset.archived_at is None or asset.is_active:
        raise ConflictError("Only archived media revisions can be purged")
    validate_managed_storage_key(asset.storage_key)
    storage_client = get_object_storage_client()
    if not storage_client.is_configured():
        raise ServiceUnavailableError(
            "Object storage is not configured; archived asset was not purged"
        )
    recording = asset.session
    jobs = await repository.schedule_storage_cleanup(
        session,
        [asset],
        retain_until=datetime.now(UTC),
    )
    await session.commit()
    if jobs:
        try:
            await process_storage_cleanup_job(session, jobs[0].id)
        except Exception as exc:
            raise ServiceUnavailableError(
                "Archived object cleanup is queued for retry"
            ) from exc
    await _clear_processing_caches(recording)


async def process_storage_cleanup_job(
    session: AsyncSession,
    job_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    """Delete one due object idempotently while persisting lease and retry state."""
    current_time = now or datetime.now(UTC)
    job = await repository.get_storage_cleanup_job_for_update(session, job_id)
    if job is None:
        return False
    if job.status == "succeeded":
        return True
    if job.retain_until > current_time or job.next_attempt_at > current_time:
        return False
    if (
        job.status == "running"
        and job.locked_at is not None
        and job.locked_at >= current_time - CLEANUP_LEASE
    ):
        return False

    job.status = "running"
    job.locked_at = current_time
    job.attempt_count += 1
    job.error_code = None
    job.error_message = None
    await session.commit()

    try:
        object_keys = getattr(job, "object_keys", None) or [job.storage_key]
        if not object_keys or not all(isinstance(key, str) for key in object_keys):
            raise ValueError("Cleanup inventory must contain storage keys")
        for storage_key in object_keys:
            validate_managed_storage_key(storage_key)
        storage_client = get_object_storage_client()
        if not storage_client.is_configured():
            raise RuntimeError("Object storage is not configured")
        for storage_key in object_keys:
            exists = await asyncio.to_thread(storage_client.object_exists, storage_key)
            if exists:
                await asyncio.to_thread(storage_client.delete_object, storage_key)
        completed_at = datetime.now(UTC)
        job.status = "succeeded"
        job.completed_at = completed_at
        job.locked_at = None
        if job.asset is not None:
            job.asset.storage_deleted_at = completed_at
        await session.commit()
        return True
    except Exception as exc:
        failed_at = datetime.now(UTC)
        retry_minutes = min(24 * 60, 2 ** min(job.attempt_count, 10))
        job.status = "failed"
        job.locked_at = None
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:1000]
        job.next_attempt_at = failed_at + timedelta(minutes=retry_minutes)
        await session.commit()
        raise


async def process_due_storage_cleanup_jobs(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> tuple[int, int]:
    """Process a bounded cleanup batch; failures remain persisted for later retries."""
    now = datetime.now(UTC)
    job_ids = await repository.due_storage_cleanup_job_ids(
        session,
        now=now,
        stale_before=now - CLEANUP_LEASE,
        limit=limit,
    )
    succeeded = 0
    failed = 0
    for job_id in job_ids:
        try:
            if await process_storage_cleanup_job(session, job_id):
                succeeded += 1
        except Exception:
            failed += 1
            logger.exception("Storage cleanup failed for job %s", job_id)
    return succeeded, failed


async def process_media_asset(
    session: AsyncSession,
    asset_id: UUID,
    *,
    processing_job_id: UUID | None = None,
) -> MediaAsset:
    asset = await repository.get_asset_for_processing(session, asset_id)
    if asset is None:
        raise NotFoundError("Media asset not found")
    job = await repository.latest_processing_job(session, asset.id, job_type=PIPELINE_JOB_TYPE)
    if job is None:
        job = await repository.create_processing_job(
            session,
            asset,
            job_type=PIPELINE_JOB_TYPE,
            request_id=current_request_id(),
        )

    if job.status == "succeeded":
        return asset
    if (
        job.status == "running"
        and not _job_is_stale(job)
        and (processing_job_id is None or processing_job_id != job.id)
    ):
        return asset
    if not asset.is_active or asset.archived_at is not None:
        if job.status in {"queued", "running"}:
            _mark_job_superseded(job, "Media asset revision is no longer active")
            await session.commit()
        raise ObsoleteAssetRevisionError("Media asset revision is no longer active")
    _mark_job_running(asset, job)
    await session.commit()
    job_context = {
        "event": "pipeline.job",
        "request_id": getattr(job, "request_id", None),
        "processing_job_id": str(getattr(job, "id", "")),
        "queue_job_id": getattr(job, "queue_job_id", None),
        "asset_id": str(asset.id),
    }
    logger.info("pipeline_processing_started", extra={**job_context, "status": "running"})

    rendition: MediaAsset | None = None
    try:
        if asset.kind not in SOURCE_AUDIO_KINDS:
            raise ValueError("Audio pipeline can only process source audio assets")

        async def metadata_stage() -> dict:
            metadata_result = await asyncio.to_thread(extract_audio_metadata, asset)
            _apply_audio_metadata(asset, metadata_result)
            return metadata_result

        metadata = await _run_pipeline_stage(
            session,
            job,
            "metadata",
            metadata_stage,
        )

        async def waveform_stage() -> dict:
            waveform_result = await asyncio.to_thread(
                generate_waveform,
                asset,
                metadata=metadata,
            )
            _apply_waveform(asset, waveform_result)
            asset.processing_status = "ready"
            return waveform_result

        await _run_pipeline_stage(session, job, "waveform", waveform_stage)

        rendition = await _ensure_streaming_rendition(
            session,
            asset,
            metadata=metadata,
        )

        async def upload_stage() -> None:
            await asyncio.to_thread(_upload_streaming_rendition, asset, rendition)

        await _run_pipeline_stage(
            session,
            job,
            "rendition_upload",
            upload_stage,
        )

        async def verify_stage() -> None:
            storage_client = get_object_storage_client()
            exists = await asyncio.to_thread(
                storage_client.object_exists,
                rendition.storage_key,
            )
            if not exists:
                raise FileNotFoundError(
                    "Uploaded streaming rendition could not be verified"
                )

        await _run_pipeline_stage(session, job, "rendition_verify", verify_stage)

        async def activate_stage() -> None:
            current_sources = await repository.active_source_assets_for_update(
                session,
                asset.session_id,
            )
            if not current_sources or current_sources[0].id != asset.id:
                raise ObsoleteAssetRevisionError(
                    "A newer source revision replaced this pipeline run"
                )
            archived_renditions = await repository.activate_rendition(session, rendition)
            await repository.schedule_storage_cleanup(
                session,
                archived_renditions,
                retain_until=_retention_deadline(),
            )

        await _run_pipeline_stage(session, job, "rendition_activate", activate_stage)

        async def bird_analysis_stage() -> None:
            await _analyze_and_store_bird_parts(session, asset)
            latest_attempt = (
                asset.session.metadata_.get("bird_analysis", {}).get("latest_attempt", {})
                if isinstance(asset.session.metadata_, dict)
                else {}
            )
            if latest_attempt.get("status") == "failed":
                raise RuntimeError(
                    str(latest_attempt.get("error_message") or "Bird analysis failed")
                )

        await _run_pipeline_stage(
            session,
            job,
            "bird_analysis",
            bird_analysis_stage,
            optional=True,
        )
        asset.processing_status = "ready"
        asset.session.processing_status = _recording_processing_status(asset.session)
        _mark_job_succeeded(job)
        await session.commit()
        PIPELINE_JOBS.labels("succeeded").inc()
        logger.info(
            "pipeline_processing_succeeded",
            extra={**job_context, "status": "succeeded"},
        )
        await _clear_processing_caches(asset.session)
        await session.refresh(asset, attribute_names=["processing_jobs"])
        return asset
    except ObsoleteAssetRevisionError as exc:
        await _fail_and_retain_rendition(session, rendition)
        _mark_job_superseded(job, str(exc))
        asset.session.processing_status = _recording_processing_status(asset.session)
        await session.commit()
        PIPELINE_JOBS.labels("superseded").inc()
        logger.warning(
            "pipeline_processing_superseded",
            extra={**job_context, "status": "superseded", "error": str(exc)},
        )
        raise
    except Exception as exc:
        await _fail_and_retain_rendition(session, rendition)
        _mark_job_failed(asset, job, exc)
        await session.commit()
        PIPELINE_JOBS.labels("failed").inc()
        logger.exception(
            "pipeline_processing_failed",
            extra={**job_context, "status": "failed", "error": str(exc)},
        )
        raise


async def _run_pipeline_stage(
    session: AsyncSession,
    job: ProcessingJob,
    stage: str,
    operation,
    *,
    optional: bool = False,
):
    """Persist an independently observable attempt around one idempotent stage."""
    started = time.perf_counter()
    _set_pipeline_stage_state(job, stage, "running")
    await session.commit()
    try:
        result = await operation()
    except Exception as exc:
        _set_pipeline_stage_state(job, stage, "failed", exc=exc)
        await session.commit()
        PIPELINE_STAGE_DURATION.labels(stage, "failed").observe(
            time.perf_counter() - started
        )
        if optional:
            return None
        raise
    _set_pipeline_stage_state(job, stage, "succeeded")
    await session.commit()
    PIPELINE_STAGE_DURATION.labels(stage, "succeeded").observe(
        time.perf_counter() - started
    )
    return result


async def _analyze_and_store_bird_parts(session: AsyncSession, asset: MediaAsset) -> None:
    """Run BirdNET analysis and persist detected bird vocal parts for the session."""
    location = asset.session.location
    lat = getattr(location, "exact_latitude", None)
    lon = getattr(location, "exact_longitude", None)
    recorded_at = asset.session.recorded_at

    try:
        detections = await asyncio.to_thread(
            _detect_bird_parts,
            asset,
            lat=lat,
            lon=lon,
            recorded_at=recorded_at,
        )
        savepoint = await session.begin_nested()
        try:
            await sessions_repository.replace_bird_vocal_parts(
                session,
                asset.session_id,
                detections,
                analysis_provider=ANALYSIS_PROVIDER,
                analysis_model_version=ANALYSIS_MODEL_VERSION,
            )
        except Exception:
            await savepoint.rollback()
            raise
        else:
            await savepoint.commit()
        _record_bird_analysis_status(
            asset.session,
            status="succeeded",
            parts_count=len(detections),
        )
    except Exception as exc:
        logger.exception("BirdNET analysis failed for session %s", asset.session_id)
        _record_bird_analysis_status(
            asset.session,
            status="failed",
            error_code=exc.__class__.__name__,
            error_message=str(exc)[:500],
        )


def _detect_bird_parts(
    asset: MediaAsset,
    *,
    lat: float | None,
    lon: float | None,
    recorded_at: datetime,
) -> list[BirdDetection]:
    with materialize_storage(asset.storage_key) as path:
        if path is None:
            raise FileNotFoundError(f"Source audio not found: {asset.storage_key}")
        return analyze_audio_file(
            path,
            lat=lat,
            lon=lon,
            recorded_at=recorded_at,
        )


def _record_bird_analysis_status(
    recording: RecordingSession,
    *,
    status: str,
    parts_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Persist the latest BirdNET analysis outcome on the session metadata."""
    metadata = recording.metadata_ if isinstance(recording.metadata_, dict) else {}
    payload: dict[str, object] = {
        "status": status,
        "provider": ANALYSIS_PROVIDER,
        "model_version": ANALYSIS_MODEL_VERSION,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    if parts_count is not None:
        payload["parts_count"] = parts_count
    if error_code is not None:
        payload["error_code"] = error_code
    if error_message is not None:
        payload["error_message"] = error_message
    existing_analysis = metadata.get("bird_analysis")
    analysis = existing_analysis if isinstance(existing_analysis, dict) else {}
    updated_analysis = {**analysis, "latest_attempt": payload}
    if status == "succeeded":
        updated_analysis["last_successful"] = payload
    recording.metadata_ = {**metadata, "bird_analysis": updated_analysis}


def _apply_pipeline_results(asset: MediaAsset, *, metadata: dict, waveform: dict) -> None:
    """Compatibility helper for callers that produce metadata and waveform together."""
    _apply_audio_metadata(asset, metadata)
    _apply_waveform(asset, waveform)
    asset.processing_status = "ready"


def _apply_audio_metadata(asset: MediaAsset, metadata: dict) -> None:
    existing = asset.metadata_ if isinstance(asset.metadata_, dict) else {}
    safe_metadata = public_audio_metadata(metadata)
    asset.metadata_ = {
        **existing,
        "audio_metadata": safe_metadata,
        "pipeline": {
            "processed_at": datetime.now(UTC).isoformat(),
            "version": "sprint6-local",
        },
    }
    duration_seconds = _int_or_none(metadata.get("duration_seconds"))
    size_bytes = _int_or_none(metadata.get("size_bytes"))
    if duration_seconds is not None:
        asset.duration_seconds = duration_seconds
        asset.session.duration_seconds = asset.session.duration_seconds or duration_seconds
    if size_bytes is not None:
        asset.size_bytes = asset.size_bytes or size_bytes

    session_metadata = asset.session.metadata_ if isinstance(asset.session.metadata_, dict) else {}
    asset.session.metadata_ = {
        **session_metadata,
        "audio_metadata": safe_metadata,
    }


def _apply_waveform(asset: MediaAsset, waveform: dict) -> None:
    session_metadata = asset.session.metadata_ if isinstance(asset.session.metadata_, dict) else {}
    asset.session.metadata_ = {**session_metadata, "waveform": waveform}


async def _ensure_streaming_rendition(
    session: AsyncSession, asset: MediaAsset, *, metadata: dict
) -> MediaAsset:
    rendition_id = uuid4()
    storage_key = streaming_rendition_key(asset, rendition_id)
    duration_seconds = _int_or_none(metadata.get("duration_seconds")) or asset.duration_seconds
    rendition_mime_type = "audio/wav"
    rendition = MediaAsset(
        id=rendition_id,
        session=asset.session,
        kind=STREAMING_RENDITION_KIND,
        storage_key=storage_key,
        mime_type=rendition_mime_type,
        processing_status="processing",
        duration_seconds=duration_seconds,
        size_bytes=None,
        checksum=asset.checksum,
        revision=asset.revision,
        is_active=False,
        source_asset_id=asset.id,
        metadata_={
            "bitrate_kbps": None,
            "source_asset_id": str(asset.id),
            "storage_policy": "versioned_s3_key",
            "transcoding": "copy_source_wav",
        },
    )
    session.add(rendition)
    await session.flush()
    return rendition


def _recording_processing_status(recording: RecordingSession) -> str:
    assets = list(recording.media_assets)
    source_assets = [
        asset
        for asset in assets
        if asset.kind in SOURCE_AUDIO_KINDS
        and asset.is_active
        and asset.archived_at is None
    ]
    if not source_assets:
        return "pending"
    if any(asset.processing_status == "failed" for asset in source_assets):
        return "failed"
    if any(asset.processing_status == "processing" for asset in source_assets):
        return "processing"
    if any(asset.processing_status == "queued" for asset in source_assets):
        return "queued"
    active_source_ids = {asset.id for asset in source_assets}
    has_rendition = any(
        asset.kind == STREAMING_RENDITION_KIND
        and asset.processing_status == "ready"
        and asset.is_active
        and asset.archived_at is None
        and (asset.source_asset_id is None or asset.source_asset_id in active_source_ids)
        for asset in assets
    )
    if all(asset.processing_status == "ready" for asset in source_assets) and has_rendition:
        return "ready"
    if any(asset.processing_status == "uploaded" for asset in source_assets):
        return "uploaded"
    return "pending"


def _mark_job_running(asset: MediaAsset, job: ProcessingJob) -> None:
    now = datetime.now(UTC)
    job.status = "running"
    job.attempt_count += 1
    job.error_code = None
    job.error_message = None
    job.started_at = now
    job.heartbeat_at = now
    job.finished_at = None
    states = getattr(job, "stage_states", None)
    existing_states = states if isinstance(states, dict) else {}
    job.stage_states = {
        stage: existing_states.get(
            stage,
            {
                "status": "pending",
                "attempt_count": 0,
                "error_code": None,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            },
        )
        for stage in PIPELINE_STAGES
    }
    asset.processing_status = "processing"
    asset.session.processing_status = "processing"


def _set_pipeline_stage_state(
    job: ProcessingJob,
    stage: str,
    stage_status: str,
    *,
    exc: Exception | None = None,
) -> None:
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Unknown pipeline stage: {stage}")
    heartbeat_at = datetime.now(UTC)
    now = heartbeat_at.isoformat()
    job.heartbeat_at = heartbeat_at
    states = getattr(job, "stage_states", None)
    updated_states = dict(states) if isinstance(states, dict) else {}
    previous = updated_states.get(stage)
    state = dict(previous) if isinstance(previous, dict) else {}
    attempts = int(state.get("attempt_count", 0))
    if stage_status == "running":
        attempts += 1
        state.update(
            status="running",
            attempt_count=attempts,
            error_code=None,
            error_message=None,
            started_at=now,
            finished_at=None,
        )
    else:
        state.update(
            status=stage_status,
            attempt_count=attempts,
            error_code=None if exc is None else exc.__class__.__name__,
            error_message=None if exc is None else str(exc)[:1000],
            finished_at=now,
        )
    updated_states[stage] = state
    job.stage_states = updated_states


def _mark_job_succeeded(job: ProcessingJob) -> None:
    job.status = "succeeded"
    job.finished_at = datetime.now(UTC)
    job.heartbeat_at = job.finished_at


def _mark_job_superseded(job: ProcessingJob, message: str) -> None:
    job.status = "failed"
    job.error_code = "superseded"
    job.error_message = message[:1000]
    job.finished_at = datetime.now(UTC)
    job.heartbeat_at = job.finished_at


def _mark_job_failed(asset: MediaAsset, job: ProcessingJob, exc: Exception) -> None:
    job.status = "failed"
    job.error_code = exc.__class__.__name__
    job.error_message = str(exc)[:1000]
    job.finished_at = datetime.now(UTC)
    job.heartbeat_at = job.finished_at
    asset.processing_status = "failed"
    asset.session.processing_status = "failed"


def _retention_deadline() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().media_retention_days)


async def _fail_and_retain_rendition(
    session: AsyncSession,
    rendition: MediaAsset | None,
) -> None:
    """Tombstone every incomplete rendition and retain its object for cleanup."""
    if rendition is None or rendition.processing_status == "ready":
        return
    rendition.processing_status = "failed"
    rendition.is_active = False
    rendition.archived_at = rendition.archived_at or datetime.now(UTC)
    await repository.schedule_storage_cleanup(
        session,
        [rendition],
        retain_until=_retention_deadline(),
    )


async def _enqueue_or_mark_failed(
    session: AsyncSession, asset: MediaAsset, job: ProcessingJob
) -> None:
    try:
        queue_job_id = await enqueue_asset_processing(
            asset.id,
            asset.revision,
            request_id=getattr(job, "request_id", None),
            processing_job_id=getattr(job, "id", None),
            duration_seconds=getattr(asset, "duration_seconds", None),
        )
        job.queue_job_id = queue_job_id
        await session.commit()
        PIPELINE_QUEUE_JOBS.labels("enqueued").inc()
    except Exception as exc:
        job.status = "failed"
        job.error_code = "enqueue_failed"
        job.error_message = str(exc)[:1000]
        job.finished_at = datetime.now(UTC)
        asset.processing_status = "failed"
        asset.session.processing_status = "failed"
        await session.commit()
        PIPELINE_QUEUE_JOBS.labels("enqueue_failed").inc()
        PIPELINE_JOBS.labels("enqueue_failed").inc()
        raise ServiceUnavailableError("Unable to enqueue audio processing job") from exc


def _latest_job(assets: list[MediaAsset]) -> ProcessingJob | None:
    jobs = [job for asset in assets for job in asset.processing_jobs]
    return max(jobs, key=lambda job: job.created_at, default=None)


async def _clear_processing_caches(recording: RecordingSession) -> None:
    await invalidate_atlas_cache(
        session_keys=(
            f"session:{recording.id}",
            f"session:{recording.slug}",
        )
    )
