from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.domain_types import CoordinateVisibility
from orna_atlas.app.integrations.redis import invalidate_atlas_cache
from orna_atlas.app.modules.locations import repository
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate


def _validate_public_coordinate_update(location: Location, data: LocationUpdate) -> None:
    latitude = (
        data.public_latitude
        if "public_latitude" in data.model_fields_set
        else location.public_latitude
    )
    longitude = (
        data.public_longitude
        if "public_longitude" in data.model_fields_set
        else location.public_longitude
    )
    visibility = data.coordinate_visibility or location.coordinate_visibility

    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Public latitude and longitude must be supplied together",
        )
    if visibility == CoordinateVisibility.APPROXIMATE_PUBLIC and latitude is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Approximate public visibility requires public coordinates",
        )


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
    await session.commit()
    await session.refresh(location)
    await invalidate_atlas_cache()
    return location


async def update_location(session: AsyncSession, location_id: UUID, data: LocationUpdate) -> Location:
    location = await require_location_for_admin(session, location_id)
    _validate_public_coordinate_update(location, data)
    if (
        data.slug
        and data.slug != location.slug
        and await repository.get_location_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Location slug exists")
    location = await repository.update_location(session, location, data)
    await session.commit()
    await session.refresh(location)
    await invalidate_atlas_cache()
    return location


async def delete_location(session: AsyncSession, location_id: UUID) -> None:
    location = await require_location_for_admin(session, location_id)
    await repository.delete_location(session, location)
    await session.commit()
    await invalidate_atlas_cache()
