from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_types import (
    CoordinateVisibility,
    MembershipStatus,
    ProcessingStatus,
    PublicationStatus,
    SensitivityLevel,
    SessionAccess,
    UserRole,
)
from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.modules.admin.context import (
    build_admin_mutation_context,
)
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.admin import service as admin_service
from orna_atlas.app.modules.admin.schemas import (
    AdminCollectionResource,
    AdminIdentityRead,
    AdminLocationRead,
    AdminSessionResource,
    AdminUserResource,
    AuditEventRead,
)
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.billing import service as billing_service
from orna_atlas.app.modules.billing.schemas import (
    AdminBillingOfferCreate,
    AdminBillingOfferRead,
)
from orna_atlas.app.modules.collections.schemas import CollectionCreate, CollectionUpdate
from orna_atlas.app.core.pagination import PageLimit, PageOffset
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import (
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
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionUpdate
from orna_atlas.app.modules.users import service as users_service
from orna_atlas.app.modules.users.schemas import UserRoleUpdate


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
    current_user: CurrentUser = admin_dependency,
    access_cookie: str | None = Cookie(default=None, alias="orna_access"),
) -> None:
    if current_user.auth_mode in {"bearer", "local"} or current_user.id == "local-admin":
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
    q: str | None = Query(default=None, max_length=200),
    coordinate_visibility: CoordinateVisibility | None = Query(default=None),
    sensitivity_level: SensitivityLevel | None = Query(default=None),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminLocationRead]:
    return await locations_service.list_locations_for_admin(
        session,
        include_archived=include_archived,
        q=q.strip()[:200] if q else None,
        coordinate_visibility=coordinate_visibility,
        sensitivity_level=sensitivity_level,
        limit=limit,
        offset=offset,
    )


