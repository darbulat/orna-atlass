from dataclasses import dataclass

from sqlalchemy import Select, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.sessions.models import RecordingSession


@dataclass(frozen=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


def _coordinate_filters(bbox: BoundingBox | None):
    filters = [Location.coordinate_visibility != "hidden_public"]
    if bbox is None:
        return filters

    public_latitude = case(
        (Location.coordinate_visibility == "exact_public", Location.exact_latitude),
        else_=Location.public_latitude,
    )
    public_longitude = case(
        (Location.coordinate_visibility == "exact_public", Location.exact_longitude),
        else_=Location.public_longitude,
    )
    filters.append(public_latitude.between(bbox.south, bbox.north))
    if bbox.west <= bbox.east:
        filters.append(public_longitude.between(bbox.west, bbox.east))
    else:
        filters.append(
            or_(
                public_longitude >= bbox.west,
                public_longitude <= bbox.east,
            )
        )
    return filters


def _published_location_query(bbox: BoundingBox | None, habitats: list[str] | None) -> Select[tuple[Location]]:
    query = (
        select(Location)
        .join(RecordingSession)
        .options(selectinload(Location.sessions))
        .where(RecordingSession.access_level == "public", *_coordinate_filters(bbox))
        .order_by(Location.name)
        .distinct()
    )
    if habitats:
        query = query.where(Location.habitat.in_(habitats))
    return query


async def list_atlas_locations(
    session: AsyncSession,
    *,
    bbox: BoundingBox | None,
    habitats: list[str] | None,
    limit: int | None,
) -> list[Location]:
    query = _published_location_query(bbox, habitats)
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().unique())


async def search_locations_and_sessions(
    session: AsyncSession, *, query: str, limit: int, offset: int
) -> list[Location | RecordingSession]:
    term = f"%{query}%"
    location_result = await session.execute(
        select(Location)
        .join(RecordingSession)
        .options(selectinload(Location.sessions))
        .where(
            RecordingSession.access_level == "public",
            Location.coordinate_visibility != "hidden_public",
            or_(Location.name.ilike(term), Location.region.ilike(term), Location.habitat.ilike(term)),
        )
        .order_by(Location.name)
        .distinct()
        .offset(offset)
        .limit(limit)
    )
    session_result = await session.execute(
        select(RecordingSession)
        .join(Location)
        .options(selectinload(RecordingSession.location))
        .where(
            RecordingSession.access_level == "public",
            Location.coordinate_visibility != "hidden_public",
            or_(RecordingSession.title.ilike(term), RecordingSession.description.ilike(term)),
        )
        .order_by(RecordingSession.recorded_at.desc())
        .offset(offset)
        .limit(limit)
    )
    combined: list[Location | RecordingSession] = []
    combined.extend(location_result.scalars().unique())
    combined.extend(session_result.scalars().unique())
    return combined[:limit]
