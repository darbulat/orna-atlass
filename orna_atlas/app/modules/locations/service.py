from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.domain_types import CoordinateVisibility
from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_errors import ConflictError, NotFoundError, ValidationError
from orna_atlas.app.integrations.redis import invalidate_atlas_cache
from orna_atlas.app.modules.locations import repository
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationRead, LocationUpdate
from orna_atlas.app.modules.media import repository as media_repository
from orna_atlas.app.modules.sessions import repository as sessions_repository


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
        raise ValidationError("Public latitude and longitude must be supplied together")
    if visibility == CoordinateVisibility.APPROXIMATE_PUBLIC and latitude is None:
        raise ValidationError("Approximate public visibility requires public coordinates")


async def list_public_locations(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[LocationRead]:
    locations = await repository.list_locations(session, limit=limit, offset=offset)
    return [LocationRead.model_validate(location) for location in locations]


async def require_location(session: AsyncSession, location_id: UUID) -> LocationRead:
    location = await repository.get_location(session, location_id)
    if location is None:
        raise NotFoundError("Location not found")
    return LocationRead.model_validate(location)


async def require_location_by_slug(session: AsyncSession, slug: str) -> LocationRead:
    location = await repository.get_location_by_slug(session, slug)
    if location is None:
        raise NotFoundError("Location not found")
    return LocationRead.model_validate(location)


async def require_location_for_admin(session: AsyncSession, location_id: UUID) -> Location:
    location = await repository.get_location_for_admin(session, location_id)
    if location is None:
        raise NotFoundError("Location not found")
    return location


async def create_location(session: AsyncSession, data: LocationCreate) -> Location:
    if await repository.get_location_by_slug_for_admin(session, data.slug):
        raise ConflictError("Location slug exists")
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
        raise ConflictError("Location slug exists")
    location = await repository.update_location(session, location, data)
    await session.commit()
    await session.refresh(location)
    await invalidate_atlas_cache()
    return location


async def delete_location(session: AsyncSession, location_id: UUID) -> None:
    location = await require_location_for_admin(session, location_id)
    recordings = list(location.sessions)
    assets = [asset for recording in recordings for asset in recording.media_assets]
    await repository.archive_location(session, location)
    for recording in recordings:
        await sessions_repository.archive_session(session, recording)
    await media_repository.archive_assets(session, assets)
    retain_until = datetime.now(UTC) + timedelta(days=get_settings().media_retention_days)
    await media_repository.schedule_storage_cleanup(
        session,
        assets,
        retain_until=retain_until,
    )
    await session.commit()
    await invalidate_atlas_cache()
