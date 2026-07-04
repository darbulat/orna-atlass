from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate


def _payload(data: LocationCreate | LocationUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    if "metadata" in payload:
        payload["metadata_"] = payload.pop("metadata")
    return payload


async def list_locations(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[Location]:
    result = await session.execute(select(Location).order_by(Location.name).limit(limit).offset(offset))
    return list(result.scalars())


async def get_location(session: AsyncSession, location_id: UUID) -> Location | None:
    return await session.get(Location, location_id)


async def get_location_by_slug(session: AsyncSession, slug: str) -> Location | None:
    result = await session.execute(select(Location).where(Location.slug == slug))
    return result.scalar_one_or_none()


async def create_location(session: AsyncSession, data: LocationCreate) -> Location:
    location = Location(**_payload(data))
    session.add(location)
    await session.commit()
    await session.refresh(location)
    return location


async def update_location(session: AsyncSession, location: Location, data: LocationUpdate) -> Location:
    for key, value in _payload(data, exclude_unset=True).items():
        setattr(location, key, value)
    await session.commit()
    await session.refresh(location)
    return location


async def delete_location(session: AsyncSession, location: Location) -> None:
    await session.delete(location)
    await session.commit()
