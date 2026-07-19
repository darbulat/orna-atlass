from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orna_atlas.app.modules.auth.models import OAuthIdentity, RefreshToken


async def create_refresh_token(
    session: AsyncSession, *, user_id: UUID, token_hash: str, expires_at: datetime
) -> RefreshToken:
    token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    session.add(token)
    await session.flush()
    return token


async def get_refresh_token(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken)
        .options(selectinload(RefreshToken.user))
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def revoke(session: AsyncSession, token: RefreshToken) -> None:
    token.revoked_at = datetime.now(UTC)
    await session.flush()


async def revoke_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    for token in result.scalars():
        token.revoked_at = now
    await session.flush()


async def get_oauth_identity(
    session: AsyncSession, provider: str, subject: str
) -> OAuthIdentity | None:
    result = await session.execute(
        select(OAuthIdentity)
        .options(selectinload(OAuthIdentity.user))
        .where(OAuthIdentity.provider == provider, OAuthIdentity.subject == subject)
    )
    return result.scalar_one_or_none()


async def create_oauth_identity(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider: str,
    subject: str,
    email: str,
) -> OAuthIdentity:
    identity = OAuthIdentity(
        user_id=user_id,
        provider=provider,
        subject=subject,
        email=email.lower(),
    )
    session.add(identity)
    await session.flush()
    return identity
