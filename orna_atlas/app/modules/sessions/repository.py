from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.media.models import MediaAsset  # noqa: F401
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionUpdate


def _payload(data: SessionCreate | SessionUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    if "metadata" in payload:
        payload["metadata_"] = payload.pop("metadata")
    return payload


async def list_sessions(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[RecordingSession]:
    result = await session.execute(
        select(RecordingSession)
        .options(selectinload(RecordingSession.media_assets))
        .order_by(RecordingSession.recorded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


async def get_session(session: AsyncSession, session_id: UUID) -> RecordingSession | None:
    result = await session.execute(
        select(RecordingSession)
        .options(selectinload(RecordingSession.media_assets))
        .where(RecordingSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_session_by_slug(session: AsyncSession, slug: str) -> RecordingSession | None:
    result = await session.execute(select(RecordingSession).where(RecordingSession.slug == slug))
    return result.scalar_one_or_none()


async def create_session(session: AsyncSession, data: SessionCreate) -> RecordingSession:
    recording = RecordingSession(**_payload(data))
    session.add(recording)
    await session.commit()
    await session.refresh(recording, attribute_names=["media_assets"])
    return recording


async def update_session(session: AsyncSession, recording: RecordingSession, data: SessionUpdate) -> RecordingSession:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(recording, key, value)
    await session.commit()
    await session.refresh(recording, attribute_names=["media_assets"])
    return recording


async def delete_session(session: AsyncSession, recording: RecordingSession) -> None:
    await session.delete(recording)
    await session.commit()
