from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, Security, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.security import CurrentUser, get_current_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.library import service
from orna_atlas.app.modules.library.schemas import FavoriteRead, ListeningHistoryRead, ListeningProgressUpdate

router = APIRouter(
    prefix="/users/me",
    tags=["library"],
    responses={401: {"description": "Authentication required"}},
)
bearer_scheme = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="orna_access", auto_error=False)


async def get_library_user(
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    _access_cookie: Annotated[str | None, Security(cookie_scheme)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return current_user


CurrentAccount = Annotated[CurrentUser, Depends(get_library_user)]
Database = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/favorites", response_model=list[FavoriteRead])
async def read_favorites(current_user: CurrentAccount, db: Database, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[FavoriteRead]:
    return await service.list_favorites(db, UUID(current_user.id), role=current_user.role, limit=limit, offset=offset)


@router.put("/favorites/{session_id}", response_model=FavoriteRead)
async def put_favorite(session_id: UUID, current_user: CurrentAccount, db: Database) -> FavoriteRead:
    return await service.add_favorite(db, UUID(current_user.id), session_id, role=current_user.role)


@router.delete("/favorites/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(session_id: UUID, current_user: CurrentAccount, db: Database) -> Response:
    await service.remove_favorite(db, UUID(current_user.id), session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/listening-history", response_model=list[ListeningHistoryRead])
async def read_listening_history(current_user: CurrentAccount, db: Database, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[ListeningHistoryRead]:
    return await service.list_listening_history(db, UUID(current_user.id), role=current_user.role, limit=limit, offset=offset)


@router.put("/listening-history/{session_id}", response_model=ListeningHistoryRead)
async def put_listening_progress(
    session_id: UUID,
    update: ListeningProgressUpdate,
    request: Request,
    current_user: CurrentAccount,
    db: Database,
) -> ListeningHistoryRead:
    received_at = getattr(request.state, "received_at", None) or datetime.now(UTC)
    return await service.update_listening_progress(
        db,
        UUID(current_user.id),
        session_id,
        update,
        role=current_user.role,
        occurred_at=received_at,
    )


@router.delete("/listening-history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listening_history_item(session_id: UUID, current_user: CurrentAccount, db: Database) -> Response:
    await service.remove_listening_history_item(db, UUID(current_user.id), session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/listening-history", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listening_history(current_user: CurrentAccount, db: Database) -> Response:
    await service.clear_listening_history(db, UUID(current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
