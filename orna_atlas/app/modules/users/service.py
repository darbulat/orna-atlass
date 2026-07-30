from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.domain_errors import AuthenticationError, ForbiddenError
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.admin.context import (
    apply_actor_mode_metadata,
    build_admin_user_etag,
    validate_if_match_or_fail,
)
from orna_atlas.app.modules.memberships import repository as memberships_repository
from orna_atlas.app.modules.memberships.schemas import MembershipAbsentRead, MembershipRead
from orna_atlas.app.modules.users import repository
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRead, UserRoleUpdate


async def require_user(session: AsyncSession, user_id: UUID) -> User:
    user = await repository.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User is unavailable")
    return user


async def require_user_for_update(session: AsyncSession, user_id: UUID) -> User:
    user = await repository.get_by_id_for_update(session, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User is unavailable")
    return user


async def update_role(
    session: AsyncSession,
    user_id: UUID,
    data: UserRoleUpdate,
    *,
    actor_user_id: UUID | None,
    if_match: str | None = None,
    actor_mode: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    if actor_user_id is not None and actor_user_id == user_id:
        raise ForbiddenError("Admins cannot modify their own role")

    user = await repository.get_by_id_for_update(session, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User is unavailable")

    current_membership = await memberships_repository.get_for_user(session, user_id)

    if if_match is not None:
        validate_if_match_or_fail(
            if_match=if_match,
            expected=build_admin_user_etag(
                user_id=user.id,
                user_updated_at=user.updated_at,
                membership_updated_at=(
                    current_membership.updated_at if current_membership is not None else None
                ),
            ),
        )

    previous = user.role
    if previous == "admin" and data.role != "admin":
        await repository.acquire_role_change_lock(session)
        active_admin_count = await repository.count_active_admins(session)
        if active_admin_count <= 1:
            raise ForbiddenError("At least one active admin must remain")

    if previous == data.role:
        return user

    user.role = data.role
    await repository.save(session)
    await add_audit_event(
        session,
        event_type="user.role_updated",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {"previous_role": previous, "role": data.role,
             "changed_fields": ["role"]},
            actor_mode,
        ),
    )
    await session.commit()
    await session.refresh(user)
    return user


@dataclass(frozen=True)
class AdminUserProjection:
    user: UserRead
    membership: MembershipAbsentRead | MembershipRead
    updated_at: datetime
    membership_updated_at: datetime | None


def _project_admin_user(user: User) -> AdminUserProjection:
    if user.membership is None:
        membership = MembershipAbsentRead(user_id=user.id)
    else:
        membership = MembershipRead.model_validate(user.membership)
    return AdminUserProjection(
        user=UserRead.model_validate(
            {
                "id": user.id,
                "email": user.email,
                "email_verified": getattr(user, "email_verified", False),
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
        ),
        membership=membership,
        updated_at=getattr(user, "updated_at", user.created_at),
        membership_updated_at=getattr(user.membership, "updated_at", None),
    )


async def list_admin(
    session: AsyncSession,
    *,
    email: str | None,
    role: str | None,
    is_active: bool | None,
    membership_status: str | None,
    limit: int,
    offset: int,
) -> list[AdminUserProjection]:
    users = await repository.list_for_admin(
        session,
        email=email,
        role=role,
        is_active=is_active,
        membership_status=membership_status,
        limit=limit,
        offset=offset,
    )
    return [_project_admin_user(user) for user in users]


async def require_admin_user(session: AsyncSession, user_id: UUID) -> AdminUserProjection:
    user = await repository.get_for_admin(session, user_id)
    if user is None:
        raise AuthenticationError("User is unavailable")
    return _project_admin_user(user)


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
