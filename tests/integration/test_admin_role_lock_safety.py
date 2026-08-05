import asyncio
import os
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orna_atlas.app.core.domain_errors import ForbiddenError
from orna_atlas.app.db import models as _models  # noqa: F401
from orna_atlas.app.modules.admin.models import AuditEvent
from orna_atlas.app.modules.users import service
from orna_atlas.app.modules.users.models import User
from orna_atlas.app.modules.users.schemas import UserRoleUpdate


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


@pytest.mark.asyncio
async def test_concurrent_admin_demotion_leaves_one_active_admin() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_ids = [uuid4(), uuid4()]
    actor_user_id = uuid4()

    try:
        async with AsyncSession(engine) as setup:
            setup.add_all(
                User(
                    id=user_id,
                    email=f"admin-{user_id}@example.test",
                    password_hash="hashed",
                    role="admin",
                    is_active=True,
                )
                for user_id in user_ids
            )
            setup.add(
                User(
                    id=actor_user_id,
                    email=f"actor-{actor_user_id}@example.test",
                    password_hash="hashed",
                    role="member",
                    is_active=True,
                )
            )
            await setup.commit()

        async def demote(admin_id: UUID) -> str:
            try:
                async with session_factory() as session:
                    await service.update_role(
                        session,
                        admin_id,
                        UserRoleUpdate(role="member"),
                        actor_user_id=actor_user_id,
                    )
                return "success"
            except ForbiddenError:
                return "forbidden"

        results = await asyncio.gather(
            asyncio.create_task(demote(user_ids[0])),
            asyncio.create_task(demote(user_ids[1])),
        )

        assert sorted(results) == ["forbidden", "success"]

        async with AsyncSession(engine) as verify:
            active_admin_count = await verify.scalar(
                select(func.count())
                .where(User.role == "admin", User.is_active.is_(True))
                .select_from(User)
            )
            assert active_admin_count is not None
            assert int(active_admin_count) == 1
            rows = (await verify.execute(select(User.id, User.role).where(User.id.in_(user_ids)))).all()
            roles = {str(row.id): row.role for row in rows}
            assert "admin" in roles.values()
            assert "member" in roles.values()
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(
                delete(AuditEvent).where(
                    AuditEvent.event_type == "user.role_updated",
                    AuditEvent.subject_id.in_([str(user_id) for user_id in user_ids]),
                )
            )
            await cleanup.execute(delete(User).where(User.id.in_([*user_ids, actor_user_id])))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_role_mutation_in_postgres(monkeypatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    target_user_id = uuid4()
    actor_user_id = uuid4()

    try:
        async with AsyncSession(engine) as setup:
            setup.add_all(
                [
                    User(
                        id=target_user_id,
                        email=f"audit-target-{target_user_id}@example.test",
                        password_hash="hashed",
                        role="member",
                        is_active=True,
                    ),
                    User(
                        id=actor_user_id,
                        email=f"audit-actor-{actor_user_id}@example.test",
                        password_hash="hashed",
                        role="admin",
                        is_active=True,
                    ),
                ]
            )
            await setup.commit()

        monkeypatch.setattr(
            service,
            "add_audit_event",
            AsyncMock(side_effect=RuntimeError("audit unavailable")),
        )
        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="audit unavailable"):
                await service.update_role(
                    session,
                    target_user_id,
                    UserRoleUpdate(role="editor"),
                    actor_user_id=actor_user_id,
                )

        async with AsyncSession(engine) as verify:
            role = await verify.scalar(select(User.role).where(User.id == target_user_id))
            audit_count = await verify.scalar(
                select(func.count())
                .where(
                    AuditEvent.event_type == "user.role_updated",
                    AuditEvent.subject_id == str(target_user_id),
                )
                .select_from(AuditEvent)
            )
            assert role == "member"
            assert audit_count == 0
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(
                delete(AuditEvent).where(AuditEvent.subject_id == str(target_user_id))
            )
            await cleanup.execute(
                delete(User).where(User.id.in_([target_user_id, actor_user_id]))
            )
            await cleanup.commit()
        await engine.dispose()
