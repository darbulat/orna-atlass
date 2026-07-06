from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.atlas import service
from orna_atlas.app.modules.atlas.schemas import (
    AtlasPointsResponse,
    DawnCurrentResponse,
    DawnFollowResponse,
    SearchResult,
)

router = APIRouter(tags=["atlas"])

TimeModeQuery = Annotated[service.TimeMode, Query()]


async def _cached_response(cache_key: str, response_model, producer, *, ttl: int):
    redis = get_redis_client()
    try:
        try:
            cached = await redis.get(cache_key)
        except Exception:
            cached = None
        if cached:
            return response_model.model_validate_json(cached)
        response = await producer()
        try:
            await redis.set(cache_key, response.model_dump_json(), ex=ttl)
        except Exception:
            pass
        return response
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


@router.get("/atlas/points", response_model=AtlasPointsResponse)
async def get_atlas_points(
    bbox: str | None = None,
    zoom: int = Query(default=3, ge=0, le=22),
    habitat: list[str] | None = Query(default=None),
    time_mode: TimeModeQuery = "local",
    limit: int = Query(default=250, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
):
    parsed_bbox = service.parse_bbox(bbox)
    normalized_habitats = service.normalize_habitats(habitat)
    cache_key = service.stable_cache_key(
        bbox=parsed_bbox,
        zoom=zoom,
        habitats=normalized_habitats,
        time_mode=time_mode,
        limit=limit,
    )
    return await _cached_response(
        cache_key,
        AtlasPointsResponse,
        lambda: service.get_atlas_points(
            session,
            bbox=bbox,
            zoom=zoom,
            habitats=habitat,
            time_mode=time_mode,
            limit=limit,
        ),
        ttl=60,
    )


@router.get("/atlas/dawn/current", response_model=DawnCurrentResponse)
async def get_current_dawn(
    limit: int = Query(default=12, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    now = datetime.now(UTC)
    cache_key = service.stable_dawn_cache_key(kind="current", now=now, limit=limit)
    return await _cached_response(
        cache_key,
        DawnCurrentResponse,
        lambda: service.get_current_dawn(session, now=now, limit=limit),
        ttl=service.DAWN_CACHE_SECONDS,
    )


@router.get("/atlas/dawn/follow", response_model=DawnFollowResponse)
async def get_follow_dawn(
    limit: int = Query(default=24, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    now = datetime.now(UTC)
    cache_key = service.stable_dawn_cache_key(kind="follow", now=now, limit=limit)
    return await _cached_response(
        cache_key,
        DawnFollowResponse,
        lambda: service.get_follow_dawn(session, now=now, limit=limit),
        ttl=service.DAWN_CACHE_SECONDS,
    )


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.search(session, query=q, limit=limit, offset=offset)
