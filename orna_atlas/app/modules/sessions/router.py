from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.rate_limit import playback_rate_limit
from orna_atlas.app.core.pagination import FeaturedLimit, PageLimit, PageOffset
from orna_atlas.app.core.security import CurrentUser, get_optional_active_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.sessions import service
from orna_atlas.app.modules.sessions.schemas import (
    BirdPartsResponse,
    FeaturedSessionRead,
    PlaybackGrantRead,
    PublicSessionAnnotationRead,
    PublicSessionRead,
    SessionDetailRead,
    WaveformRead,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/featured", response_model=list[FeaturedSessionRead])
async def list_featured_sessions(
    limit: FeaturedLimit = 12, session: AsyncSession = Depends(get_db_session)
):
    return await service.list_featured_sessions(session, limit=limit)


@router.get("", response_model=list[PublicSessionRead])
async def list_sessions(
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    current_user: CurrentUser | None = Depends(get_optional_active_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_visible_sessions(
        session, current_user, limit=limit, offset=offset
    )


@router.post(
    "/{session_id}/playback-grants",
    response_model=PlaybackGrantRead,
    dependencies=[Depends(playback_rate_limit)],
)
async def create_playback_grant(
    session_id: UUID,
    request: Request,
    current_user: CurrentUser | None = Depends(get_optional_active_user),
    session: AsyncSession = Depends(get_db_session),
):
    recording = await service.require_session_for_admin(session, session_id)
    return await service.authorize_playback_grant(
        session, recording, current_user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/{session_id}/bird-parts", response_model=BirdPartsResponse)
async def get_bird_parts(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return service.bird_parts_for_session(recording)


@router.get("/{session_id}/waveform", response_model=WaveformRead)
async def get_waveform(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return service.waveform_for_session(recording)


@router.get("/{session_id}/annotations", response_model=list[PublicSessionAnnotationRead])
async def get_annotations(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    return service.annotations_for_session(recording)


@router.get("/{locator}", response_model=SessionDetailRead)
async def get_session(
    locator: str,
    current_user: CurrentUser | None = Depends(get_optional_active_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.require_visible_session(session, locator, current_user)
