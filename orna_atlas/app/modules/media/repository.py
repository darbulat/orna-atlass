from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob
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


async def get_asset_by_storage_key(session: AsyncSession, storage_key: str) -> MediaAsset | None:
    result = await session.execute(select(MediaAsset).where(MediaAsset.storage_key == storage_key))
    return result.scalar_one_or_none()


async def list_assets_for_session(session: AsyncSession, session_id: UUID) -> list[MediaAsset]:
    result = await session.execute(
        select(MediaAsset)
        .options(selectinload(MediaAsset.processing_jobs))
        .where(MediaAsset.session_id == session_id)
        .order_by(MediaAsset.created_at.desc())
    )
    return list(result.scalars())


async def create_media_asset(
    session: AsyncSession, recording: RecordingSession, data: MediaAssetCreate
) -> MediaAsset:
    asset = MediaAsset(session=recording, **_payload(data))
    session.add(asset)
    await session.flush()
    return asset


async def update_media_asset(
    session: AsyncSession, asset: MediaAsset, data: MediaAssetUpdate
) -> MediaAsset:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(asset, key, value)
    await session.flush()
    return asset


async def create_processing_job(
    session: AsyncSession, asset: MediaAsset, *, job_type: str, status: str = "queued"
) -> ProcessingJob:
    job = ProcessingJob(asset=asset, job_type=job_type, status=status)
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
