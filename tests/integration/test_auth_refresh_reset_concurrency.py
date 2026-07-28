import asyncio
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.core.domain_errors import AuthenticationError
from orna_atlas.app.core.security import hash_token
from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.modules.auth import account_tokens, repository, service
from orna_atlas.app.modules.auth.models import RefreshToken
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.models import User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


@pytest.mark.asyncio
async def test_user_row_lock_refreshes_stale_identity_map_state() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id = uuid4()
    email = f"identity-{user_id}@example.test"
    try:
        async with AsyncSession(engine) as setup:
            setup.add(
                User(
                    id=user_id,
                    email=email,
                    password_hash="original-hash",
                    role="admin",
                    is_active=True,
                )
            )
            await setup.commit()

        async with AsyncSession(engine) as stale_session:
            stale_user = await users_repository.get_by_id(stale_session, user_id)
            assert stale_user is not None and stale_user.role == "admin"
            async with AsyncSession(engine) as update_session:
                await update_session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(role="member", is_active=False)
                )
                await update_session.commit()

            locked_user = await users_repository.get_by_id_for_update(stale_session, user_id)
            assert locked_user is not None
            assert locked_user is stale_user
            assert locked_user.role == "member"
            assert locked_user.is_active is False
            await stale_session.rollback()
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_password_reset_serializes_with_refresh_rotation(monkeypatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id = uuid4()
    raw_refresh = f"refresh-{uuid4().hex}"
    reset_has_user_lock = asyncio.Event()
    allow_reset_to_revoke = asyncio.Event()
    original_revoke_all = repository.revoke_all_for_user

    async def claim_reset_token(_kind: str, _token: str) -> account_tokens.TokenClaim:
        return account_tokens.TokenClaim(
            claim_id="integration-claim",
            claims={
                "kind": "password_reset",
                "user_id": str(user_id),
                "email": f"race-{user_id}@example.test",
            },
        )

    async def complete_claim(*_args) -> bool:
        return True

    async def paused_revoke_all(session: AsyncSession, locked_user_id) -> None:
        assert locked_user_id == user_id
        reset_has_user_lock.set()
        await allow_reset_to_revoke.wait()
        await original_revoke_all(session, locked_user_id)

    monkeypatch.setattr(account_tokens, "claim_token", claim_reset_token)
    monkeypatch.setattr(account_tokens, "finalize_token_claim", complete_claim)
    monkeypatch.setattr(account_tokens, "rollback_token_claim", complete_claim)
    monkeypatch.setattr(service, "hash_password", lambda _password: "replacement-hash")
    monkeypatch.setattr(repository, "revoke_all_for_user", paused_revoke_all)

    try:
        async with AsyncSession(engine) as setup:
            setup.add(
                User(
                    id=user_id,
                    email=f"race-{user_id}@example.test",
                    password_hash="original-hash",
                    role="member",
                    is_active=True,
                )
            )
            setup.add(
                RefreshToken(
                    user_id=user_id,
                    token_hash=hash_token(raw_refresh),
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            await setup.commit()

        async def reset_password() -> None:
            async with AsyncSession(engine) as session:
                await service.confirm_password_reset(
                    session,
                    "r" * 43,
                    "replacement password",
                )
                await session.commit()

        async def rotate_refresh() -> None:
            await reset_has_user_lock.wait()
            async with AsyncSession(engine) as session:
                with pytest.raises(AuthenticationError):
                    await service.rotate_refresh_token(session, raw_refresh)
                await session.rollback()

        reset_task = asyncio.create_task(reset_password())
        await reset_has_user_lock.wait()
        refresh_task = asyncio.create_task(rotate_refresh())
        await asyncio.sleep(0.1)
        assert not refresh_task.done()
        allow_reset_to_revoke.set()
        await asyncio.gather(reset_task, refresh_task)

        async with AsyncSession(engine) as verify:
            token = await verify.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
            )
            user = await verify.get(User, user_id)
            assert token is not None and token.revoked_at is not None
            assert user is not None and user.password_hash == "replacement-hash"
    finally:
        allow_reset_to_revoke.set()
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
