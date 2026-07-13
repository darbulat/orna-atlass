from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.integrations.bird_analysis import (
    ANALYSIS_MODEL_VERSION,
    ANALYSIS_PROVIDER,
    analyze_audio_file,
)
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.media import repository
from orna_atlas.app.modules.media.audio import (
    extract_audio_metadata,
    generate_waveform,
    int_or_none as _int_or_none,
    public_audio_metadata,
    streaming_rendition_key,
    upload_streaming_rendition as _upload_streaming_rendition,
)
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob
from orna_atlas.app.modules.media.schemas import (
    MediaAssetCreate,
    ProcessingStatusRead,
)
from orna_atlas.app.modules.media.storage import materialize_storage
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.models import RecordingSession

PIPELINE_JOB_TYPE = "audio_pipeline"
SOURCE_AUDIO_KINDS = {"audio", "source_audio", "master_audio"}
STREAMING_RENDITION_KIND = "streaming_rendition"
logger = logging.getLogger(__name__)


async def require_asset(session: AsyncSession, asset_id: UUID) -> MediaAsset:
    asset = await repository.get_asset(session, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    return asset


async def create_asset_for_session(
    session: AsyncSession, session_id: UUID, data: MediaAssetCreate
) -> MediaAsset:
    recording = await sessions_service.require_session_for_admin(session, session_id)
    if await repository.get_asset_by_storage_key(session, data.storage_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Media asset storage key exists")

    asset = await repository.create_media_asset(session, recording, data)
    job = None
    if should_enqueue_audio_pipeline(data.kind, enqueue_processing=data.enqueue_processing):
        recording.processing_status = "queued"
        job = await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)
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


async def enqueue_asset_processing(asset_id: UUID) -> str:
    from orna_atlas.app.workers.audio_pipeline import enqueue_audio_processing

    return enqueue_audio_processing(asset_id)


async def retry_asset_processing(session: AsyncSession, asset_id: UUID) -> ProcessingStatusRead:
    asset = await require_asset(session, asset_id)
    if asset.kind not in SOURCE_AUDIO_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Audio processing can only be queued for source audio assets",
        )
    asset.processing_status = "queued"
    asset.session.processing_status = "queued"
    job = await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)
    await session.commit()
    await _enqueue_or_mark_failed(session, asset, job)
    return await processing_status_for_session(session, asset.session_id)


async def process_media_asset(session: AsyncSession, asset_id: UUID) -> MediaAsset:
    asset = await require_asset(session, asset_id)
    job = await repository.latest_processing_job(session, asset.id, job_type=PIPELINE_JOB_TYPE)
    if job is None:
        job = await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)

    _mark_job_running(asset, job)
    await session.commit()

    try:
        if asset.kind not in SOURCE_AUDIO_KINDS:
            raise ValueError("Audio pipeline can only process source audio assets")
        metadata = extract_audio_metadata(asset)
        waveform = generate_waveform(asset, metadata=metadata)
        _apply_pipeline_results(asset, metadata=metadata, waveform=waveform)
        rendition = await _ensure_streaming_rendition(session, asset, metadata=metadata)
        _upload_streaming_rendition(asset, rendition)
        await _analyze_and_store_bird_parts(session, asset)
        asset.session.processing_status = _recording_processing_status(asset.session)
        _mark_job_succeeded(job)
        await session.commit()
        await _clear_processing_caches(asset.session)
        await session.refresh(asset, attribute_names=["processing_jobs"])
        return asset
    except Exception as exc:
        _mark_job_failed(asset, job, exc)
        await session.commit()
        raise


async def _analyze_and_store_bird_parts(session: AsyncSession, asset: MediaAsset) -> None:
    """Run BirdNET analysis and persist detected bird vocal parts for the session."""
    location = asset.session.location
    lat = getattr(location, "exact_latitude", None)
    lon = getattr(location, "exact_longitude", None)
    recorded_at = asset.session.recorded_at

    try:
        with materialize_storage(asset.storage_key) as path:
            if path is None:
                raise FileNotFoundError(f"Source audio not found: {asset.storage_key}")
            detections = analyze_audio_file(
                path,
                lat=lat,
                lon=lon,
                recorded_at=recorded_at,
            )
        await sessions_repository.replace_bird_vocal_parts(
            session,
            asset.session_id,
            detections,
            analysis_provider=ANALYSIS_PROVIDER,
            analysis_model_version=ANALYSIS_MODEL_VERSION,
        )
        _record_bird_analysis_status(
            asset.session,
            status="succeeded",
            parts_count=len(detections),
        )
    except Exception as exc:
        logger.exception("BirdNET analysis failed for session %s", asset.session_id)
        await sessions_repository.replace_bird_vocal_parts(
            session,
            asset.session_id,
            [],
            analysis_provider=ANALYSIS_PROVIDER,
            analysis_model_version=ANALYSIS_MODEL_VERSION,
        )
        _record_bird_analysis_status(
            asset.session,
            status="failed",
            error_code=exc.__class__.__name__,
            error_message=str(exc)[:500],
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
    }
    if parts_count is not None:
        payload["parts_count"] = parts_count
    if error_code is not None:
        payload["error_code"] = error_code
    if error_message is not None:
        payload["error_message"] = error_message
    recording.metadata_ = {**metadata, "bird_analysis": payload}


