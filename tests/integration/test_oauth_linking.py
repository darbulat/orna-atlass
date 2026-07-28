import asyncio
import hashlib
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.modules.admin.models import AuditEvent
from orna_atlas.app.modules.auth import oauth, service
from orna_atlas.app.modules.auth.models import OAuthIdentity
from orna_atlas.app.modules.users.models import User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


@pytest.mark.asyncio
async def test_real_redis_oauth_link_intent_is_digest_addressed_and_single_use(monkeypatch) -> None:
    redis_url = os.environ["REDIS_URL"]
    monkeypatch.setattr(
        oauth,
        "get_redis_client",
        lambda: Redis.from_url(redis_url, decode_responses=True),
    )
    target_user_id = uuid4()
    raw_intent = await oauth.register_oauth_link_intent(
        oauth.VerifiedIdentity(
            provider="google",
            subject=f"subject-{uuid4().hex}",
            email=f"link-{uuid4().hex}@example.test",
            email_verified=True,
        ),
        target_user_id=target_user_id,
        return_to="/library",
    )
    redis = Redis.from_url(redis_url, decode_responses=True)
    digest_key = f"oauth:link:{hashlib.sha256(raw_intent.encode()).hexdigest()}"
    try:
        assert await redis.exists(digest_key) == 1
        assert raw_intent not in digest_key
        assert await oauth.mark_oauth_link_reauthenticated(raw_intent, uuid4()) is False
        assert await oauth.mark_oauth_link_reauthenticated(raw_intent, target_user_id) is True
        consumed = await oauth.consume_oauth_link_intent(raw_intent)
        assert consumed is not None
        assert consumed.target_user_id == target_user_id
        assert consumed.reauthenticated_user_id == target_user_id
        assert await oauth.consume_oauth_link_intent(raw_intent) is None
    finally:
        await redis.delete(digest_key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_oauth_link_confirmations_converge_to_one_identity() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id = uuid4()
    subject = f"subject-{uuid4().hex}"
    email = f"link-{uuid4().hex}@example.test"
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject=subject,
        email=email,
        target_user_id=user_id,
        return_to="/membership",
        reauthenticated_user_id=user_id,
    )
    try:
        async with AsyncSession(engine) as setup:
            setup.add(
                User(
                    id=user_id,
                    email=email,
                    password_hash="existing-password-hash",
                    role="member",
                    is_active=True,
                )
            )
            await setup.commit()

        async def link_once() -> None:
            async with AsyncSession(engine) as session:
                await service.link_oauth_identity(
                    session,
                    current_user_id=user_id,
                    intent=intent,
                )

        await asyncio.gather(link_once(), link_once())

        async with AsyncSession(engine) as verify:
            identity_count = await verify.scalar(
                select(func.count())
                .select_from(OAuthIdentity)
                .where(
                    OAuthIdentity.provider == "google",
                    OAuthIdentity.subject == subject,
                    OAuthIdentity.user_id == user_id,
                )
            )
            audit_count = await verify.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "auth.oauth_identity_linked",
                    AuditEvent.actor_user_id == user_id,
                )
            )
            assert identity_count == 1
            assert audit_count == 1
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
