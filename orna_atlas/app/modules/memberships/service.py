from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.admin.context import (
    apply_actor_mode_metadata,
    build_admin_user_etag,
    validate_if_match_or_fail,
)
from orna_atlas.app.modules.memberships import repository
from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.memberships.schemas import (
    MembershipAbsentRead,
    MembershipRead,
    MembershipUpdate,
)
from orna_atlas.app.modules.users.service import require_user_for_update


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
    session: AsyncSession,
    user_id: UUID,
    data: MembershipUpdate,
    *,
    actor_user_id: UUID | None,
    if_match: str | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Membership:
    user = await require_user_for_update(session, user_id)
    current = await repository.get_for_user(session, user_id)
    if if_match is not None:
        validate_if_match_or_fail(
            if_match=if_match,
            expected=build_admin_user_etag(
                user_id=user.id,
                user_updated_at=user.updated_at,
                membership_updated_at=(
                    current.updated_at if current is not None else None
                ),
            ),
        )
    membership = await repository.upsert(session, user_id, data)
    await add_audit_event(
        session,
        event_type="membership.updated",
        subject_type="membership",
        subject_id=str(membership.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {
                "user_id": str(user_id),
                "changed_fields": ["status", "plan"],
                "status": data.status,
                "plan": data.plan,
            },
            actor_mode,
        ),
    )
    await session.commit()
    await session.refresh(membership)
    return membership
