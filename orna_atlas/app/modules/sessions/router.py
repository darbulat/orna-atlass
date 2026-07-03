from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.sessions import repository, service
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionRead, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
async def list_sessions(limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_db_session)):
    return await repository.list_sessions(session, limit=limit, offset=offset)


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreate, session: AsyncSession = Depends(get_db_session)):
    return await service.create_session(session, data)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    return await service.require_session(session, session_id)


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: UUID, data: SessionUpdate, session: AsyncSession = Depends(get_db_session)):
    return await service.update_session(session, session_id, data)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: UUID, session: AsyncSession = Depends(get_db_session)):
    recording = await service.require_session(session, session_id)
    await repository.delete_session(session, recording)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