@router.get("/locations/{location_id}", response_model=AdminLocationRead)
async def get_location(
    location_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminLocationRead:
    location = await locations_service.require_location_for_admin(session, location_id)
    entity = AdminLocationRead.model_validate(location)
    response.headers["ETag"] = entity.revision
    return entity


@router.post(
    "/locations",
    response_model=AdminLocationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_location(
    data: LocationCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await locations_service.create_location(
        session,
        data,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.patch(
    "/locations/{location_id}",
    response_model=AdminLocationRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_location(
    location_id: UUID,
    data: LocationUpdate,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await locations_service.update_location(
        session,
        location_id,
        data,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def delete_location(
    location_id: UUID,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    await locations_service.delete_location(
        session,
        location_id,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[AdminSessionResource])
async def list_sessions(
    *,
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    location_id: UUID | None = Query(default=None),
    publication_status: PublicationStatus | None = Query(default=None),
    processing_status: ProcessingStatus | None = Query(default=None),
    access_level: SessionAccess | None = Query(default=None),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminSessionResource]:
    return await sessions_service.list_sessions_for_admin(
        session,
        include_archived=include_archived,
        q=q.strip()[:200] if q else None,
        location_id=location_id,
        publication_status=publication_status,
        processing_status=processing_status,
        access_level=access_level,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=AdminSessionResource)
async def get_session(
    session_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminSessionResource:
    session_obj = await sessions_service.require_session_for_admin(session, session_id)
    entity = AdminSessionResource.model_validate(session_obj)
    response.headers["ETag"] = entity.revision
    return entity


@router.post(
    "/sessions",
    response_model=AdminSessionResource,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_session(
    data: SessionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await sessions_service.create_session(
        session,
        data,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=AdminSessionResource,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_session(
    session_id: UUID,
    data: SessionUpdate,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await sessions_service.update_session(
        session,
        session_id,
        data,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.post(
    "/sessions/{session_id}/assets",
    response_model=AdminMediaAssetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_session_asset(
    session_id: UUID,
    data: MediaAssetCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await media_service.create_asset_for_session(
        session,
        session_id,
        data,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.post(
    "/sessions/{session_id}/segments",
    response_model=list[RecordingSegmentRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def register_session_segments(
    session_id: UUID,
    data: RecordingSegmentBatchCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    segments, _job = await media_service.register_recording_segments(
        session,
        session_id,
        data,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return segments


@router.post(
    "/sessions/{session_id}/segments/process",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def retry_session_segments(
    session_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    job = await media_service.retry_hls_processing(
        session,
        session_id,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
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
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await media_service.retry_asset_processing(
        session,
        asset_id,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.delete(
    "/media-assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def archive_media_asset(
    asset_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    await media_service.archive_asset(
        session,
        asset_id,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/media-assets/{asset_id}/object",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def purge_archived_media_asset(
    asset_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    await media_service.purge_archived_asset(
        session,
        asset_id,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def delete_session(
    session_id: UUID,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    await sessions_service.delete_session(
        session,
        session_id,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections", response_model=list[AdminCollectionResource])
async def list_collections(
    *,
    q: str | None = Query(default=None, max_length=200),
    is_public: bool | None = Query(default=None),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminCollectionResource]:
    return await collections_service.list_collections_for_admin(
        session,
        q=q.strip()[:200] if q else None,
        is_public=is_public,
        limit=limit,
        offset=offset,
    )


@router.get("/collections/{collection_id}", response_model=AdminCollectionResource)
async def get_collection(
    collection_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminCollectionResource:
    collection = await collections_service.require_collection_for_admin(session, collection_id)
    entity = AdminCollectionResource.model_validate(collection)
    response.headers["ETag"] = entity.revision
    return entity


@router.get("/users", response_model=list[AdminUserResource])
async def list_users(
    email: str | None = Query(default=None, max_length=200),
    role: UserRole | None = None,
    is_active: bool | None = None,
    membership_status: MembershipStatus | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AdminUserResource]:
    email_value = email.strip() if email else None
    role_value = role.value if role else None
    membership = membership_status.value if membership_status else None
    return await users_service.list_admin(
        session,
        email=email_value,
        role=role_value,
        is_active=is_active,
        membership_status=membership,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserResource)
async def get_user(
    user_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminUserResource:
    user = await users_service.require_admin_user(session, user_id)
    entity = AdminUserResource.model_validate(user)
    response.headers["ETag"] = entity.revision
    return entity


@router.post(
    "/collections",
    response_model=AdminCollectionResource,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def create_collection(
    data: CollectionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await collections_service.create_collection(
        session,
        data,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.patch(
    "/collections/{collection_id}",
    response_model=AdminCollectionResource,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
):
    context = build_admin_mutation_context(current_user, request)
    return await collections_service.update_collection(
        session,
        collection_id,
        data,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserResource,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_user_role(
    user_id: UUID,
    data: UserRoleUpdate,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
) -> AdminUserResource:
    if current_user.id is not None and str(current_user.id) == str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins cannot modify their own role")
    context = build_admin_mutation_context(current_user, request)
    user = await users_service.update_role(
        session,
        user_id,
        data,
        actor_user_id=context.actor_user_id,
        if_match=if_match,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return AdminUserResource.model_validate(await users_service.require_admin_user(session, user.id))


@router.put(
    "/memberships/{user_id}",
    response_model=MembershipRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def update_membership(
    user_id: UUID,
    data: MembershipUpdate,
    request: Request,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
) -> MembershipRead:
    context = build_admin_mutation_context(current_user, request)
    await memberships_service.update_membership(
        session,
        user_id,
        data,
        actor_user_id=context.actor_user_id,
        if_match=if_match,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return await memberships_service.entitlement_for_user(session, user_id)


@router.get("/billing/offers/lifetime-member", response_model=AdminBillingOfferRead)
async def get_lifetime_membership_offer(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> AdminBillingOfferRead:
    offer = await billing_service.active_offer_for_admin(session)
    entity = AdminBillingOfferRead.model_validate(offer)
    response.headers["ETag"] = entity.revision
    return entity


@router.put(
    "/billing/offers/lifetime-member",
    response_model=AdminBillingOfferRead,
    dependencies=[Depends(_require_admin_cookie_origin)],
)
async def replace_lifetime_membership_offer(
    data: AdminBillingOfferCreate,
    request: Request,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    session: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = admin_dependency,
) -> AdminBillingOfferRead:
    context = build_admin_mutation_context(current_user, request)
    offer = await billing_service.replace_active_offer(
        session,
        data,
        if_match=if_match,
        actor_user_id=context.actor_user_id,
        actor_mode=context.actor_mode,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    entity = AdminBillingOfferRead.model_validate(offer)
    response.headers["ETag"] = entity.revision
    return entity


@router.get("/audit-events", response_model=list[AuditEventRead])
async def list_audit_events(
    event_type: str | None = None,
    actor_user_id: UUID | None = Query(default=None),
    subject_type: str | None = None,
    subject_id: str | None = None,
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),

    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = admin_dependency,
) -> list[AuditEventRead]:
    events = await admin_service.list_audit_events(
        session,
        event_type=event_type,
        actor_user_id=actor_user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        created_from=created_from,
        created_to=created_to,

        limit=limit,
        offset=offset,
    )
    return [AuditEventRead.model_validate(event) for event in events]
