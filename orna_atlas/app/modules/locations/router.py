from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.pagination import PageLimit, PageOffset
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.locations import service
from orna_atlas.app.modules.locations.schemas import LocationRead

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
async def list_locations(
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_public_locations(session, limit=limit, offset=offset)


@router.get("/{locator}", response_model=LocationRead)
async def get_location(locator: str, session: AsyncSession = Depends(get_db_session)):
    try:
        location_id = UUID(locator)
    except ValueError:
        return await service.require_location_by_slug(session, locator)
    return await service.require_location(session, location_id)
