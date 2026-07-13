from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.memberships import repository
from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.memberships.schemas import (
    MembershipAbsentRead,
    MembershipRead,
    MembershipUpdate,
)
from orna_atlas.app.modules.users.service import require_user


async def entitlement_for_user(
    session: AsyncSession, user_id: UUID
) -> MembershipRead | MembershipAbsentRead:
    membership = await repository.get_for_user(session, user_id)
    if membership is None:
        return MembershipAbsentRead(user_id=user_id)
    return MembershipRead.model_validate(membership)


async def has_playback_entitlement(session: AsyncSession, user_id: UUID) -> bool:
    membership = await repository.get_for_user(session, user_id)
    return membership is not None and membership.is_entitled


async def update_membership(
    session: AsyncSession, user_id: UUID, data: MembershipUpdate, *, actor_user_id: UUID | None
) -> Membership:
    await require_user(session, user_id)
    membership = await repository.upsert(session, user_id, data)
    await add_audit_event(
        session,
        event_type="membership.updated",
        subject_type="membership",
        subject_id=str(membership.id),
        actor_user_id=actor_user_id,
        metadata={"user_id": str(user_id), "status": data.status, "plan": data.plan},
    )
    await session.commit()
    await session.refresh(membership)
    return membership
