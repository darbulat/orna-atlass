import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use a disposable PostgreSQL database",
    ),
]


@pytest.mark.asyncio
async def test_database_rejects_unknown_session_access_state() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    location_slug = f"constraint-location-{uuid4().hex}"
    try:
        async with engine.begin() as connection:
            location_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO locations (
                            id, slug, name, exact_latitude, exact_longitude,
                            coordinate_visibility, sensitivity_level, timezone,
                            metadata, created_at, updated_at
                        ) VALUES (
                            gen_random_uuid(), :location_slug, 'Constraint location', 1, 1,
                            'exact_public', 'none', 'UTC', '{}'::jsonb, now(), now()
                        ) RETURNING id
                        """
                    ),
                    {"location_slug": location_slug},
                )
            ).scalar_one()
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO recording_sessions (
                                id, location_id, slug, title, recorded_at, access_level,
                                processing_status, is_featured, metadata, created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(), :location_id, 'invalid-state', 'Invalid state',
                                now(), 'unknown', 'pending', false, '{}'::jsonb, now(), now()
                            )
                            """
                        ),
                        {"location_id": location_id},
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_approximate_visibility_without_public_point() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO locations (
                                id, slug, name, exact_latitude, exact_longitude,
                                coordinate_visibility, sensitivity_level, timezone,
                                metadata, created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(), :slug, 'Invalid approximate point', 1, 1,
                                'approximate_public', 'none', 'UTC', '{}'::jsonb, now(), now()
                            )
                            """
                        ),
                        {"slug": f"invalid-approximate-{os.getpid()}"},
                    )
    finally:
        await engine.dispose()
