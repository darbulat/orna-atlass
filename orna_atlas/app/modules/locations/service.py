from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.domain_types import CoordinateVisibility
from orna_atlas.app.modules.admin.context import (
    apply_actor_mode_metadata,
    build_admin_etag,
    validate_if_match_or_fail,
)
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_errors import ConflictError, NotFoundError, ValidationError
from orna_atlas.app.integrations.redis import invalidate_atlas_cache
from orna_atlas.app.modules.locations import repository
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import (
    AdminLocationRead,
    LocationCreate,
    LocationRead,
    LocationUpdate,
)
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


async def list_locations_for_admin(
    session: AsyncSession,
    *,
    include_archived: bool = False,
    q: str | None = None,
    coordinate_visibility: str | None = None,
    sensitivity_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AdminLocationRead]:
    filters: dict[str, object] = {
        "include_archived": include_archived,
        "limit": limit,
        "offset": offset,
    }
    if q is not None:
        filters["q"] = q
    if coordinate_visibility is not None:
        filters["coordinate_visibility"] = coordinate_visibility
    if sensitivity_level is not None:
        filters["sensitivity_level"] = sensitivity_level
    locations = await repository.list_locations_for_admin(session, **filters)
    return [AdminLocationRead.model_validate(location) for location in locations]


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


async def require_location_for_admin_for_update(
    session: AsyncSession, location_id: UUID
) -> Location:
    location = await repository.get_location_for_admin_for_update(session, location_id)
    if location is None:
        raise NotFoundError("Location not found")
    return location


async def create_location(
    session: AsyncSession,
    data: LocationCreate,
    *,
    actor_user_id: UUID | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Location:
    if await repository.get_location_by_slug_for_admin(session, data.slug):
        raise ConflictError("Location slug exists")
    location = await repository.create_location(session, data)
    await add_audit_event(
        session,
        event_type="location.created",
        subject_type="location",
        subject_id=str(location.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {
                "changed_fields": list(
                    (
                        data.model_dump(exclude_unset=True, exclude_none=True)
                        if hasattr(data, "model_dump")
                        else vars(data)
                    ).keys()
                )
            },
            actor_mode,
        ),
    )
    await session.commit()
    await session.refresh(location)
    await invalidate_atlas_cache()
    return location


async def update_location(
    session: AsyncSession,
    location_id: UUID,
    data: LocationUpdate,
    *,
    if_match: str | None = None,
    actor_user_id: UUID | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Location:
    location = await require_location_for_admin_for_update(session, location_id)
    if if_match is not None:
        expected_etag = build_admin_etag(
            resource_id=location.id, updated_at=location.updated_at
        )
        validate_if_match_or_fail(if_match=if_match, expected=expected_etag)

    _validate_public_coordinate_update(location, data)
    if (
        data.slug
        and data.slug != location.slug
        and await repository.get_location_by_slug_for_admin(session, data.slug)
    ):
        raise ConflictError("Location slug exists")
    location = await repository.update_location(session, location, data)
    await add_audit_event(
        session,
        event_type="location.updated",
        subject_type="location",
        subject_id=str(location.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {"changed_fields": sorted(data.model_fields_set)},
            actor_mode,
        ),
    )
    await session.commit()
    await session.refresh(location)
    await invalidate_atlas_cache()
    return location


async def delete_location(
    session: AsyncSession,
    location_id: UUID,
    *,
    if_match: str | None = None,
    actor_user_id: UUID | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    location = await require_location_for_admin_for_update(session, location_id)
    if if_match is not None:
        expected_etag = build_admin_etag(
            resource_id=location.id, updated_at=location.updated_at
        )
        validate_if_match_or_fail(if_match=if_match, expected=expected_etag)

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
    await add_audit_event(
        session,
        event_type="location.archived",
        subject_type="location",
        subject_id=str(location.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {"changed_fields": ["archived"], "status": "archived"},
            actor_mode,
        ),
    )
    await session.commit()
    await invalidate_atlas_cache()
