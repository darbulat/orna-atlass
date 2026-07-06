import hashlib
import json
from math import floor
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.atlas import repository
from orna_atlas.app.modules.atlas.repository import BoundingBox
from orna_atlas.app.modules.atlas.schemas import (
    AtlasCluster,
    AtlasPoint,
    AtlasPointsResponse,
    AtlasSessionSummary,
    SearchResult,
)
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.sessions.models import RecordingSession


def parse_bbox(value: str | None) -> BoundingBox | None:
    if not value:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox must be west,south,east,north",
        )
    try:
        west, south, east, north = (round(float(part), 6) for part in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox contains non-numeric values",
        ) from exc
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox is outside valid coordinate ranges",
        )
    if south > north:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox south cannot be north of bbox north",
        )
    return BoundingBox(west=west, south=south, east=east, north=north)


def normalize_habitats(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    habitats = sorted({value.strip().lower() for value in values if value.strip()})
    return habitats or None


def stable_cache_key(
    *,
    bbox: BoundingBox | None,
    zoom: int,
    habitats: list[str] | None,
    time_mode: str,
    limit: int,
) -> str:
    payload = {
        "bbox": None if bbox is None else [bbox.west, bbox.south, bbox.east, bbox.north],
        "habitats": habitats or [],
        "limit": limit,
        "time_mode": time_mode,
        "zoom": zoom,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]
    return f"atlas:points:{digest}"


def point_from_location(location: Location) -> AtlasPoint | None:
    if location.latitude is None or location.longitude is None:
        return None
    public_sessions = sorted(
        (session for session in location.sessions if session.access_level == "public"),
        key=lambda item: item.recorded_at,
        reverse=True,
    )
    latest = public_sessions[0] if public_sessions else None
    return AtlasPoint(
        id=location.id,
        slug=location.slug,
        name=location.name,
        description=location.description,
        country_code=location.country_code,
        region=location.region,
        habitat=location.habitat,
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
        sensitivity_level=location.sensitivity_level,
        session_count=len(public_sessions),
        latest_session=None
        if latest is None
        else AtlasSessionSummary(
            id=latest.id,
            slug=latest.slug,
            title=latest.title,
            recorded_at=latest.recorded_at,
            duration_seconds=latest.duration_seconds,
        ),
    )


def _cluster_id(latitude: float, longitude: float, zoom: int) -> str:
    scale = max(1, 7 - zoom)
    return f"{floor(latitude / scale) * scale}:{floor(longitude / scale) * scale}"


def cluster_points(points: list[AtlasPoint], zoom: int) -> list[AtlasCluster]:
    groups: dict[str, list[AtlasPoint]] = {}
    for point in points:
        groups.setdefault(_cluster_id(point.latitude, point.longitude, zoom), []).append(point)
    clusters: list[AtlasCluster] = []
    for key, items in groups.items():
        latitude = sum(item.latitude for item in items) / len(items)
        longitude = sum(item.longitude for item in items) / len(items)
        habitats = sorted({item.habitat for item in items if item.habitat})
        clusters.append(
            AtlasCluster(
                id=key,
                latitude=latitude,
                longitude=longitude,
                count=len(items),
                habitats=habitats,
            )
        )
    return clusters


async def get_atlas_points(
    session: AsyncSession,
    *,
    bbox: str | None,
    zoom: int,
    habitats: list[str] | None,
    time_mode: str,
    limit: int,
) -> AtlasPointsResponse:
    parsed_bbox = parse_bbox(bbox)
    normalized_habitats = normalize_habitats(habitats)
    locations = await repository.list_atlas_locations(
        session,
        bbox=parsed_bbox,
        habitats=normalized_habitats,
        limit=limit,
    )
    points = [point for location in locations if (point := point_from_location(location)) is not None]
    mode: Literal["points", "clusters"] = "clusters" if zoom < 5 else "points"
    payload_points = cluster_points(points, zoom) if mode == "clusters" else points
    return AtlasPointsResponse(
        bbox=None
        if parsed_bbox is None
        else (parsed_bbox.west, parsed_bbox.south, parsed_bbox.east, parsed_bbox.north),
        zoom=zoom,
        mode=mode,
        points=payload_points,
        cache_key=stable_cache_key(
            bbox=parsed_bbox,
            zoom=zoom,
            habitats=normalized_habitats,
            time_mode=time_mode,
            limit=limit,
        ),
    )


async def search(session: AsyncSession, *, query: str, limit: int) -> list[SearchResult]:
    if len(query.strip()) < 2:
        return []
    rows = await repository.search_locations_and_sessions(session, query=query.strip(), limit=limit)
    results: list[SearchResult] = []
    for row in rows:
        if isinstance(row, Location):
            results.append(
                SearchResult(
                    type="location",
                    id=row.id,
                    slug=row.slug,
                    title=row.name,
                    subtitle=row.region or row.country_code,
                    habitat=row.habitat,
                    latitude=row.latitude,
                    longitude=row.longitude,
                )
            )
        else:
            results.append(
                SearchResult(
                    type="session",
                    id=row.id,
                    slug=row.location.slug,
                    title=row.title,
                    subtitle=row.location.name,
                    habitat=row.location.habitat,
                    latitude=row.location.latitude,
                    longitude=row.location.longitude,
                    session_slug=row.slug,
                )
            )
    return results
