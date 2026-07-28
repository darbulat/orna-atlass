import asyncio
from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.async_utils import finish_cancelled_compensation
from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ServiceUnavailableError,
)
from orna_atlas.app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from orna_atlas.app.db.session import AsyncSessionLocal
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.auth import account_tokens, repository
from orna_atlas.app.modules.auth.oauth import OAuthLinkIntent, VerifiedIdentity
from orna_atlas.app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRead

logger = logging.getLogger(__name__)


_DUMMY_PASSWORD_HASH = hash_password("orna-invalid-credential-canary")


class OAuthLinkRequired(ConflictError):
    def __init__(self, *, target_user_id: UUID, identity: VerifiedIdentity) -> None:
        super().__init__("An account with this email uses a different sign-in method")
        self.target_user_id = target_user_id
        self.identity = identity


async def request_email_verification(session: AsyncSession, user_id: UUID) -> None:
    user = await users_repository.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User is unavailable")
    if user.email_verified_at is not None:
        return
    await account_tokens.send_email_verification(
        settings=get_settings(),
        user_id=user.id,
        email=user.email,
    )


async def confirm_email_verification(session: AsyncSession, raw_token: str) -> User:
    claim = await account_tokens.claim_token("email_verification", raw_token)
    if claim is None:
        raise AuthenticationError("Invalid or expired email verification token")
    claims = claim.claims
    try:
        try:
            user_id = UUID(claims["user_id"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("Invalid or expired email verification token") from exc
        user = await users_repository.get_by_id_for_update(session, user_id)
        if (
            user is None
            or not user.is_active
            or user.email.lower() != claims.get("email", "").lower()
        ):
            raise AuthenticationError("Invalid or expired email verification token")
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
            await add_audit_event(
                session,
                event_type="auth.email_verified",
                subject_type="user",
                subject_id=str(user.id),
                actor_user_id=user.id,
            )
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            await finish_cancelled_compensation(session.rollback())
            await finish_cancelled_compensation(
                account_tokens.rollback_token_claim(
                    "email_verification", raw_token, claim.claim_id
                )
            )
            raise exc
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await account_tokens.rollback_token_claim(
                "email_verification", raw_token, claim.claim_id
            )
        except ServiceUnavailableError:
            pass
        raise
    try:
        await session.commit()
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            await finish_cancelled_compensation(session.rollback())
            await finish_cancelled_compensation(
                account_tokens.finalize_token_claim(
                    "email_verification", raw_token, claim.claim_id
                )
            )
            raise exc
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await account_tokens.finalize_token_claim(
                "email_verification", raw_token, claim.claim_id
            )
        except ServiceUnavailableError:
            pass
        raise
    try:
        await account_tokens.finalize_token_claim(
            "email_verification", raw_token, claim.claim_id
        )
    except ServiceUnavailableError:
        pass
    return user


async def request_password_reset(session: AsyncSession, email: str) -> None:
    user = await users_repository.get_by_email(session, email.lower())
    if user is None or not user.is_active or not user.password_hash:
        return
    await account_tokens.send_password_reset(
        settings=get_settings(),
        user_id=user.id,
        email=user.email,
    )


async def deliver_password_reset(email: str) -> None:
    """Run neutral password-reset delivery outside the request response path."""
    try:
        async with AsyncSessionLocal() as session:
            await request_password_reset(session, email)
    except ServiceUnavailableError:
        logger.warning("Password reset delivery unavailable")
    except Exception:
        logger.error("Password reset delivery failed")


async def confirm_password_reset(
    session: AsyncSession,
    raw_token: str,
    new_password: str,
) -> User:
    claim = await account_tokens.claim_token("password_reset", raw_token)
    if claim is None:
        raise AuthenticationError("Invalid or expired password reset token")
    claims = claim.claims
    try:
        try:
            user_id = UUID(claims["user_id"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("Invalid or expired password reset token") from exc
        user = await users_repository.get_by_id_for_update(session, user_id)
        if (
            user is None
            or not user.is_active
            or not user.password_hash
            or user.email.lower() != claims.get("email", "").lower()
        ):
            raise AuthenticationError("Invalid or expired password reset token")
        user.password_hash = hash_password(new_password)
        await repository.revoke_all_for_user(session, user.id)
        await add_audit_event(
            session,
            event_type="auth.password_reset",
            subject_type="user",
            subject_id=str(user.id),
            actor_user_id=user.id,
        )
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            await finish_cancelled_compensation(session.rollback())
            await finish_cancelled_compensation(
                account_tokens.rollback_token_claim(
                    "password_reset", raw_token, claim.claim_id
                )
            )
            raise exc
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await account_tokens.rollback_token_claim(
                "password_reset", raw_token, claim.claim_id
            )
        except ServiceUnavailableError:
            pass
        raise
    try:
        await session.commit()
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            await finish_cancelled_compensation(session.rollback())
            await finish_cancelled_compensation(
                account_tokens.finalize_token_claim(
                    "password_reset", raw_token, claim.claim_id
                )
            )
            raise exc
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await account_tokens.finalize_token_claim(
                "password_reset", raw_token, claim.claim_id
            )
        except ServiceUnavailableError:
            pass
        if isinstance(exc, Exception):
            raise ServiceUnavailableError("Password reset outcome is unavailable") from exc
        raise
    try:
        await account_tokens.finalize_token_claim(
            "password_reset", raw_token, claim.claim_id
        )
    except ServiceUnavailableError:
        pass
    return user


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
    user = await users_repository.get_by_email_for_update(session, str(data.email))
    encoded = user.password_hash if user is not None and user.password_hash else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(data.password, encoded)
    if user is None or not user.is_active or not user.password_hash or not password_valid:
        raise AuthenticationError("Invalid credentials")
    return user


async def authenticate_password_login(
    session: AsyncSession,
    data: LoginRequest,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[TokenResponse, str]:
    user = await authenticate(session, data)
    await add_audit_event(
        session,
        event_type="auth.login_succeeded",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await issue_token_pair(session, user)


async def authenticate_magic_link(
    session: AsyncSession,
    email: str,
    *,
    expected_user_id: UUID | str | None = None,
) -> tuple[TokenResponse, str, bool]:
    user = await users_repository.get_by_email(session, email)
    created = False
    event_type = "auth.magic_link_login_succeeded"
    if expected_user_id is not None:
        if user is None or user.id != UUID(str(expected_user_id)):
            raise AuthenticationError("Magic link no longer matches the existing account")
    if user is None:
        try:
            user = await users_repository.create(
                session,
                email=email,
                password_hash=None,
                email_verified=True,
            )
            created = True
            event_type = "auth.magic_link_user_registered"
        except IntegrityError:
            await session.rollback()
            user = await users_repository.get_by_email(session, email)
            if user is None:
                raise
    if not user.is_active:
        raise AuthenticationError("User is unavailable")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await add_audit_event(
        session,
        event_type=event_type,
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=user.id,
    )
    payload, refresh_token = await issue_token_pair(session, user)
    return payload, refresh_token, created


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
            raise OAuthLinkRequired(target_user_id=user.id, identity=identity)
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


async def link_oauth_identity(
    session: AsyncSession, *, current_user_id: UUID, intent: OAuthLinkIntent
) -> None:
    if (
        intent.target_user_id != current_user_id
        or intent.reauthenticated_user_id != current_user_id
    ):
        raise AuthenticationError("OAuth link requires recent account authentication")
    user = await users_repository.get_by_id_for_update(session, current_user_id)
    if (
        user is None
        or not user.is_active
        or user.email.lower() != intent.email.lower()
    ):
        raise AuthenticationError("OAuth link intent does not match the active account")
    stored_identity = await repository.get_oauth_identity(
        session, intent.provider, intent.subject
    )
    if stored_identity is not None:
        if stored_identity.user_id == current_user_id:
            return
        raise ConflictError("OAuth identity is already linked to another account")
    user_provider_identity = await repository.get_oauth_identity_for_user_provider(
        session, current_user_id, intent.provider
    )
    if user_provider_identity is not None:
        if user_provider_identity.subject == intent.subject:
            return
        raise ConflictError("A different provider identity is already linked")
    try:
        await repository.create_oauth_identity(
            session,
            user_id=current_user_id,
            provider=intent.provider,
            subject=intent.subject,
            email=intent.email,
        )
        await add_audit_event(
            session,
            event_type="auth.oauth_identity_linked",
            subject_type="user",
            subject_id=str(current_user_id),
            actor_user_id=current_user_id,
            metadata={"provider": intent.provider},
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        race_identity = await repository.get_oauth_identity(
            session, intent.provider, intent.subject
        )
        if race_identity is not None:
            if race_identity.user_id == current_user_id:
                return
            raise ConflictError("OAuth identity is already linked to another account")
        race_user_provider = await repository.get_oauth_identity_for_user_provider(
            session, current_user_id, intent.provider
        )
        if (
            race_user_provider is not None
            and race_user_provider.subject == intent.subject
        ):
            return
        if race_user_provider is not None:
            raise ConflictError("A different provider identity is already linked")
        raise


async def issue_token_pair(session: AsyncSession, user: User) -> tuple[TokenResponse, str]:
    locked_user = await users_repository.get_by_id_for_update(session, user.id)
    if locked_user is None or not locked_user.is_active:
        raise AuthenticationError("User is unavailable")
    user = locked_user
    access_token, expires_at = create_access_token(user.id, user.role, user.email)
    refresh_token = new_refresh_token()
    refresh_expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days)
    await repository.create_refresh_token(
        session, user_id=user.id, token_hash=hash_token(refresh_token), expires_at=refresh_expires
    )
    user_read = UserRead.model_validate(user)
    await session.commit()
    return (
        TokenResponse(
            access_token=access_token,
            expires_at=expires_at,
            user=user_read,
        ),
        refresh_token,
    )


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str
) -> tuple[TokenResponse, str]:
    token_hash = hash_token(raw_token)
    candidate = await repository.find_refresh_token(session, token_hash)
    if candidate is None:
        raise AuthenticationError("Invalid refresh token")
    user = await users_repository.get_by_id_for_update(session, candidate.user_id)
    stored = await repository.get_refresh_token(session, token_hash)
    if stored is None or not stored.is_valid:
        raise AuthenticationError("Invalid refresh token")
    if user is None or not user.is_active:
        raise AuthenticationError("User is unavailable")
    await repository.revoke(session, stored)
    return await issue_token_pair(session, user)


async def logout(session: AsyncSession, raw_token: str | None) -> None:
    if raw_token:
        stored = await repository.get_refresh_token(session, hash_token(raw_token))
        if stored is not None and stored.revoked_at is None:
            await repository.revoke(session, stored)
    await session.commit()
