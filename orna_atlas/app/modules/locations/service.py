from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.locations import repository
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate


async def require_location(session: AsyncSession, location_id: UUID) -> Location:
    location = await repository.get_location(session, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


async def require_location_by_slug(session: AsyncSession, slug: str) -> Location:
    location = await repository.get_location_by_slug(session, slug)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


async def create_location(session: AsyncSession, data: LocationCreate) -> Location:
    if await repository.get_location_by_slug(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Location slug exists")
    return await repository.create_location(session, data)


async def update_location(session: AsyncSession, location_id: UUID, data: LocationUpdate) -> Location:
    location = await require_location(session, location_id)
    if data.slug and data.slug != location.slug and await repository.get_location_by_slug(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Location slug exists")
    return await repository.update_location(session, location, data)
