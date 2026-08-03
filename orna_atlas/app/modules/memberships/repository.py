from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.memberships.models import Membership, MembershipEntitlementGrant
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


async def upsert_grant(
    session: AsyncSession,
    user_id: UUID,
    *,
    source_type: str,
    source_id: UUID,
    plan: str,
    expires_at: datetime | None,
) -> MembershipEntitlementGrant:
    grant = await session.scalar(
        select(MembershipEntitlementGrant).where(
            MembershipEntitlementGrant.source_type == source_type,
            MembershipEntitlementGrant.source_id == source_id,
        )
    )
    if grant is None:
        grant = MembershipEntitlementGrant(
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            plan=plan,
        )
        session.add(grant)
    grant.status = "active"
    grant.expires_at = expires_at
    grant.revoked_at = None
    await session.flush()
    return grant


async def membership_grant_source_type(
    session: AsyncSession, membership_id: UUID
) -> str:
    legacy_source = await session.scalar(
        select(MembershipEntitlementGrant.source_type).where(
            MembershipEntitlementGrant.source_type == "legacy",
            MembershipEntitlementGrant.source_id == membership_id,
        )
    )
    return "legacy" if legacy_source is not None else "admin"


async def revoke_grant(
    session: AsyncSession, *, source_type: str, source_id: UUID
) -> bool:
    grant = await session.scalar(
        select(MembershipEntitlementGrant)
        .where(
            MembershipEntitlementGrant.source_type == source_type,
            MembershipEntitlementGrant.source_id == source_id,
        )
        .with_for_update()
    )
    if grant is None:
        return False
    grant.status = "revoked"
    grant.revoked_at = datetime.now(UTC)
    await session.flush()
    return True


async def has_active_grant(session: AsyncSession, user_id: UUID) -> bool:
    grant_id = await session.scalar(
        select(MembershipEntitlementGrant.id)
        .where(
            MembershipEntitlementGrant.user_id == user_id,
            MembershipEntitlementGrant.status == "active",
            or_(
                MembershipEntitlementGrant.expires_at.is_(None),
                MembershipEntitlementGrant.expires_at > datetime.now(UTC),
            ),
        )
        .limit(1)
    )
    return grant_id is not None
