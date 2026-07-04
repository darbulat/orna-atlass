from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.locations import repository as locations_repository
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationRead, LocationUpdate
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionRead, SessionUpdate

router = APIRouter(prefix="/admin", tags=["admin"])
admin_dependency = Depends(get_current_admin)


@router.get("/me")
async def read_admin(current_user: CurrentUser = admin_dependency) -> dict[str, object]:
    return {"id": current_user.id, "is_admin": current_user.is_admin, "mode": "local"}


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    data: LocationCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.create_location(session, data)


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: UUID,
    data: LocationUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.update_location(session, location_id, data)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    location = await locations_service.require_location(session, location_id)
    await locations_repository.delete_location(session, location)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await sessions_service.create_session(session, data)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: UUID,
    data: SessionUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await sessions_service.update_session(session, session_id, data)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    recording = await sessions_service.require_session_for_admin(session, session_id)
    await sessions_repository.delete_session(session, recording)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
