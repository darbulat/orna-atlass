from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.sessions import repository, service
from orna_atlas.app.modules.sessions.schemas import SessionRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
async def list_sessions(limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_db_session)):
    return await repository.list_sessions(session, limit=limit, offset=offset)


@router.get("/{locator}", response_model=SessionRead)
async def get_session(locator: str, session: AsyncSession = Depends(get_db_session)):
    try:
        session_id = UUID(locator)
    except ValueError:
        return await service.require_public_session_by_slug(session, locator)
    return await service.require_session(session, session_id)
