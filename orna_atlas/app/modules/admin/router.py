from fastapi import APIRouter, Depends

from orna_atlas.app.core.security import CurrentUser, get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me")
async def read_admin(current_user: CurrentUser = Depends(get_current_admin)) -> dict[str, object]:
    return {"id": current_user.id, "is_admin": current_user.is_admin, "mode": "local"}
