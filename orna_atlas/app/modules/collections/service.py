from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from orna_atlas.app.modules.sessions.schemas import SessionRead


def summary_from_collection(collection: Collection) -> CollectionSummaryRead:
    public_sessions = [
        link.session for link in collection.session_links if link.session.access_level == "public"
    ]
    return CollectionSummaryRead(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        sort_order=collection.sort_order,
        location_count=len(collection.location_links),
        session_count=len(public_sessions),
    )


def detail_from_collection(collection: Collection) -> CollectionDetailRead:
    summary = summary_from_collection(collection)
    locations = [LocationRead.model_validate(link.location) for link in collection.location_links]
    sessions = [
        SessionRead.model_validate(link.session)
        for link in collection.session_links
        if link.session.access_level == "public"
    ]
    return CollectionDetailRead(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        sort_order=collection.sort_order,
        location_count=summary.location_count,
        session_count=summary.session_count,
        metadata_=collection.metadata_,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
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


async def require_public_collection_by_slug(session: AsyncSession, slug: str) -> CollectionDetailRead:
    collection = await repository.get_collection_by_slug(session, slug)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return detail_from_collection(collection)


async def require_collection(session: AsyncSession, collection_id: UUID) -> Collection:
    collection = await repository.get_collection(session, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


async def create_collection(session: AsyncSession, data: CollectionCreate) -> CollectionAdminRead:
    if await repository.get_collection_by_slug_for_admin(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection slug exists")
    try:
        await repository.validate_location_ids(session, data.location_ids)
        await repository.validate_session_ids(session, data.session_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    collection = await repository.create_collection(session, data)
    return admin_read_from_collection(collection)


async def update_collection(
    session: AsyncSession, collection_id: UUID, data: CollectionUpdate
) -> CollectionAdminRead:
    collection = await require_collection(session, collection_id)
    if (
        data.slug
        and data.slug != collection.slug
        and await repository.get_collection_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection slug exists")
    if data.location_ids is not None or data.session_ids is not None:
        try:
            if data.location_ids is not None:
                await repository.validate_location_ids(session, data.location_ids)
            if data.session_ids is not None:
                await repository.validate_session_ids(session, data.session_ids)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    collection = await repository.update_collection(session, collection, data)
    return admin_read_from_collection(collection)
