from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.admin import service as admin_service
from orna_atlas.app.modules.admin.schemas import AdminIdentityRead, AuditEventRead
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.collections.schemas import CollectionAdminRead, CollectionCreate, CollectionUpdate
from orna_atlas.app.core.pagination import PageLimit, PageOffset
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import (
    AdminLocationRead,
    LocationCreate,
    LocationUpdate,
)
from orna_atlas.app.modules.memberships import service as memberships_service
from orna_atlas.app.modules.memberships.schemas import MembershipRead, MembershipUpdate
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media.schemas import (
    AdminMediaAssetRead,
    MediaAssetCreate,
    ProcessingStatusRead,
    RecordingSegmentBatchCreate,
    RecordingSegmentRead,
)
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionRead, SessionUpdate
from orna_atlas.app.modules.users import service as users_service
from orna_atlas.app.modules.users.schemas import AdminUserRead, UserRead, UserRoleUpdate


def _set_admin_no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(_set_admin_no_cache)],
)
admin_dependency = Depends(get_current_admin)


async def _require_admin_cookie_origin(
    request: Request,
    authorization: str | None = Header(default=None),
    _: CurrentUser = admin_dependency,
    access_cookie: str | None = Cookie(default=None, alias="orna_access"),
    x_orna_admin: str | None = Header(default=None),
) -> None:
    if x_orna_admin == "local" or (authorization or "").lower().startswith("bearer "):
        return
    if access_cookie is None:
        return
    if request.headers.get("origin") is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
    if request.headers["origin"] not in get_settings().cors_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")


@router.get("/me", response_model=AdminIdentityRead)
async def read_admin(current_user: CurrentUser = admin_dependency) -> AdminIdentityRead:
    mode = "local" if current_user.id == "local-admin" else "token"
    return AdminIdentityRead(
        id=current_user.id,
        is_admin=current_user.is_admin,
        role="admin",
        mode=mode,
    )


@router.get("/locations", response_model=list[AdminLocationRead])
async def list_locations(
    *,
    include_archived: bool = Query(default=False),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminLocationRead]:
    return await locations_service.list_locations_for_admin(
        session, include_archived=include_archived, limit=limit, offset=offset
    )


@router.get("/locations/{location_id}", response_model=AdminLocationRead)
async def get_location(
    location_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminLocationRead:
    location = await locations_service.require_location_for_admin(session, location_id)
    return AdminLocationRead.model_validate(location)


@router.post(
    "/locations",
    response_model=AdminLocationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_location(
    data: LocationCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.create_location(session, data)


@router.patch(
    "/locations/{location_id}",
    response_model=AdminLocationRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_location(
    location_id: UUID,
    data: LocationUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await locations_service.update_location(session, location_id, data)


@router.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def delete_location(
    location_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await locations_service.delete_location(session, location_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    *,
    include_archived: bool = Query(default=False),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[SessionRead]:
    return await sessions_service.list_sessions_for_admin(
        session, include_archived=include_archived, limit=limit, offset=offset
    )


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> SessionRead:
    return SessionRead.model_validate(
        await sessions_service.require_session_for_admin(session, session_id)
    )


@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_session(
    data: SessionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await sessions_service.create_session(session, data)


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
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
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_session_asset(
    session_id: UUID,
    data: MediaAssetCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.create_asset_for_session(session, session_id, data)


@router.post(
    "/sessions/{session_id}/segments",
    response_model=list[RecordingSegmentRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def register_session_segments(
    session_id: UUID,
    data: RecordingSegmentBatchCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    segments, _job = await media_service.register_recording_segments(session, session_id, data)
    return segments


@router.post(
    "/sessions/{session_id}/segments/process",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def retry_session_segments(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    job = await media_service.retry_hls_processing(session, session_id)
    return {"job_id": str(job.id), "status": job.status}


@router.get("/sessions/{session_id}/processing", response_model=ProcessingStatusRead)
async def read_session_processing(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.processing_status_for_session(session, session_id)


@router.post(
    "/media-assets/{asset_id}/process",
    response_model=ProcessingStatusRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def retry_asset_processing(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await media_service.retry_asset_processing(session, asset_id)


@router.delete(
    "/media-assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def archive_media_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await media_service.archive_asset(session, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/media-assets/{asset_id}/object",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def purge_archived_media_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await media_service.purge_archived_asset(session, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def delete_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    await sessions_service.delete_session(session, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections", response_model=list[CollectionAdminRead])
async def list_collections(
    *,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[CollectionAdminRead]:
    return await collections_service.list_collections_for_admin(
        session, limit=limit, offset=offset
    )


@router.get("/collections/{collection_id}", response_model=CollectionAdminRead)
async def get_collection(
    collection_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> CollectionAdminRead:
    return await collections_service.require_collection_for_admin(session, collection_id)


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    membership_status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminUserRead]:
    return await users_service.list_admin(
        session,
        email=email,
        role=role,
        is_active=is_active,
        membership_status=membership_status,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminUserRead:
    return await users_service.require_admin_user(session, user_id)


@router.post(
    "/collections",
    response_model=CollectionAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_collection(
    data: CollectionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await collections_service.create_collection(session, data)


@router.patch(
    "/collections/{collection_id}",
    response_model=CollectionAdminRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
):
    return await collections_service.update_collection(session, collection_id, data)


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
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


@router.put(
    "/memberships/{user_id}",
    response_model=MembershipRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
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
    events = await admin_service.list_audit_events(
        session, event_type=event_type, limit=limit, offset=offset
    )
    return [AuditEventRead.model_validate(event) for event in events]
