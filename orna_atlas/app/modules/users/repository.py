from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.users.models import User


async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
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


async def save(session: AsyncSession) -> None:
    await session.flush()