def _apply_pipeline_results(asset: MediaAsset, *, metadata: dict, waveform: dict) -> None:
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
        "waveform": waveform,
    }
    asset.processing_status = "ready"


async def _ensure_streaming_rendition(
    session: AsyncSession, asset: MediaAsset, *, metadata: dict
) -> MediaAsset:
    storage_key = streaming_rendition_key(asset)
    rendition = await repository.get_asset_by_storage_key(session, storage_key)
    duration_seconds = _int_or_none(metadata.get("duration_seconds")) or asset.duration_seconds
    rendition_mime_type = "audio/wav"
    if rendition is None:
        rendition = MediaAsset(
            session=asset.session,
            kind=STREAMING_RENDITION_KIND,
            storage_key=storage_key,
            mime_type=rendition_mime_type,
            processing_status="ready",
            duration_seconds=duration_seconds,
            size_bytes=None,
            checksum=asset.checksum,
            metadata_={
                "bitrate_kbps": None,
                "source_asset_id": str(asset.id),
                "storage_policy": "deterministic_s3_key",
                "transcoding": "copy_source_wav",
            },
        )
        session.add(rendition)
        await session.flush()
    else:
        existing = rendition.metadata_ if isinstance(rendition.metadata_, dict) else {}
        rendition.processing_status = "ready"
        rendition.duration_seconds = duration_seconds
        rendition.checksum = rendition.checksum or asset.checksum
        rendition.metadata_ = {
            **existing,
            "bitrate_kbps": None,
            "source_asset_id": str(asset.id),
            "storage_policy": "deterministic_s3_key",
            "transcoding": "copy_source_wav",
        }
    return rendition


def _recording_processing_status(recording: RecordingSession) -> str:
    assets = list(recording.media_assets)
    source_assets = [asset for asset in assets if asset.kind in SOURCE_AUDIO_KINDS]
    if not source_assets:
        return "pending"
    if any(asset.processing_status == "failed" for asset in source_assets):
        return "failed"
    has_rendition = any(
        asset.kind == STREAMING_RENDITION_KIND and asset.processing_status == "ready"
        for asset in assets
    )
    if all(asset.processing_status == "ready" for asset in source_assets) and has_rendition:
        return "ready"
    if any(asset.processing_status == "processing" for asset in source_assets):
        return "processing"
    return "queued"


def _mark_job_running(asset: MediaAsset, job: ProcessingJob) -> None:
    now = datetime.now(UTC)
    job.status = "running"
    job.attempt_count += 1
    job.error_code = None
    job.error_message = None
    job.started_at = now
    job.finished_at = None
    asset.processing_status = "processing"
    asset.session.processing_status = "processing"


def _mark_job_succeeded(job: ProcessingJob) -> None:
    job.status = "succeeded"
    job.finished_at = datetime.now(UTC)


def _mark_job_failed(asset: MediaAsset, job: ProcessingJob, exc: Exception) -> None:
    job.status = "failed"
    job.error_code = exc.__class__.__name__
    job.error_message = str(exc)[:1000]
    job.finished_at = datetime.now(UTC)
    asset.processing_status = "failed"
    asset.session.processing_status = "failed"


async def _enqueue_or_mark_failed(
    session: AsyncSession, asset: MediaAsset, job: ProcessingJob
) -> None:
    try:
        await enqueue_asset_processing(asset.id)
    except Exception as exc:
        job.status = "failed"
        job.error_code = "enqueue_failed"
        job.error_message = str(exc)[:1000]
        job.finished_at = datetime.now(UTC)
        asset.processing_status = "failed"
        asset.session.processing_status = "failed"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to enqueue audio processing job",
        ) from exc


def _latest_job(assets: list[MediaAsset]) -> ProcessingJob | None:
    jobs = [job for asset in assets for job in asset.processing_jobs]
    return max(jobs, key=lambda job: job.created_at, default=None)


async def _clear_processing_caches(recording: RecordingSession) -> None:
    redis = get_redis_client()
    try:
        keys = [
            key
            async for key in redis.scan_iter("atlas:points:*")
        ]
        keys.extend(
            [
                f"session:{recording.id}",
                f"session:{recording.slug}",
            ]
        )
        if keys:
            await redis.delete(*keys)
    except Exception:
        pass
    finally:
        await redis.aclose()
