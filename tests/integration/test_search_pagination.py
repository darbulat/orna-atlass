"""PostgreSQL-backed proof for stable mixed search pagination."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.modules.atlas.repository import search_locations_and_sessions
from orna_atlas.app.modules.locations.models import Location

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use a disposable PostgreSQL database",
    ),
]


@pytest.mark.asyncio
async def test_mixed_search_pages_are_stable_complete_and_non_overlapping() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    marker = f"page{uuid4().hex}"
    async with AsyncSession(engine) as session:
        transaction = await session.begin()
        try:
            for index in range(15):
                location_id = uuid4()
                await session.execute(
                    text(
                        """
                        INSERT INTO locations (
                            id, slug, name, exact_latitude, exact_longitude,
                            coordinate_visibility, sensitivity_level, timezone,
                            metadata, created_at, updated_at
                        ) VALUES (
                            :id, :slug, :name, :latitude, :longitude,
                            'exact_public', 'none', 'UTC', '{}'::jsonb, now(), now()
                        )
                        """
                    ),
                    {
                        "id": location_id,
                        "slug": f"{marker}-location-{index:02d}",
                        "name": f"{marker} location {index:02d}",
                        "latitude": -10 + index / 10,
                        "longitude": 20 + index / 10,
                    },
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO recording_sessions (
                            id, location_id, slug, title, recorded_at, access_level,
                            publication_status, processing_status, is_featured,
                            metadata, created_at, updated_at
                        ) VALUES (
                            :id, :location_id, :slug, :title,
                            now() - (:position * interval '1 minute'), 'public',
                            'published', 'pending', false, '{}'::jsonb, now(), now()
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "location_id": location_id,
                        "slug": f"{marker}-session-{index:02d}",
                        "title": f"{marker} session {index:02d}",
                        "position": index,
                    },
                )
            await session.flush()

            pages: list[list[tuple[str, str]]] = []
            for offset in range(0, 35, 7):
                rows = await search_locations_and_sessions(
                    session,
                    query=marker,
                    limit=7,
                    offset=offset,
                )
                pages.append(
                    [
                        (
                            "location" if isinstance(row, Location) else "session",
                            str(row.id),
                        )
                        for row in rows
                    ]
                )
            repeated_second_page = await search_locations_and_sessions(
                session,
                query=marker,
                limit=7,
                offset=7,
            )

            flattened = [item for page in pages for item in page]
            assert len(flattened) == 30
            assert len(set(flattened)) == 30
            assert pages[-1] == flattened[28:]
            assert pages[1] == [
                (
                    "location" if isinstance(row, Location) else "session",
                    str(row.id),
                )
                for row in repeated_second_page
            ]
        finally:
            await transaction.rollback()
    await engine.dispose()
