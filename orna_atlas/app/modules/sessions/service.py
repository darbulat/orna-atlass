from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.locations.service import require_location
from orna_atlas.app.modules.sessions import repository
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions.schemas import (
    SessionAnnotationRead,
    SessionCreate,
    SessionUpdate,
    WaveformRead,
)


async def require_session(session: AsyncSession, session_id: UUID) -> RecordingSession:
    recording = await repository.get_session(session, session_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


async def require_session_for_admin(session: AsyncSession, session_id: UUID) -> RecordingSession:
    recording = await repository.get_session_for_admin(session, session_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


async def require_public_session_by_slug(session: AsyncSession, slug: str) -> RecordingSession:
    recording = await repository.get_session_by_slug(session, slug)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


def waveform_for_session(recording: RecordingSession) -> WaveformRead:
    metadata = recording.metadata_ if isinstance(recording.metadata_, dict) else {}
    waveform = metadata.get("waveform") if isinstance(metadata.get("waveform"), dict) else {}
    return WaveformRead(
        session_id=recording.id,
        duration_seconds=recording.duration_seconds,
        **waveform,
    )


def annotations_for_session(recording: RecordingSession) -> list[SessionAnnotationRead]:
    metadata = recording.metadata_ if isinstance(recording.metadata_, dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), list) else []
    return [SessionAnnotationRead.model_validate(annotation) for annotation in annotations]


async def create_session(session: AsyncSession, data: SessionCreate) -> RecordingSession:
    await require_location(session, data.location_id)
    if await repository.get_session_by_slug_for_admin(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    return await repository.create_session(session, data)


async def update_session(session: AsyncSession, session_id: UUID, data: SessionUpdate) -> RecordingSession:
    recording = await require_session_for_admin(session, session_id)
    if data.location_id is not None:
        await require_location(session, data.location_id)
    if (
        data.slug
        and data.slug != recording.slug
        and await repository.get_session_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    return await repository.update_session(session, recording, data)
