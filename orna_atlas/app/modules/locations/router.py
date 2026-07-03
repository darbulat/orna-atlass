from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.locations import repository, service
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationRead, LocationUpdate

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
async def list_locations(limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_db_session)):
    return await repository.list_locations(session, limit=limit, offset=offset)


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(data: LocationCreate, session: AsyncSession = Depends(get_db_session)):
    return await service.create_location(session, data)


@router.get("/{location_id}", response_model=LocationRead)
async def get_location(location_id: UUID, session: AsyncSession = Depends(get_db_session)):
    return await service.require_location(session, location_id)


@router.patch("/{location_id}", response_model=LocationRead)
async def update_location(location_id: UUID, data: LocationUpdate, session: AsyncSession = Depends(get_db_session)):
    return await service.update_location(session, location_id, data)


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(location_id: UUID, session: AsyncSession = Depends(get_db_session)):
    location = await service.require_location(session, location_id)
    await repository.delete_location(session, location)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
