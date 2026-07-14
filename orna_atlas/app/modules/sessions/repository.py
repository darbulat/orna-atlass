from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.integrations.bird_analysis import BirdDetection
from orna_atlas.app.modules.media.models import MediaAsset  # noqa: F401
from orna_atlas.app.modules.sessions.models import BirdVocalPart, RecordingSession
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionUpdate
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.public import publicly_discoverable_clause


def _payload(data: SessionCreate | SessionUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    if "metadata" in payload:
        payload["metadata_"] = payload.pop("metadata")
    return payload


def _session_load_options():
    return (
        selectinload(RecordingSession.media_assets).selectinload(MediaAsset.processing_jobs),
        selectinload(RecordingSession.location),
        selectinload(RecordingSession.bird_vocal_parts),
    )


async def list_featured_sessions(session: AsyncSession, *, limit: int = 12) -> list[RecordingSession]:
    result = await session.execute(
        select(RecordingSession)
        .join(Location)
        .options(selectinload(RecordingSession.location))
        .where(
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
            RecordingSession.is_featured.is_(True),
            publicly_discoverable_clause(),
            RecordingSession.media_assets.any(
                (MediaAsset.kind == "streaming_rendition")
                & (MediaAsset.processing_status == "ready")
                & (MediaAsset.is_active.is_(True))
                & (MediaAsset.archived_at.is_(None))
            ),
        )
        .order_by(RecordingSession.featured_sort_order.nulls_last(), RecordingSession.recorded_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def list_bird_vocal_parts(session: AsyncSession, session_id: UUID) -> list[BirdVocalPart]:
    result = await session.execute(
        select(BirdVocalPart)
        .where(BirdVocalPart.session_id == session_id)
        .order_by(BirdVocalPart.starts_at_seconds)
    )
    return list(result.scalars())


async def list_sessions(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    access_levels: tuple[str, ...] = ("public",),
) -> list[RecordingSession]:
    result = await session.execute(
        select(RecordingSession)
        .join(Location)
        .options(*_session_load_options())
        .where(
            RecordingSession.access_level.in_(access_levels),
            RecordingSession.publication_status == "published",
            publicly_discoverable_clause(),
        )
        .order_by(RecordingSession.recorded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


async def get_session(session: AsyncSession, session_id: UUID) -> RecordingSession | None:
    return await get_visible_session(session, session_id, access_levels=("public",))


async def get_visible_session(
    session: AsyncSession,
    session_id: UUID,
    *,
    access_levels: tuple[str, ...],
) -> RecordingSession | None:
    result = await session.execute(
        select(RecordingSession)
        .join(Location)
        .options(*_session_load_options())
        .where(
            RecordingSession.id == session_id,
            RecordingSession.access_level.in_(access_levels),
            RecordingSession.publication_status == "published",
            publicly_discoverable_clause(),
        )
    )
    return result.scalar_one_or_none()


async def get_session_for_admin(session: AsyncSession, session_id: UUID) -> RecordingSession | None:
    result = await session.execute(
        select(RecordingSession)
        .options(*_session_load_options())
        .where(RecordingSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_session_by_slug(session: AsyncSession, slug: str) -> RecordingSession | None:
    return await get_visible_session_by_slug(session, slug, access_levels=("public",))


async def get_visible_session_by_slug(
    session: AsyncSession,
    slug: str,
    *,
    access_levels: tuple[str, ...],
) -> RecordingSession | None:
    result = await session.execute(
        select(RecordingSession)
        .join(Location)
        .options(*_session_load_options())
        .where(
            RecordingSession.slug == slug,
            RecordingSession.access_level.in_(access_levels),
            RecordingSession.publication_status == "published",
            publicly_discoverable_clause(),
        )
    )
    return result.scalar_one_or_none()


async def get_session_by_slug_for_admin(session: AsyncSession, slug: str) -> RecordingSession | None:
    result = await session.execute(select(RecordingSession).where(RecordingSession.slug == slug))
    return result.scalar_one_or_none()


async def create_session(session: AsyncSession, data: SessionCreate) -> RecordingSession:
    recording = RecordingSession(**_payload(data))
    session.add(recording)
    await session.flush()
    return recording


async def update_session(session: AsyncSession, recording: RecordingSession, data: SessionUpdate) -> RecordingSession:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(recording, key, value)
    await session.flush()
    return recording


async def delete_session(session: AsyncSession, recording: RecordingSession) -> None:
    await session.delete(recording)
    await session.flush()


async def replace_bird_vocal_parts(
    session: AsyncSession,
    session_id: UUID,
    detections: list[BirdDetection],
    *,
    analysis_provider: str,
    analysis_model_version: str,
) -> list[BirdVocalPart]:
    """Replace bird vocal parts for a session and analysis model version."""
    await session.execute(
        delete(BirdVocalPart).where(
            BirdVocalPart.session_id == session_id,
            BirdVocalPart.analysis_provider == analysis_provider,
            BirdVocalPart.analysis_model_version == analysis_model_version,
        )
    )
    parts = [
        BirdVocalPart(
            session_id=session_id,
            species_code=detection.species_code,
            species_common_name=detection.species_common_name,
            species_scientific_name=detection.species_scientific_name,
            starts_at_seconds=detection.starts_at_seconds,
            ends_at_seconds=detection.ends_at_seconds,
            confidence=detection.confidence,
            call_type=detection.call_type,
            analysis_provider=analysis_provider,
            analysis_model_version=analysis_model_version,
            metadata_=detection.metadata,
        )
        for detection in detections
    ]
    session.add_all(parts)
    await session.flush()
    return parts
