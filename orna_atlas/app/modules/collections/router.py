from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.pagination import PageLimit, PageOffset
from orna_atlas.app.core.security import CurrentUser, get_optional_catalog_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.collections import service
from orna_atlas.app.modules.collections.schemas import CollectionDetailRead, CollectionSummaryRead

router = APIRouter(prefix="/collections", tags=["collections"])


def _set_private_projection_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Authorization, Cookie"


@router.get("", response_model=list[CollectionSummaryRead])
async def list_collections(
    response: Response,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    current_user: CurrentUser | None = Depends(get_optional_catalog_user),
    session: AsyncSession = Depends(get_db_session),
):
    _set_private_projection_headers(response)
    return await service.list_public_collections(
        session, current_user, limit=limit, offset=offset
    )


@router.get("/{slug}", response_model=CollectionDetailRead)
async def get_collection(
    slug: str,
    response: Response,
    current_user: CurrentUser | None = Depends(get_optional_catalog_user),
    session: AsyncSession = Depends(get_db_session),
):
    _set_private_projection_headers(response)
    return await service.require_public_collection_by_slug(session, slug, current_user)
