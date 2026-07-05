from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.sessions import repository, service
from orna_atlas.app.modules.sessions.schemas import (
    PlaybackGrantRead,
    SessionAnnotationRead,
    SessionDetailRead,
    SessionRead,
    WaveformRead,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
async def list_sessions(limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_db_session)):
    return await repository.list_sessions(session, limit=limit, offset=offset)


@router.post("/{session_id}/playback-grants", response_model=PlaybackGrantRead)
async def create_playback_grant(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return PlaybackGrantRead.mock_for_session(recording.id)


@router.get("/{session_id}/waveform", response_model=WaveformRead)
async def get_waveform(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return service.waveform_for_session(recording)


@router.get("/{session_id}/annotations", response_model=list[SessionAnnotationRead])
async def get_annotations(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return service.annotations_for_session(recording)


@router.get("/{session_id}/mock-stream", include_in_schema=False)
async def get_mock_stream(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    await service.require_session(session, session_id)
    return Response(content=service.mock_wav_bytes(), media_type="audio/wav")


@router.get("/{locator}", response_model=SessionDetailRead)
async def get_session(locator: str, session: AsyncSession = Depends(get_db_session)):
    try:
        session_id = UUID(locator)
    except ValueError:
        return await service.require_public_session_by_slug(session, locator)
    return await service.require_session(session, session_id)
