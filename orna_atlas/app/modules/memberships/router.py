from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.security import CurrentUser, get_current_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.memberships import service
from orna_atlas.app.modules.memberships.schemas import MembershipRead

router = APIRouter(prefix="/memberships", tags=["memberships"])


@router.get("/me", response_model=MembershipRead)
async def read_my_membership(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MembershipRead:
    return await service.entitlement_for_user(session, UUID(current_user.id))
