from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.core.pagination import PageLimit, PageOffset
from orna_atlas.app.modules.collections import service
from orna_atlas.app.modules.collections.schemas import CollectionDetailRead, CollectionSummaryRead

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionSummaryRead])
async def list_collections(
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_public_collections(session, limit=limit, offset=offset)


@router.get("/{slug}", response_model=CollectionDetailRead)
async def get_collection(slug: str, session: AsyncSession = Depends(get_db_session)):
    return await service.require_public_collection_by_slug(session, slug)
