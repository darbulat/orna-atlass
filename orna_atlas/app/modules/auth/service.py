from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.auth import repository
from orna_atlas.app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRead


async def register(session: AsyncSession, data: RegisterRequest) -> User:
    if await users_repository.get_by_email(session, str(data.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        user = await users_repository.create(
            session, email=str(data.email), password_hash=hash_password(data.password)
        )
        await add_audit_event(
            session,
            event_type="auth.user_registered",
            subject_type="user",
            subject_id=str(user.id),
            actor_user_id=user.id,
        )
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc


async def authenticate(session: AsyncSession, data: LoginRequest) -> User:
    user = await users_repository.get_by_email(session, str(data.email))
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


async def issue_token_pair(session: AsyncSession, user: User) -> tuple[TokenResponse, str]:
    access_token, expires_at = create_access_token(user.id, user.role, user.email)
    refresh_token = new_refresh_token()
    refresh_expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days)
    await repository.create_refresh_token(
        session, user_id=user.id, token_hash=hash_token(refresh_token), expires_at=refresh_expires
    )
    await session.commit()
    return (
        TokenResponse(
            access_token=access_token,
            expires_at=expires_at,
            user=UserRead.model_validate(user),
        ),
        refresh_token,
    )


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str
) -> tuple[TokenResponse, str]:
    stored = await repository.get_refresh_token(session, hash_token(raw_token))
    if stored is None or not stored.is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = stored.user
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")
    await repository.revoke(session, stored)
    return await issue_token_pair(session, user)


async def logout(session: AsyncSession, raw_token: str | None) -> None:
    if raw_token:
        stored = await repository.get_refresh_token(session, hash_token(raw_token))
        if stored is not None and stored.revoked_at is None:
            await repository.revoke(session, stored)
    await session.commit()
