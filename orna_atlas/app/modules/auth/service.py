from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ConflictError
from orna_atlas.app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.auth import repository
from orna_atlas.app.modules.auth.oauth import VerifiedIdentity
from orna_atlas.app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRead


_DUMMY_PASSWORD_HASH = hash_password("orna-invalid-credential-canary")


async def register(session: AsyncSession, data: RegisterRequest) -> User:
    if await users_repository.get_by_email(session, str(data.email)):
        raise ConflictError("Email already registered")
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
        raise ConflictError("Email already registered") from exc


async def authenticate(session: AsyncSession, data: LoginRequest) -> User:
    user = await users_repository.get_by_email(session, str(data.email))
    encoded = user.password_hash if user is not None and user.password_hash else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(data.password, encoded)
    if user is None or not user.is_active or not user.password_hash or not password_valid:
        raise AuthenticationError("Invalid credentials")
    return user


async def authenticate_oauth_identity(
    session: AsyncSession, identity: VerifiedIdentity
) -> tuple[TokenResponse, str]:
    if not identity.email_verified:
        raise AuthenticationError("OAuth provider must supply a verified email address")
    stored_identity = await repository.get_oauth_identity(
        session, identity.provider, identity.subject
    )
    if stored_identity is not None:
        user = stored_identity.user
        if not user.is_active:
            raise AuthenticationError("User is unavailable")
        event_type = "auth.oauth_login_succeeded"
    else:
        user = await users_repository.get_by_email(session, identity.email)
        if user is not None:
            raise ConflictError(
                "An account with this email uses a different sign-in method"
            )
        try:
            user = await users_repository.create(
                session,
                email=identity.email,
                password_hash=None,
                email_verified=True,
            )
            event_type = "auth.oauth_user_registered"
            await repository.create_oauth_identity(
                session,
                user_id=user.id,
                provider=identity.provider,
                subject=identity.subject,
                email=identity.email,
            )
        except IntegrityError as exc:
            await session.rollback()
            raced_identity = await repository.get_oauth_identity(
                session, identity.provider, identity.subject
            )
            if raced_identity is None:
                raise ConflictError(
                    "An account with this email uses a different sign-in method"
                ) from exc
            user = raced_identity.user
            if not user.is_active:
                raise AuthenticationError("User is unavailable") from exc
            event_type = "auth.oauth_login_succeeded"
    await add_audit_event(
        session,
        event_type=event_type,
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=user.id,
        metadata={"provider": identity.provider},
    )
    return await issue_token_pair(session, user)


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
        raise AuthenticationError("Invalid refresh token")
    user = stored.user
    if not user.is_active:
        raise AuthenticationError("User is unavailable")
    await repository.revoke(session, stored)
    return await issue_token_pair(session, user)


async def logout(session: AsyncSession, raw_token: str | None) -> None:
    if raw_token:
        stored = await repository.get_refresh_token(session, hash_token(raw_token))
        if stored is not None and stored.revoked_at is None:
            await repository.revoke(session, stored)
    await session.commit()
