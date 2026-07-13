from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.users import repository
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRoleUpdate


async def require_user(session: AsyncSession, user_id: UUID) -> User:
    user = await repository.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")
    return user


async def update_role(
    session: AsyncSession, user_id: UUID, data: UserRoleUpdate, *, actor_user_id: UUID | None
) -> User:
    user = await require_user(session, user_id)
    previous = user.role
    user.role = data.role
    await repository.save(session)
    await add_audit_event(
        session,
        event_type="user.role_updated",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=actor_user_id,
        metadata={"previous_role": previous, "role": data.role},
    )
    await session.commit()
    await session.refresh(user)
    return user


async def bootstrap_first_admin(session: AsyncSession, email: str) -> User:
    """Promote one existing active user when the deployment has no administrator."""
    await repository.acquire_admin_bootstrap_lock(session)
    if await repository.get_admin(session) is not None:
        raise ValueError("An admin user already exists; use the authenticated admin API")
    user = await repository.get_by_email(session, email)
    if user is None:
        raise ValueError("User not found; register the account before bootstrapping it")
    if not user.is_active:
        raise ValueError("Inactive users cannot be bootstrapped as administrators")
    previous = user.role
    user.role = "admin"
    await repository.save(session)
    await add_audit_event(
        session,
        event_type="user.admin_bootstrapped",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=None,
        metadata={"previous_role": previous, "role": "admin"},
    )
    await session.commit()
    await session.refresh(user)
    return user
