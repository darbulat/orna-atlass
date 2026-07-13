from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.security import CurrentUser, get_current_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.users.schemas import UserRead
from orna_atlas.app.modules.users.service import require_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserRead:
    return UserRead.model_validate(await require_user(session, UUID(current_user.id)))
