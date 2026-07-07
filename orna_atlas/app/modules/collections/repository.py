from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.collections.models import Collection, CollectionLocation, CollectionSession
from orna_atlas.app.modules.collections.schemas import CollectionCreate, CollectionUpdate
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.sessions.models import RecordingSession


def _payload(data: CollectionCreate | CollectionUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    for key in ("location_ids", "session_ids"):
        payload.pop(key, None)
    if "metadata" in payload:
        payload["metadata_"] = payload.pop("metadata")
    return payload


def _collection_load_options():
    return (
        selectinload(Collection.location_links).selectinload(CollectionLocation.location),
        selectinload(Collection.session_links)
        .selectinload(CollectionSession.session)
        .selectinload(RecordingSession.media_assets),
    )


async def list_public_collections(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[Collection]:
    result = await session.execute(
        select(Collection)
        .options(*_collection_load_options())
        .where(Collection.is_public.is_(True))
        .order_by(Collection.sort_order, Collection.title)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


async def get_collection_by_slug(session: AsyncSession, slug: str, *, public_only: bool = True) -> Collection | None:
    query = select(Collection).options(*_collection_load_options()).where(Collection.slug == slug)
    if public_only:
        query = query.where(Collection.is_public.is_(True))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_collection(session: AsyncSession, collection_id: UUID) -> Collection | None:
    result = await session.execute(
        select(Collection).options(*_collection_load_options()).where(Collection.id == collection_id)
    )
    return result.scalar_one_or_none()


async def get_collection_by_slug_for_admin(session: AsyncSession, slug: str) -> Collection | None:
    result = await session.execute(
        select(Collection).options(*_collection_load_options()).where(Collection.slug == slug)
    )
    return result.scalar_one_or_none()


async def _sync_links(
    session: AsyncSession,
    collection: Collection,
    *,
    location_ids: list[UUID] | None,
    session_ids: list[UUID] | None,
) -> None:
    if location_ids is not None:
        collection.location_links.clear()
        await session.flush()
        for index, location_id in enumerate(location_ids):
            collection.location_links.append(
                CollectionLocation(collection_id=collection.id, location_id=location_id, sort_order=index)
            )
    if session_ids is not None:
        collection.session_links.clear()
        await session.flush()
        for index, session_id in enumerate(session_ids):
            collection.session_links.append(
                CollectionSession(collection_id=collection.id, session_id=session_id, sort_order=index)
            )


async def create_collection(session: AsyncSession, data: CollectionCreate) -> Collection:
    collection = Collection(**_payload(data))
    session.add(collection)
    await session.flush()
    await _sync_links(session, collection, location_ids=data.location_ids, session_ids=data.session_ids)
    await session.commit()
    await session.refresh(collection)
    return await get_collection(session, collection.id) or collection


async def update_collection(session: AsyncSession, collection: Collection, data: CollectionUpdate) -> Collection:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(collection, key, value)
    await _sync_links(
        session,
        collection,
        location_ids=data.location_ids,
        session_ids=data.session_ids,
    )
    await session.commit()
    return await get_collection(session, collection.id) or collection


async def delete_collection(session: AsyncSession, collection: Collection) -> None:
    await session.delete(collection)
    await session.commit()


async def validate_location_ids(session: AsyncSession, location_ids: list[UUID]) -> None:
    if not location_ids:
        return
    result = await session.execute(select(Location.id).where(Location.id.in_(location_ids)))
    found = set(result.scalars())
    missing = [str(item) for item in location_ids if item not in found]
    if missing:
        raise ValueError(f"Unknown location ids: {', '.join(missing)}")


async def validate_session_ids(session: AsyncSession, session_ids: list[UUID]) -> None:
    if not session_ids:
        return
    result = await session.execute(select(RecordingSession.id).where(RecordingSession.id.in_(session_ids)))
    found = set(result.scalars())
    missing = [str(item) for item in session_ids if item not in found]
    if missing:
        raise ValueError(f"Unknown session ids: {', '.join(missing)}")
