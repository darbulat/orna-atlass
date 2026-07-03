from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_admin: bool = False


async def get_current_admin(x_orna_admin: str | None = Header(default=None)) -> CurrentUser:
    """Local admin-mode dependency for Sprint 2.

    Supplying ``X-ORNA-Admin: local`` unlocks write-oriented admin endpoints without introducing
    production authentication before the dedicated auth sprint.
    """
    if x_orna_admin != "local":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local admin mode required")
    return CurrentUser(id="local-admin", is_admin=True)
