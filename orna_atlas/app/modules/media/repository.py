from uuid import UUID

from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.media.models import (
    HlsProcessingJob,
    MediaAsset,
    ProcessingJob,
    RecordingSegment,
    StorageCleanupJob,
)
from orna_atlas.app.modules.media.schemas import MediaAssetCreate, MediaAssetUpdate
from orna_atlas.app.modules.sessions.models import RecordingSession


def _payload(data: MediaAssetCreate | MediaAssetUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    payload.pop("enqueue_processing", None)
    if "metadata" in payload:
        payload["metadata_"] = payload.pop("metadata")
    return payload


async def get_asset(session: AsyncSession, asset_id: UUID) -> MediaAsset | None:
    result = await session.execute(
        select(MediaAsset)
        .options(
            selectinload(MediaAsset.processing_jobs),
            selectinload(MediaAsset.session)
            .selectinload(RecordingSession.media_assets),
            selectinload(MediaAsset.session)
            .selectinload(RecordingSession.location),
        )
        .where(MediaAsset.id == asset_id)
    )
    return result.scalar_one_or_none()


async def get_asset_for_processing(session: AsyncSession, asset_id: UUID) -> MediaAsset | None:
    result = await session.execute(
        select(MediaAsset)
        .options(
            selectinload(MediaAsset.processing_jobs),
            selectinload(MediaAsset.session).selectinload(RecordingSession.media_assets),
            selectinload(MediaAsset.session).selectinload(RecordingSession.location),
        )
        .where(MediaAsset.id == asset_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_asset_by_storage_key(session: AsyncSession, storage_key: str) -> MediaAsset | None:
    result = await session.execute(select(MediaAsset).where(MediaAsset.storage_key == storage_key))
    return result.scalar_one_or_none()


async def list_recording_segments(
    session: AsyncSession, session_id: UUID, *, for_update: bool = False
) -> list[RecordingSegment]:
    query = (
        select(RecordingSegment)
        .options(selectinload(RecordingSegment.source_asset))
        .where(RecordingSegment.session_id == session_id)
        .order_by(RecordingSegment.sequence_number)
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return list(result.scalars())


async def create_recording_segment(
    session: AsyncSession,
    *,
    recording: RecordingSession,
    source_asset: MediaAsset,
    sequence_number: int,
) -> RecordingSegment:
    segment = RecordingSegment(
        session=recording,
        source_asset=source_asset,
        sequence_number=sequence_number,
    )
    session.add(segment)
    await session.flush()
    return segment


async def create_hls_processing_job(
    session: AsyncSession, *, session_id: UUID, source_fingerprint: str
) -> HlsProcessingJob:
    job = HlsProcessingJob(session_id=session_id, source_fingerprint=source_fingerprint)
    session.add(job)
    await session.flush()
    return job


async def get_hls_processing_job(
    session: AsyncSession, job_id: UUID, *, for_update: bool = False
) -> HlsProcessingJob | None:
    query = select(HlsProcessingJob).where(HlsProcessingJob.id == job_id)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def latest_hls_processing_job(
    session: AsyncSession, session_id: UUID, *, for_update: bool = False
) -> HlsProcessingJob | None:
    query = (
        select(HlsProcessingJob)
        .where(HlsProcessingJob.session_id == session_id)
        .order_by(HlsProcessingJob.created_at.desc())
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def list_assets_for_session(session: AsyncSession, session_id: UUID) -> list[MediaAsset]:
    result = await session.execute(
        select(MediaAsset)
        .options(selectinload(MediaAsset.processing_jobs))
        .where(MediaAsset.session_id == session_id)
        .order_by(MediaAsset.created_at.desc())
    )
    return list(result.scalars())


async def create_media_asset(
    session: AsyncSession,
    recording: RecordingSession,
    data: MediaAssetCreate,
    *,
    revision: int = 1,
    is_active: bool = True,
) -> MediaAsset:
    asset = MediaAsset(
        session=recording,
        revision=revision,
        is_active=is_active,
        **_payload(data),
    )
    session.add(asset)
    await session.flush()
    return asset


async def active_source_assets_for_update(
    session: AsyncSession, session_id: UUID
) -> list[MediaAsset]:
    result = await session.execute(
        select(MediaAsset)
        .where(
            MediaAsset.session_id == session_id,
            MediaAsset.kind.in_(("audio", "source_audio", "master_audio")),
            MediaAsset.is_active.is_(True),
            MediaAsset.archived_at.is_(None),
        )
        .order_by(MediaAsset.revision.desc())
        .with_for_update()
    )
    return list(result.scalars())


async def archive_assets(session: AsyncSession, assets: list[MediaAsset]) -> None:
    now = datetime.now(UTC)
    for asset in assets:
        asset.is_active = False
        asset.archived_at = now
    await session.flush()


async def active_processing_job(
    session: AsyncSession, asset_id: UUID, *, job_type: str
) -> ProcessingJob | None:
    result = await session.execute(
        select(ProcessingJob)
        .where(
            ProcessingJob.asset_id == asset_id,
            ProcessingJob.job_type == job_type,
            ProcessingJob.status.in_(("queued", "running")),
        )
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def activate_rendition(
    session: AsyncSession,
    rendition: MediaAsset,
) -> list[MediaAsset]:
    result = await session.execute(
        select(MediaAsset)
        .where(
            MediaAsset.session_id == rendition.session_id,
            MediaAsset.kind == "streaming_rendition",
            MediaAsset.is_active.is_(True),
            MediaAsset.archived_at.is_(None),
            MediaAsset.id != rendition.id,
        )
        .with_for_update()
    )
    archived = list(result.scalars())
    await archive_assets(session, archived)
    rendition.processing_status = "ready"
    rendition.is_active = True
    rendition.archived_at = None
    await session.flush()
    return archived


async def incomplete_streaming_renditions_for_recovery(
    session: AsyncSession,
    asset: MediaAsset,
) -> list[MediaAsset]:
    """Find unactivated rendition attempts left behind by a timed-out pipeline."""
    result = await session.execute(
        select(MediaAsset)
        .where(
            MediaAsset.session_id == asset.session_id,
            MediaAsset.kind == "streaming_rendition",
            MediaAsset.is_active.is_(False),
            MediaAsset.archived_at.is_(None),
        )
        .with_for_update()
    )
    return list(result.scalars())


async def delete_asset(session: AsyncSession, asset: MediaAsset) -> None:
    await session.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
    await session.flush()


async def schedule_storage_cleanup(
    session: AsyncSession,
    assets: list[MediaAsset],
    *,
    retain_until: datetime,
) -> list[StorageCleanupJob]:
    """Create one durable cleanup request per storage key without duplicating retries."""
    candidates = [
        asset for asset in assets if getattr(asset, "storage_deleted_at", None) is None
    ]
    if not candidates:
        return []
    # Serialize query-then-create on the canonical asset rows so concurrent
    # archive requests cannot race into the cleanup-job unique constraints.
    await session.execute(
        select(MediaAsset.id)
        .where(MediaAsset.id.in_([asset.id for asset in candidates]))
        .order_by(MediaAsset.id)
        .with_for_update()
    )
    keys = [asset.storage_key for asset in candidates]
    result = await session.execute(
        select(StorageCleanupJob).where(StorageCleanupJob.storage_key.in_(keys))
    )
    existing = {job.storage_key: job for job in result.scalars()}
    jobs: list[StorageCleanupJob] = []
    for asset in candidates:
        job = existing.get(asset.storage_key)
        object_keys = (
            (getattr(asset, "metadata_", None) or {}).get("object_keys")
            if getattr(asset, "kind", None) == "streaming_rendition"
            else None
        )
        if job is None:
            job = StorageCleanupJob(
                asset=asset,
                storage_key=asset.storage_key,
                object_keys=object_keys,
                retain_until=retain_until,
                next_attempt_at=retain_until,
            )
            session.add(job)
        elif job.status != "succeeded":
            if object_keys:
                job.object_keys = object_keys
            if retain_until < job.retain_until:
                job.retain_until = retain_until
                job.next_attempt_at = min(job.next_attempt_at, retain_until)
        jobs.append(job)
    await session.flush()
    return jobs


async def get_storage_cleanup_job_for_update(
    session: AsyncSession, job_id: UUID
) -> StorageCleanupJob | None:
    result = await session.execute(
        select(StorageCleanupJob)
        .options(selectinload(StorageCleanupJob.asset))
        .where(StorageCleanupJob.id == job_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def due_storage_cleanup_job_ids(
    session: AsyncSession,
    *,
    now: datetime,
    stale_before: datetime,
    limit: int = 50,
) -> list[UUID]:
    result = await session.execute(
        select(StorageCleanupJob.id)
        .where(
            StorageCleanupJob.next_attempt_at <= now,
            or_(
                StorageCleanupJob.status.in_(("pending", "failed")),
                and_(
                    StorageCleanupJob.status == "running",
                    StorageCleanupJob.locked_at < stale_before,
                ),
            ),
        )
        .order_by(StorageCleanupJob.next_attempt_at, StorageCleanupJob.created_at)
        .limit(limit)
    )
    return list(result.scalars())


async def update_media_asset(
    session: AsyncSession, asset: MediaAsset, data: MediaAssetUpdate
) -> MediaAsset:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(asset, key, value)
    await session.flush()
    return asset


async def create_processing_job(
    session: AsyncSession,
    asset: MediaAsset,
    *,
    job_type: str,
    status: str = "queued",
    request_id: str | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        asset=asset,
        job_type=job_type,
        status=status,
        request_id=request_id,
    )
    session.add(job)
    await session.flush()
    return job


async def latest_processing_job(
    session: AsyncSession, asset_id: UUID, *, job_type: str | None = None
) -> ProcessingJob | None:
    statement = select(ProcessingJob).where(ProcessingJob.asset_id == asset_id)
    if job_type:
        statement = statement.where(ProcessingJob.job_type == job_type)
    result = await session.execute(statement.order_by(ProcessingJob.created_at.desc()).limit(1))
    return result.scalar_one_or_none()


async def stale_processing_asset_ids(
    session: AsyncSession,
    *,
    stale_before: datetime,
    limit: int = 25,
) -> list[UUID]:
    result = await session.execute(
        select(ProcessingJob.asset_id)
        .where(
            or_(
                and_(
                    ProcessingJob.status == "running",
                    ProcessingJob.heartbeat_at.is_not(None),
                    ProcessingJob.heartbeat_at < stale_before,
                ),
                and_(
                    ProcessingJob.status == "queued",
                    func.coalesce(
                        ProcessingJob.updated_at,
                        ProcessingJob.created_at,
                    )
                    < stale_before,
                ),
            )
        )
        .order_by(
            func.coalesce(
                ProcessingJob.heartbeat_at,
                ProcessingJob.updated_at,
                ProcessingJob.created_at,
            ),
            ProcessingJob.created_at,
        )
        .limit(limit)
    )
    return list(result.scalars())
