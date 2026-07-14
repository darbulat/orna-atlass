"""PostgreSQL proof that the local seed mutates only explicitly owned rows."""

from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.seed_atlas import (
    SEED_OWNER,
    _adopt_legacy_seed_rows,
    _seed_collections,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use a disposable PostgreSQL database",
    ),
]


@pytest.mark.asyncio
async def test_seed_collection_sync_preserves_user_owned_links() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    suffix = uuid4().hex
    seed_location_id = uuid4()
    user_location_id = uuid4()
    collection_id = uuid4()
    async with AsyncSession(engine) as session:
        transaction = await session.begin()
        try:
            for location_id, slug, metadata in (
                (
                    seed_location_id,
                    "valdaysky-dawn-forest",
                    {"seed": True, "seed_owner": SEED_OWNER},
                ),
                (user_location_id, f"user-location-{suffix}", {}),
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO locations (
                            id, slug, name, exact_latitude, exact_longitude,
                            coordinate_visibility, sensitivity_level, timezone,
                            metadata, created_at, updated_at
                        ) VALUES (
                            :id, :slug, :slug, 10, 20, 'exact_public', 'none', 'UTC',
                            CAST(:metadata AS jsonb), now(), now()
                        )
                        """
                    ),
                    {
                        "id": location_id,
                        "slug": slug,
                        "metadata": json.dumps(metadata),
                    },
                )
            await session.execute(
                text(
                    """
                    INSERT INTO collections (
                        id, slug, title, is_public, sort_order, metadata, created_at, updated_at
                    ) VALUES (
                        :id, 'dawn-archive', 'Existing seed collection', true, 0,
                        CAST(:metadata AS jsonb), now(), now()
                    )
                    """
                ),
                {
                    "id": collection_id,
                    "metadata": json.dumps(
                        {"seed": True, "seed_owner": SEED_OWNER}
                    ),
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO collection_locations (
                        id, collection_id, location_id, sort_order, seed_owner
                    ) VALUES
                        (:seed_link_id, :collection_id, :seed_location_id, 0, :seed_owner),
                        (:user_link_id, :collection_id, :user_location_id, 99, NULL)
                    """
                ),
                {
                    "seed_link_id": uuid4(),
                    "user_link_id": uuid4(),
                    "collection_id": collection_id,
                    "seed_location_id": seed_location_id,
                    "user_location_id": user_location_id,
                    "seed_owner": SEED_OWNER,
                },
            )
            await session.flush()

            await _seed_collections(session)
            await session.flush()

            links = (
                await session.execute(
                    text(
                        """
                        SELECT location_id, seed_owner
                        FROM collection_locations
                        WHERE collection_id = :collection_id
                        """
                    ),
                    {"collection_id": collection_id},
                )
            ).all()
            assert set(links) == {
                (seed_location_id, SEED_OWNER),
                (user_location_id, None),
            }
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_seed_adoption_is_explicit_and_manifest_bounded() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    known_id = uuid4()
    arbitrary_id = uuid4()
    suffix = uuid4().hex
    async with AsyncSession(engine) as session:
        transaction = await session.begin()
        try:
            for location_id, slug in (
                (known_id, "valdaysky-dawn-forest"),
                (arbitrary_id, f"user-seed-marker-{suffix}"),
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO locations (
                            id, slug, name, exact_latitude, exact_longitude,
                            coordinate_visibility, sensitivity_level, timezone,
                            metadata, created_at, updated_at
                        ) VALUES (
                            :id, :slug, :slug, 10, 20, 'exact_public', 'none', 'UTC',
                            '{"seed": true}'::jsonb, now(), now()
                        )
                        """
                    ),
                    {"id": location_id, "slug": slug},
                )

            await _adopt_legacy_seed_rows(session)
            owners = dict(
                (
                    await session.execute(
                        text(
                            """
                            SELECT id, metadata ->> 'seed_owner'
                            FROM locations
                            WHERE id IN (:known_id, :arbitrary_id)
                            """
                        ),
                        {"known_id": known_id, "arbitrary_id": arbitrary_id},
                    )
                ).all()
            )

            assert owners[known_id] == SEED_OWNER
            assert owners[arbitrary_id] is None
        finally:
            await transaction.rollback()
    await engine.dispose()
