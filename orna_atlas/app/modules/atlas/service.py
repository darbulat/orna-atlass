import hashlib
import json
from datetime import UTC, datetime, timedelta
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
    DawnCurrentResponse,
    DawnFollowResponse,
    DawnLocation,
    DawnWindowConfig,
    SearchResult,
)
from orna_atlas.app.integrations.sunrise import dawn_window, get_timezone
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.public import normalized_visibility

TimeMode = Literal["local", "utc", "dawn"]
DawnState = Literal["active", "upcoming", "past", "polar"]
DAWN_BEFORE_MINUTES = 45
DAWN_AFTER_MINUTES = 30
DAWN_CACHE_SECONDS = 60


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
    time_mode: TimeMode,
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


def stable_dawn_cache_key(*, kind: Literal["current", "follow"], now: datetime, limit: int) -> str:
    bucket = int(now.timestamp()) // DAWN_CACHE_SECONDS
    return f"atlas:dawn:{kind}:{bucket}:{limit}"


def point_from_location(location: Location) -> AtlasPoint | None:
    if location.latitude is None or location.longitude is None:
        return None
    public_sessions = sorted(
        (
            session
            for session in location.sessions
            if session.access_level == "public"
            and getattr(session, "publication_status", "published") == "published"
        ),
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
        coordinate_visibility=normalized_visibility(
            getattr(location, "coordinate_visibility", "exact_public")
        ),
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
    time_mode: TimeMode,
    limit: int,
) -> AtlasPointsResponse:
    parsed_bbox = parse_bbox(bbox)
    normalized_habitats = normalize_habitats(habitats)
    mode: Literal["points", "clusters"] = "clusters" if zoom < 5 else "points"
    locations = await repository.list_atlas_locations(
        session,
        bbox=parsed_bbox,
        habitats=normalized_habitats,
        limit=None if mode == "clusters" else limit,
    )
    points = [point for location in locations if (point := point_from_location(location)) is not None]
    payload_points = cluster_points(points, zoom)[:limit] if mode == "clusters" else points
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


def _dawn_location_from_point(
    point: AtlasPoint, *, now: datetime, roll_past_forward: bool = False
) -> DawnLocation:
    window = dawn_window(
        latitude=point.latitude,
        longitude=point.longitude,
        timezone=point.timezone,
        now=now,
        before_minutes=DAWN_BEFORE_MINUTES,
        after_minutes=DAWN_AFTER_MINUTES,
    )
    if roll_past_forward and window.window_ends_at is not None and now > window.window_ends_at:
        window = dawn_window(
            latitude=point.latitude,
            longitude=point.longitude,
            timezone=point.timezone,
            now=now + timedelta(days=1),
            before_minutes=DAWN_BEFORE_MINUTES,
            after_minutes=DAWN_AFTER_MINUTES,
        )
    local_now = now.astimezone(get_timezone(point.timezone))
    state: DawnState
    minutes_until_sunrise: int | None = None
    if window.sunrise_at is None or window.window_starts_at is None or window.window_ends_at is None:
        state = "polar"
    else:
        minutes_until_sunrise = round((window.sunrise_at - now).total_seconds() / 60)
        if window.window_starts_at <= now <= window.window_ends_at:
            state = "active"
        elif now < window.window_starts_at:
            state = "upcoming"
        else:
            state = "past"
    return DawnLocation(
        location=point,
        local_date=window.local_date.isoformat(),
        local_time=local_now.strftime("%H:%M"),
        civil_dawn_at=window.civil_dawn_at,
        sunrise_at=window.sunrise_at,
        sunset_at=getattr(window, "sunset_at", None),
        civil_dusk_at=getattr(window, "civil_dusk_at", None),
        window_starts_at=window.window_starts_at,
        window_ends_at=window.window_ends_at,
        minutes_until_sunrise=minutes_until_sunrise,
        state=state,
        solar_phase=getattr(window, "solar_phase", "night"),
    )


def _sort_dawn_locations(locations: list[DawnLocation]) -> list[DawnLocation]:
    def sort_key(item: DawnLocation) -> tuple[int, float, str]:
        groups = {"active": 0, "upcoming": 1, "past": 2, "polar": 3}
        minutes = item.minutes_until_sunrise
        return (groups[item.state], abs(minutes) if minutes is not None else 10_000, item.location.name)

    return sorted(locations, key=sort_key)


async def get_current_dawn(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 12
) -> DawnCurrentResponse:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    locations = await repository.list_atlas_locations(
        session,
        bbox=None,
        habitats=None,
        limit=None,
    )
    dawn_locations = [
        _dawn_location_from_point(point, now=generated_at)
        for location in locations
        if (point := point_from_location(location)) is not None
    ]
    next_dawn_locations = [
        _dawn_location_from_point(point, now=generated_at, roll_past_forward=True)
        for location in locations
        if (point := point_from_location(location)) is not None
    ]
    return DawnCurrentResponse(
        generated_at=generated_at,
        window=DawnWindowConfig(
            before_minutes=DAWN_BEFORE_MINUTES,
            after_minutes=DAWN_AFTER_MINUTES,
            refresh_seconds=DAWN_CACHE_SECONDS,
        ),
        active_locations=_sort_dawn_locations(
            [item for item in dawn_locations if item.state == "active"]
        )[:limit],
        next_locations=_sort_dawn_locations(
            [item for item in next_dawn_locations if item.state == "upcoming"]
        )[:limit],
        cache_key=stable_dawn_cache_key(kind="current", now=generated_at, limit=limit),
    )


async def get_follow_dawn(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 24
) -> DawnFollowResponse:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    locations = await repository.list_atlas_locations(
        session,
        bbox=None,
        habitats=None,
        limit=None,
    )
    dawn_locations = [
        _dawn_location_from_point(point, now=generated_at, roll_past_forward=True)
        for location in locations
        if (point := point_from_location(location)) is not None
    ]
    return DawnFollowResponse(
        generated_at=generated_at,
        window=DawnWindowConfig(
            before_minutes=DAWN_BEFORE_MINUTES,
            after_minutes=DAWN_AFTER_MINUTES,
            refresh_seconds=DAWN_CACHE_SECONDS,
        ),
        locations=_sort_dawn_locations(dawn_locations)[:limit],
        cache_key=stable_dawn_cache_key(kind="follow", now=generated_at, limit=limit),
    )


async def search(session: AsyncSession, *, query: str, limit: int, offset: int) -> list[SearchResult]:
    if len(query.strip()) < 2:
        return []
    rows = await repository.search_locations_and_sessions(
        session,
        query=query.strip(),
        limit=limit,
        offset=offset,
    )
    results: list[SearchResult] = []
    for row in rows:
        if isinstance(row, Location):
            atlas_point = point_from_location(row)
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
                    atlas_point=atlas_point,
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
