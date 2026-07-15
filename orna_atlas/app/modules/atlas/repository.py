from dataclasses import dataclass

from sqlalchemy import DateTime, Select, distinct, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.public import publicly_discoverable_clause
from orna_atlas.app.modules.sessions.models import RecordingSession


@dataclass(frozen=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class AtlasClusterRecord:
    id: str
    latitude: float
    longitude: float
    count: int
    habitats: list[str]


def _coordinate_filters(bbox: BoundingBox | None):
    filters = [publicly_discoverable_clause(), Location.public_point.is_not(None)]
    if bbox is None:
        return filters
    if bbox.west <= bbox.east:
        envelope = func.ST_MakeEnvelope(
            bbox.west, bbox.south, bbox.east, bbox.north, 4326
        )
        filters.append(func.ST_Intersects(Location.public_point, envelope))
    else:
        western_envelope = func.ST_MakeEnvelope(
            bbox.west, bbox.south, 180.0, bbox.north, 4326
        )
        eastern_envelope = func.ST_MakeEnvelope(
            -180.0, bbox.south, bbox.east, bbox.north, 4326
        )
        filters.append(
            or_(
                func.ST_Intersects(Location.public_point, western_envelope),
                func.ST_Intersects(Location.public_point, eastern_envelope),
            )
        )
    return filters


def _published_location_query(bbox: BoundingBox | None, habitats: list[str] | None) -> Select[tuple[Location]]:
    query = (
        select(Location)
        .join(RecordingSession)
        .options(selectinload(Location.sessions))
        .where(
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
            *_coordinate_filters(bbox),
        )
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


async def list_dawn_candidate_locations(
    session: AsyncSession,
    *,
    target_longitude: float,
    limit: int,
) -> list[Location]:
    """Load a bounded set nearest the moving sunrise meridian.

    Solar calculations still run in Python because latitude, date, timezone and
    polar conditions matter, but PostGIS first narrows a planet-scale table by
    angular longitude distance.  The EXISTS clause avoids session fan-out.
    """
    has_public_session = (
        select(literal(1))
        .where(
            RecordingSession.location_id == Location.id,
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
        )
        .exists()
    )
    result = await session.execute(
        _dawn_candidate_query(
            has_public_session=has_public_session,
            target_longitude=target_longitude,
            limit=limit,
        )
    )
    return list(result.scalars().unique())


def _longitude_meridian(longitude: float):
    """A constant north/south line suitable for a PostGIS KNN GiST order."""
    return func.ST_MakeLine(
        func.ST_SetSRID(func.ST_MakePoint(longitude, -90.0), 4326),
        func.ST_SetSRID(func.ST_MakePoint(longitude, 90.0), 4326),
    )


def _dawn_candidate_query(*, has_public_session, target_longitude: float, limit: int):
    # Three individually bounded KNN scans preserve circular longitude at the
    # anti-meridian without wrapping ST_X in a non-indexable sort expression.
    nearest_scans = []
    for longitude in (
        target_longitude,
        target_longitude - 360.0,
        target_longitude + 360.0,
    ):
        distance = Location.public_point.op("<->")(_longitude_meridian(longitude))
        nearest_scans.append(
            select(
                Location.id.label("location_id"),
                distance.label("distance"),
            )
            .where(*_coordinate_filters(None), has_public_session)
            .order_by(distance, Location.id)
            .limit(limit)
        )
    candidates = union_all(*nearest_scans).subquery("dawn_knn_candidates")
    nearest = (
        select(
            candidates.c.location_id,
            func.min(candidates.c.distance).label("distance"),
        )
        .group_by(candidates.c.location_id)
        .subquery("dawn_nearest")
    )
    return (
        select(Location)
        .join(nearest, nearest.c.location_id == Location.id)
        .options(selectinload(Location.sessions))
        .order_by(nearest.c.distance, Location.name, Location.id)
        .limit(limit)
    )


async def list_atlas_clusters(
    session: AsyncSession,
    *,
    bbox: BoundingBox | None,
    habitats: list[str] | None,
    zoom: int,
    limit: int,
) -> list[AtlasClusterRecord]:
    """Aggregate public points in PostGIS without materializing every location."""
    public_locations = (
        select(
            Location.id.label("location_id"),
            Location.public_point.label("point"),
            Location.habitat.label("habitat"),
        )
        .join(RecordingSession)
        .where(
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
            *_coordinate_filters(bbox),
        )
        .distinct()
    )
    if habitats:
        public_locations = public_locations.where(Location.habitat.in_(habitats))
    points = public_locations.subquery()

    # Geohash precision grows with viewport zoom while keeping low-zoom result sets bounded.
    precision = max(1, min(8, zoom + 1))
    cluster_key = func.ST_GeoHash(points.c.point, precision)
    centroid = func.ST_Centroid(func.ST_Collect(points.c.point))
    statement = (
        select(
            cluster_key.label("cluster_key"),
            func.ST_Y(centroid).label("latitude"),
            func.ST_X(centroid).label("longitude"),
            func.count().label("point_count"),
            func.array_remove(
                func.array_agg(distinct(points.c.habitat)), None
            ).label("habitats"),
        )
        .group_by(cluster_key)
        .order_by(cluster_key)
        .limit(limit)
    )
    result = await session.execute(statement)
    return [
        AtlasClusterRecord(
            id=f"{zoom}:{row.cluster_key}",
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            count=int(row.point_count),
            habitats=list(row.habitats or []),
        )
        for row in result
    ]


async def search_locations_and_sessions(
    session: AsyncSession, *, query: str, limit: int, offset: int
) -> list[Location | RecordingSession]:
    term = f"%{query}%"
    location_hits = (
        select(Location)
        .join(RecordingSession)
        .where(
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
            publicly_discoverable_clause(),
            or_(Location.name.ilike(term), Location.region.ilike(term), Location.habitat.ilike(term)),
        )
        .with_only_columns(
            literal("location").label("result_type"),
            Location.id.label("result_id"),
            literal(0).label("type_order"),
            func.lower(Location.name).label("title_order"),
            literal(None, DateTime(timezone=True)).label("date_order"),
        )
        .distinct()
    )
    session_hits = (
        select(RecordingSession)
        .join(Location)
        .where(
            RecordingSession.access_level == "public",
            RecordingSession.publication_status == "published",
            publicly_discoverable_clause(),
            or_(RecordingSession.title.ilike(term), RecordingSession.description.ilike(term)),
        )
        .with_only_columns(
            literal("session").label("result_type"),
            RecordingSession.id.label("result_id"),
            literal(1).label("type_order"),
            literal(None).label("title_order"),
            RecordingSession.recorded_at.label("date_order"),
        )
    )
    hits = union_all(location_hits, session_hits).cte("search_hits")
    page = (
        select(hits)
        .order_by(
            hits.c.type_order,
            hits.c.title_order.asc().nulls_last(),
            hits.c.date_order.desc().nulls_last(),
            hits.c.result_id,
        )
        .offset(offset)
        .limit(limit)
        .cte("search_page")
    )
    result = await session.execute(
        select(page.c.result_type, Location, RecordingSession)
        .outerjoin(
            Location,
            (page.c.result_type == "location") & (Location.id == page.c.result_id),
        )
        .outerjoin(
            RecordingSession,
            (page.c.result_type == "session") & (RecordingSession.id == page.c.result_id),
        )
        .options(
            joinedload(Location.sessions),
            joinedload(RecordingSession.location),
        )
        .order_by(
            page.c.type_order,
            page.c.title_order.asc().nulls_last(),
            page.c.date_order.desc().nulls_last(),
            page.c.result_id,
        )
    )
    rows: list[Location | RecordingSession] = []
    for result_type, location, recording in result.unique().all():
        entity = location if result_type == "location" else recording
        if entity is not None:
            rows.append(entity)
    return rows
