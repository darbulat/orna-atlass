from __future__ import annotations

import hashlib
import math
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.media import repository
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob
from orna_atlas.app.modules.media.schemas import (
    MediaAssetCreate,
    ProcessingStatusRead,
)
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.models import RecordingSession

PIPELINE_JOB_TYPE = "audio_pipeline"
SOURCE_AUDIO_KINDS = {"audio", "source_audio", "master_audio"}
STREAMING_RENDITION_KIND = "streaming_rendition"
WAVEFORM_BUCKETS = 64


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
    if data.enqueue_processing:
        recording.processing_status = "queued"
        await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)
    await session.commit()
    await session.refresh(asset, attribute_names=["processing_jobs"])

    if data.enqueue_processing:
        await enqueue_asset_processing(asset.id)
    return asset


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


async def enqueue_asset_processing(asset_id: UUID) -> str | None:
    from orna_atlas.app.workers.audio_pipeline import enqueue_audio_processing

    return enqueue_audio_processing(asset_id)


async def retry_asset_processing(session: AsyncSession, asset_id: UUID) -> ProcessingStatusRead:
    asset = await require_asset(session, asset_id)
    asset.processing_status = "queued"
    asset.session.processing_status = "queued"
    await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)
    await session.commit()
    await enqueue_asset_processing(asset.id)
    return await processing_status_for_session(session, asset.session_id)


async def process_media_asset(session: AsyncSession, asset_id: UUID) -> MediaAsset:
    asset = await require_asset(session, asset_id)
    job = await repository.latest_processing_job(session, asset.id, job_type=PIPELINE_JOB_TYPE)
    if job is None:
        job = await repository.create_processing_job(session, asset, job_type=PIPELINE_JOB_TYPE)

    _mark_job_running(asset, job)
    await session.commit()

    try:
        metadata = extract_audio_metadata(asset)
        waveform = generate_waveform(asset, metadata=metadata)
        _apply_pipeline_results(asset, metadata=metadata, waveform=waveform)
        await _ensure_streaming_rendition(session, asset, metadata=metadata)
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


def extract_audio_metadata(asset: MediaAsset) -> dict:
    metadata = asset.metadata_ if isinstance(asset.metadata_, dict) else {}
    path = storage_key_path(asset.storage_key)
    if path is not None:
        wav_metadata = _extract_wav_metadata(path)
        return {
            **wav_metadata,
            "checksum": asset.checksum or sha256_file(path),
            "source": "wave",
            "storage_key": asset.storage_key,
        }

    declared_duration = asset.duration_seconds or _int_or_none(metadata.get("duration_seconds"))
    return {
        "bit_depth": metadata.get("bit_depth"),
        "channels": metadata.get("channels"),
        "checksum": asset.checksum,
        "duration_seconds": declared_duration,
        "frame_rate_hz": metadata.get("frame_rate_hz"),
        "size_bytes": asset.size_bytes,
        "source": "declared",
        "storage_key": asset.storage_key,
    }


def generate_waveform(asset: MediaAsset, *, metadata: dict | None = None) -> dict:
    path = storage_key_path(asset.storage_key)
    if path is not None:
        peaks = _waveform_peaks_from_wav(path)
    else:
        peaks = _deterministic_peaks(asset)

    duration_seconds = _int_or_none((metadata or {}).get("duration_seconds")) or asset.duration_seconds
    sample_rate = 1
    if duration_seconds and duration_seconds > 0:
        sample_rate = max(1, round(len(peaks) / duration_seconds))
    return {
        "peaks": peaks,
        "sample_rate": sample_rate,
        "status": "generated",
    }


def storage_key_path(storage_key: str) -> Path | None:
    candidate = storage_key[7:] if storage_key.startswith("file://") else storage_key
    path = Path(candidate)
    if path.exists() and path.is_file():
        return path
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def streaming_rendition_key(asset: MediaAsset) -> str:
    return f"sessions/{asset.session_id}/renditions/stream_320.mp3"


def _extract_wav_metadata(path: Path) -> dict:
    with wave.open(str(path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        frame_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
    duration = int(round(frame_count / frame_rate)) if frame_rate else None
    return {
        "bit_depth": sample_width * 8,
        "channels": channels,
        "duration_seconds": duration,
        "frame_count": frame_count,
        "frame_rate_hz": frame_rate,
        "size_bytes": path.stat().st_size,
    }


def _waveform_peaks_from_wav(path: Path, buckets: int = WAVEFORM_BUCKETS) -> list[float]:
    with wave.open(str(path), "rb") as wav_file:
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(wav_file.getnframes())

    if not raw:
        return []
    samples = _pcm_samples(raw, sample_width)
    if not samples:
        return []

    bucket_size = max(1, math.ceil(len(samples) / buckets))
    max_amplitude = float(max(1, 2 ** (sample_width * 8 - 1) - 1))
    peaks = []
    for offset in range(0, len(samples), bucket_size):
        bucket = samples[offset : offset + bucket_size]
        peak = max(abs(sample) for sample in bucket) / max_amplitude
        peaks.append(round(min(1.0, peak), 4))
    return peaks


def _pcm_samples(raw: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [byte - 128 for byte in raw]
    if sample_width == 2:
        samples = array("h")
        samples.frombytes(raw)
        return list(samples)
    if sample_width == 3:
        return [
            int.from_bytes(raw[index : index + 3], "little", signed=True)
            for index in range(0, len(raw) - 2, 3)
        ]
    if sample_width == 4:
        samples = array("i")
        samples.frombytes(raw)
        return list(samples)
    return []


def _deterministic_peaks(asset: MediaAsset, buckets: int = WAVEFORM_BUCKETS) -> list[float]:
    seed = hashlib.sha256(f"{asset.storage_key}:{asset.checksum or ''}".encode()).digest()
    values = []
    while len(values) < buckets:
        seed = hashlib.sha256(seed).digest()
        values.extend(seed)
    return [round(0.05 + (value / 255) * 0.9, 4) for value in values[:buckets]]


def _apply_pipeline_results(asset: MediaAsset, *, metadata: dict, waveform: dict) -> None:
    existing = asset.metadata_ if isinstance(asset.metadata_, dict) else {}
    asset.metadata_ = {
        **existing,
        "audio_metadata": metadata,
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
        "audio_metadata": metadata,
        "waveform": waveform,
    }
    asset.processing_status = "ready"


async def _ensure_streaming_rendition(
    session: AsyncSession, asset: MediaAsset, *, metadata: dict
) -> MediaAsset:
    storage_key = streaming_rendition_key(asset)
    rendition = await repository.get_asset_by_storage_key(session, storage_key)
    duration_seconds = _int_or_none(metadata.get("duration_seconds")) or asset.duration_seconds
    if rendition is None:
        rendition = MediaAsset(
            session=asset.session,
            kind=STREAMING_RENDITION_KIND,
            storage_key=storage_key,
            mime_type="audio/mpeg",
            processing_status="ready",
            duration_seconds=duration_seconds,
            size_bytes=None,
            checksum=asset.checksum,
            metadata_={
                "bitrate_kbps": 320,
                "source_asset_id": str(asset.id),
                "storage_policy": "deterministic_s3_key",
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
            "bitrate_kbps": 320,
            "source_asset_id": str(asset.id),
            "storage_policy": "deterministic_s3_key",
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


def _latest_job(assets: list[MediaAsset]) -> ProcessingJob | None:
    jobs = [job for asset in assets for job in asset.processing_jobs]
    return max(jobs, key=lambda job: job.created_at, default=None)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
