from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.atlas import service
from orna_atlas.app.modules.atlas.schemas import AtlasPointsResponse, SearchResult

router = APIRouter(tags=["atlas"])


@router.get("/atlas/points", response_model=AtlasPointsResponse)
async def get_atlas_points(
    bbox: str | None = None,
    zoom: int = Query(default=3, ge=0, le=22),
    habitat: list[str] | None = Query(default=None),
    time_mode: str = "local",
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
    redis = get_redis_client()
    try:
        cached = await redis.get(cache_key)
        if cached:
            return AtlasPointsResponse.model_validate_json(cached)
        response = await service.get_atlas_points(
            session,
            bbox=bbox,
            zoom=zoom,
            habitats=habitat,
            time_mode=time_mode,
            limit=limit,
        )
        await redis.set(cache_key, response.model_dump_json(), ex=60)
        return response
    finally:
        await redis.aclose()


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=10, ge=1, le=25),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.search(session, query=q, limit=limit)
