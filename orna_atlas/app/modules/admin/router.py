from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.admin import repository as admin_repository
from orna_atlas.app.modules.admin.schemas import AuditEventRead
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.collections.schemas import CollectionAdminRead, CollectionCreate, CollectionUpdate
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationRead, LocationUpdate
from orna_atlas.app.modules.memberships import service as memberships_service
from orna_atlas.app.modules.memberships.schemas import MembershipRead, MembershipUpdate
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media.schemas import (
    AdminMediaAssetRead,
    MediaAssetCreate,
    ProcessingStatusRead,
)
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionRead, SessionUpdate
from orna_atlas.app.modules.users import service as users_service
from orna_atlas.app.modules.users.schemas import UserRead, UserRoleUpdate

router = APIRouter(prefix="/admin", tags=["admin"])
admin_dependency = Depends(get_current_admin)


@router.get("/me")
async def read_admin(current_user: CurrentUser = admin_dependency) -> dict[str, object]:
    mode = "local" if current_user.id == "local-admin" else "token"
    return {"id": current_user.id, "is_admin": current_user.is_admin, "mode": mode}


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    data: LocationCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.create_location(session, data)


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: UUID,
    data: LocationUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.update_location(session, location_id, data)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await locations_service.delete_location(session, location_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await sessions_service.create_session(session, data)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: UUID,
    data: SessionUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await sessions_service.update_session(session, session_id, data)


@router.post(
    "/sessions/{session_id}/assets",
    response_model=AdminMediaAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_asset(
    session_id: UUID,
    data: MediaAssetCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.create_asset_for_session(session, session_id, data)


@router.get("/sessions/{session_id}/processing", response_model=ProcessingStatusRead)
async def read_session_processing(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.processing_status_for_session(session, session_id)


@router.post("/media-assets/{asset_id}/process", response_model=ProcessingStatusRead)
async def retry_asset_processing(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.retry_asset_processing(session, asset_id)


@router.delete("/media-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_media_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await media_service.archive_asset(session, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/media-assets/{asset_id}/object", status_code=status.HTTP_204_NO_CONTENT)
async def purge_archived_media_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await media_service.purge_archived_asset(session, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await sessions_service.delete_session(session, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections", response_model=CollectionAdminRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await collections_service.create_collection(session, data)


@router.patch("/collections/{collection_id}", response_model=CollectionAdminRead)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await collections_service.update_collection(session, collection_id, data)


@router.patch("/users/{user_id}/role", response_model=UserRead)
async def update_user_role(
    user_id: UUID,
    data: UserRoleUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
) -> UserRead:
    actor_id = UUID(current_user.id) if current_user.id != "local-admin" else None
    return UserRead.model_validate(
        await users_service.update_role(session, user_id, data, actor_user_id=actor_id)
    )


@router.put("/memberships/{user_id}", response_model=MembershipRead)
async def update_membership(
    user_id: UUID,
    data: MembershipUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
) -> MembershipRead:
    actor_id = UUID(current_user.id) if current_user.id != "local-admin" else None
    return MembershipRead.model_validate(
        await memberships_service.update_membership(
            session, user_id, data, actor_user_id=actor_id
        )
    )


@router.get("/audit-events", response_model=list[AuditEventRead])
async def list_audit_events(
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AuditEventRead]:
    events = await admin_repository.list_audit_events(
        session, event_type=event_type, limit=limit, offset=offset
    )
    return [AuditEventRead.model_validate(event) for event in events]
