from typing import Literal, cast
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
    is_entitled = await repository.has_active_grant(session, user_id)
    if membership is None:
        return MembershipAbsentRead(user_id=user_id)
    return MembershipRead(
        id=membership.id,
        user_id=membership.user_id,
        status=(
            "active"
            if is_entitled
            else cast(
                Literal["inactive", "active", "cancelled", "expired"],
                membership.status,
            )
        ),
        plan=membership.plan,
        starts_at=membership.starts_at,
        expires_at=membership.expires_at,
        is_entitled=is_entitled,
    )


async def has_playback_entitlement(session: AsyncSession, user_id: UUID) -> bool:
    return await repository.has_active_grant(session, user_id)


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
    if data.status == "active":
        source_type = await repository.membership_grant_source_type(
            session, membership.id
        )
        await repository.upsert_grant(
            session,
            user_id,
            source_type=source_type,
            source_id=membership.id,
            plan=data.plan,
            expires_at=data.expires_at,
        )
    else:
        for source_type in ("legacy", "admin"):
            await repository.revoke_grant(
                session, source_type=source_type, source_id=membership.id
            )
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
                "changed_fields": sorted(data.model_fields_set),
                "status": data.status,
                "plan": data.plan,
            },
            actor_mode,
        ),
    )
    await session.commit()
    await session.refresh(membership)
    return membership
