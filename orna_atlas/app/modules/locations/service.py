from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.locations import repository
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate
from orna_atlas.app.integrations.redis import invalidate_atlas_cache


async def list_public_locations(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[Location]:
    return await repository.list_locations(session, limit=limit, offset=offset)


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


async def require_location_for_admin(session: AsyncSession, location_id: UUID) -> Location:
    location = await repository.get_location_for_admin(session, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


async def create_location(session: AsyncSession, data: LocationCreate) -> Location:
    if await repository.get_location_by_slug_for_admin(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Location slug exists")
    location = await repository.create_location(session, data)
    await invalidate_atlas_cache()
    return location


async def update_location(session: AsyncSession, location_id: UUID, data: LocationUpdate) -> Location:
    location = await require_location_for_admin(session, location_id)
    if (
        data.slug
        and data.slug != location.slug
        and await repository.get_location_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Location slug exists")
    location = await repository.update_location(session, location, data)
    await invalidate_atlas_cache()
    return location


async def delete_location(session: AsyncSession, location_id: UUID) -> None:
    location = await require_location_for_admin(session, location_id)
    await repository.delete_location(session, location)
    await invalidate_atlas_cache()
