import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.db import models as _models  # noqa: F401
from orna_atlas.app.modules.library import repository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use a disposable PostgreSQL database",
    ),
]


@pytest.mark.asyncio
async def test_account_library_upserts_are_idempotent_and_user_delete_cascades() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id, location_id, session_id = uuid4(), uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO users (id, email, role, is_active, created_at, updated_at)
                    VALUES (:user_id, :email, 'member', true, now(), now())
                """),
                {"user_id": user_id, "email": f"library-{user_id}@example.test"},
            )
            await connection.execute(
                text("""
                    INSERT INTO locations (
                        id, slug, name, exact_latitude, exact_longitude,
                        coordinate_visibility, sensitivity_level, timezone,
                        metadata, created_at, updated_at
                    ) VALUES (
                        :location_id, :slug, 'Library location', 1, 1,
                        'exact_public', 'none', 'UTC', '{}'::jsonb, now(), now()
                    )
                """),
                {"location_id": location_id, "slug": f"library-location-{location_id}"},
            )
            await connection.execute(
                text("""
                    INSERT INTO recording_sessions (
                        id, location_id, slug, title, recorded_at, duration_seconds,
                        access_level, processing_status, is_featured, metadata,
                        created_at, updated_at
                    ) VALUES (
                        :session_id, :location_id, :slug, 'Library session', now(), 120,
                        'public', 'ready', false, '{}'::jsonb, now(), now()
                    )
                """),
                {"session_id": session_id, "location_id": location_id, "slug": f"library-session-{session_id}"},
            )

        now = datetime.now(UTC)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await repository.upsert_favorite(session, user_id, session_id, created_at=now)
            await repository.upsert_favorite(session, user_id, session_id, created_at=now)
            await session.commit()

        async def persist_history(position: float, completed: bool, event_time: datetime) -> None:
            async with AsyncSession(engine, expire_on_commit=False) as history_session:
                await repository.upsert_history(
                    history_session,
                    user_id,
                    session_id,
                    position_seconds=position,
                    completed=completed,
                    now=event_time,
                )
                await history_session.commit()

        await asyncio.gather(
            persist_history(120, True, now),
            persist_history(5, False, now - timedelta(seconds=1)),
        )
        await persist_history(119, True, now + timedelta(seconds=1))

        async with engine.begin() as connection:
            assert (await connection.execute(text(
                "SELECT count(*) FROM user_favorites WHERE user_id = :user_id"
            ), {"user_id": user_id})).scalar_one() == 1
            row = (await connection.execute(text("""
                SELECT first_listened_at, last_listened_at, last_position_seconds, completed_at
                FROM listening_history
                WHERE user_id = :user_id AND session_id = :session_id
            """), {"user_id": user_id, "session_id": session_id})).one()
            assert row == (
                now - timedelta(seconds=1),
                now + timedelta(seconds=1),
                119.0,
                now,
            )

            await connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            assert (await connection.execute(text(
                "SELECT count(*) FROM user_favorites WHERE user_id = :user_id"
            ), {"user_id": user_id})).scalar_one() == 0
            assert (await connection.execute(text(
                "SELECT count(*) FROM listening_history WHERE user_id = :user_id"
            ), {"user_id": user_id})).scalar_one() == 0
    finally:
        await engine.dispose()
