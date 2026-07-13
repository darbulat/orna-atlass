from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.memberships.schemas import MembershipUpdate


async def get_for_user(session: AsyncSession, user_id: UUID) -> Membership | None:
    result = await session.execute(select(Membership).where(Membership.user_id == user_id))
    return result.scalar_one_or_none()


async def upsert(session: AsyncSession, user_id: UUID, data: MembershipUpdate) -> Membership:
    membership = await get_for_user(session, user_id)
    if membership is None:
        membership = Membership(user_id=user_id)
        session.add(membership)
    membership.status = data.status
    membership.plan = data.plan
    membership.expires_at = data.expires_at
    await session.flush()
    return membership
