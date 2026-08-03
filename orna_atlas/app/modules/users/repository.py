from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.memberships.models import Membership, MembershipEntitlementGrant


async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_id_for_update(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_by_email_for_update(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.email == email.lower())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def acquire_admin_bootstrap_lock(session: AsyncSession) -> None:
    """Serialize first-admin bootstrap attempts for the current transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": 5712684683120764980},
    )


async def get_admin(session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.role == "admin").limit(1))
    return result.scalar_one_or_none()


async def acquire_role_change_lock(session: AsyncSession) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": 5712684683120764981},
        )


async def count_active_admins(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active.is_(True))
    )
    return int(result.scalar_one())


async def create(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str | None,
    email_verified: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=password_hash,
        email_verified_at=datetime.now(UTC) if email_verified else None,
    )
    session.add(user)
    await session.flush()
    return user


async def list_for_admin(
    session: AsyncSession,
    *,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    membership_status: str | None = None,
    limit: int,
    offset: int,
) -> list[User]:
    stmt = (
        select(User)
        .options(selectinload(User.membership))
        .outerjoin(Membership)
        .order_by(User.created_at.desc(), User.id)
        .limit(limit)
        .offset(offset)
    )

    if email:
        lowered = email.strip().lower()
        stmt = stmt.where(User.email.ilike(f"%{lowered}%"))

    if role:
        stmt = stmt.where(User.role == role)

    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    if membership_status:
        normalized = membership_status.lower()
        active_grant = exists(
            select(MembershipEntitlementGrant.id).where(
                MembershipEntitlementGrant.user_id == User.id,
                MembershipEntitlementGrant.status == "active",
                or_(
                    MembershipEntitlementGrant.expires_at.is_(None),
                    MembershipEntitlementGrant.expires_at > datetime.now(UTC),
                ),
            )
        )
        if normalized == "active":
            stmt = stmt.where(active_grant)
        elif normalized == "inactive":
            stmt = stmt.where(
                ~active_grant,
                (Membership.status == "inactive") | (Membership.id.is_(None)),
            )
        else:
            stmt = stmt.where(~active_grant, Membership.status == normalized)

    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def get_for_admin(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(
        select(User)
        .options(selectinload(User.membership))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def save(session: AsyncSession) -> None:
    await session.flush()
