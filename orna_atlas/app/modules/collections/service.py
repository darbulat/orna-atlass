from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin.context import (
    apply_actor_mode_metadata,
    build_admin_etag,
    validate_if_match_or_fail,
)
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.core.domain_errors import ConflictError, NotFoundError, ValidationError
from orna_atlas.app.modules.collections import repository
from orna_atlas.app.modules.collections.models import Collection
from orna_atlas.app.modules.collections.schemas import (
    CollectionAdminRead,
    CollectionCreate,
    CollectionDetailRead,
    CollectionSummaryRead,
    CollectionUpdate,
)
from orna_atlas.app.modules.locations.schemas import LocationRead
from orna_atlas.app.modules.locations.public import is_publicly_discoverable
from orna_atlas.app.modules.sessions.schemas import PublicSessionRead


def summary_from_collection(collection: Collection) -> CollectionSummaryRead:
    public_sessions = [
        link.session
        for link in collection.session_links
        if link.session.access_level == "public"
        and getattr(link.session, "publication_status", "published") == "published"
        and is_publicly_discoverable(link.session.location)
    ]
    public_locations = [
        link.location
        for link in collection.location_links
        if is_publicly_discoverable(link.location)
    ]
    return CollectionSummaryRead(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        sort_order=collection.sort_order,
        location_count=len(public_locations),
        session_count=len(public_sessions),
    )


def detail_from_collection(collection: Collection) -> CollectionDetailRead:
    summary = summary_from_collection(collection)
    locations = [
        LocationRead.model_validate(link.location)
        for link in collection.location_links
        if is_publicly_discoverable(link.location)
    ]
    sessions = [
        PublicSessionRead.model_validate(link.session)
        for link in collection.session_links
        if link.session.access_level == "public"
        and getattr(link.session, "publication_status", "published") == "published"
        and is_publicly_discoverable(link.session.location)
    ]
    return CollectionDetailRead(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        sort_order=collection.sort_order,
        location_count=summary.location_count,
        session_count=summary.session_count,
        locations=locations,
        sessions=sessions,
    )


def admin_read_from_collection(collection: Collection) -> CollectionAdminRead:
    return CollectionAdminRead(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        is_public=collection.is_public,
        sort_order=collection.sort_order,
        metadata_=collection.metadata_,
        location_ids=[link.location_id for link in collection.location_links],
        session_ids=[link.session_id for link in collection.session_links],
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


async def list_public_collections(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[CollectionSummaryRead]:
    collections = await repository.list_public_collections(session, limit=limit, offset=offset)
    return [summary_from_collection(item) for item in collections]


async def list_collections_for_admin(
    session: AsyncSession,
    *,
    q: str | None = None,
    is_public: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CollectionAdminRead]:
    filters: dict[str, object] = {"limit": limit, "offset": offset}
    if q is not None:
        filters["q"] = q
    if is_public is not None:
        filters["is_public"] = is_public
    collections = await repository.list_collections_for_admin(session, **filters)
    return [admin_read_from_collection(item) for item in collections]


async def require_collection_for_admin(session: AsyncSession, collection_id: UUID) -> CollectionAdminRead:
    collection = await repository.get_collection(session, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found")
    return admin_read_from_collection(collection)


async def require_public_collection_by_slug(session: AsyncSession, slug: str) -> CollectionDetailRead:
    collection = await repository.get_collection_by_slug(session, slug)
    if collection is None:
        raise NotFoundError("Collection not found")
    return detail_from_collection(collection)


async def require_collection(session: AsyncSession, collection_id: UUID) -> Collection:
    collection = await repository.get_collection(session, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found")
    return collection


async def require_collection_for_update(
    session: AsyncSession, collection_id: UUID
) -> Collection:
    collection = await repository.get_collection_for_update(session, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found")
    return collection


async def create_collection(
    session: AsyncSession,
    data: CollectionCreate,
    *,
    actor_user_id: UUID | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CollectionAdminRead:
    if await repository.get_collection_by_slug_for_admin(session, data.slug):
        raise ConflictError("Collection slug exists")
    try:
        await repository.validate_location_ids(session, data.location_ids)
        await repository.validate_session_ids(session, data.session_ids)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    collection = await repository.create_collection(session, data)
    await add_audit_event(
        session,
        event_type="collection.created",
        subject_type="collection",
        subject_id=str(collection.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {
                "changed_fields": list(data.model_dump(exclude_unset=True).keys())
            },
            actor_mode,
        ),
    )
    await session.commit()
    return admin_read_from_collection(collection)


async def update_collection(
    session: AsyncSession,
    collection_id: UUID,
    data: CollectionUpdate,
    *,
    if_match: str | None = None,
    actor_user_id: UUID | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CollectionAdminRead:
    collection = await require_collection_for_update(session, collection_id)
    if if_match is not None:
        expected_etag = build_admin_etag(
            resource_id=collection.id, updated_at=collection.updated_at
        )
        validate_if_match_or_fail(if_match=if_match, expected=expected_etag)
    if (
        data.slug
        and data.slug != collection.slug
        and await repository.get_collection_by_slug_for_admin(session, data.slug)
    ):
        raise ConflictError("Collection slug exists")
    if data.location_ids is not None or data.session_ids is not None:
        try:
            if data.location_ids is not None:
                await repository.validate_location_ids(session, data.location_ids)
            if data.session_ids is not None:
                await repository.validate_session_ids(session, data.session_ids)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
    collection = await repository.update_collection(session, collection, data)
    await add_audit_event(
        session,
        event_type="collection.updated",
        subject_type="collection",
        subject_id=str(collection.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {"changed_fields": sorted(data.model_fields_set)},
            actor_mode,
        ),
    )
    await session.commit()
    return admin_read_from_collection(collection)


async def delete_collection(session: AsyncSession, collection_id: UUID, *, if_match: str | None = None) -> None:
    collection = await require_collection_for_update(session, collection_id)
    if if_match is not None:
        expected_etag = build_admin_etag(
            resource_id=collection.id, updated_at=collection.updated_at
        )
        validate_if_match_or_fail(if_match=if_match, expected=expected_etag)
    await repository.delete_collection(session, collection)
    await session.commit()
