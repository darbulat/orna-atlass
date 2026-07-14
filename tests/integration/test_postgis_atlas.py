"""PostGIS-backed atlas query integration tests."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.modules.atlas.repository import (
    BoundingBox,
    list_atlas_clusters,
    list_atlas_locations,
    list_dawn_candidate_locations,
)
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use a disposable PostgreSQL database",
    ),
]


@pytest.mark.asyncio
async def test_postgis_public_projection_bbox_and_clustering() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    location_ids = [uuid4() for _ in range(3)]
    session_ids = [uuid4() for _ in range(3)]
    suffix = uuid4().hex
    async with AsyncSession(engine) as session:
        transaction = await session.begin()
        try:
            for index, (location_id, session_id, longitude, visibility) in enumerate(
                zip(
                    location_ids,
                    session_ids,
                    (179.5, -179.5, 0.0),
                    ("exact_public", "exact_public", "hidden_public"),
                    strict=True,
                )
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO locations (
                            id, slug, name, exact_latitude, exact_longitude,
                            coordinate_visibility, sensitivity_level, timezone,
                            metadata, created_at, updated_at
                        ) VALUES (
                            :id, :slug, :name, 0, :longitude,
                            :visibility, 'none', 'UTC', '{}'::jsonb, now(), now()
                        )
                        """
                    ),
                    {
                        "id": location_id,
                        "slug": f"postgis-{suffix}-{index}",
                        "name": f"PostGIS {index}",
                        "longitude": longitude,
                        "visibility": visibility,
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
                            :id, :location_id, :slug, :title, now(), 'public',
                            'published', 'pending', false, '{}'::jsonb, now(), now()
                        )
                        """
                    ),
                    {
                        "id": session_id,
                        "location_id": location_id,
                        "slug": f"postgis-session-{suffix}-{index}",
                        "title": f"PostGIS session {index}",
                    },
                )
            await session.flush()

            bbox = BoundingBox(west=170, south=-10, east=-170, north=10)
            locations = await list_atlas_locations(
                session, bbox=bbox, habitats=None, limit=10
            )
            clusters = await list_atlas_clusters(
                session, bbox=bbox, habitats=None, zoom=3, limit=10
            )
            dawn_candidates = await list_dawn_candidate_locations(
                session,
                target_longitude=180.0,
                limit=2,
            )

            assert {item.id for item in locations} == set(location_ids[:2])
            assert sum(item.count for item in clusters) == 2
            assert {item.id for item in dawn_candidates} == set(location_ids[:2])
            hidden_public_point = await session.scalar(
                text("SELECT public_point IS NULL FROM locations WHERE id = :id"),
                {"id": location_ids[2]},
            )
            assert hidden_public_point is True
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgis_gist_indexes_exist() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            indexes = set(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexname
                            FROM pg_indexes
                            WHERE tablename = 'locations' AND indexdef ILIKE '%USING gist%'
                            """
                        )
                    )
                ).scalars()
            )
    finally:
        await engine.dispose()

    assert {
        "ix_locations_exact_point_gist",
        "ix_locations_public_point_gist",
    } <= indexes


@pytest.mark.asyncio
async def test_postgis_scale_query_aggregates_100k_rows_inside_database() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    prefix = uuid4().hex
    habitat = f"scale-{prefix}"
    async with AsyncSession(engine) as session:
        transaction = await session.begin()
        try:
            await session.execute(text("SET LOCAL statement_timeout = '120s'"))
            await session.execute(
                text(
                    """
                    INSERT INTO locations (
                        id, slug, name, habitat, exact_latitude, exact_longitude,
                        coordinate_visibility, sensitivity_level, timezone,
                        metadata, created_at, updated_at
                    )
                    SELECT
                        md5(:prefix || '-location-' || item::text)::uuid,
                        :prefix || '-location-' || item::text,
                        'Scale location ' || item::text,
                        :habitat,
                        -60.0 + (item % 12000) / 100.0,
                        -170.0 + (item % 34000) / 100.0,
                        'exact_public', 'none', 'UTC', '{}'::jsonb, now(), now()
                    FROM generate_series(1, 100000) AS item
                    """
                ),
                {"prefix": prefix, "habitat": habitat},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO recording_sessions (
                        id, location_id, slug, title, recorded_at, access_level,
                        publication_status, processing_status, is_featured,
                        metadata, created_at, updated_at
                    )
                    SELECT
                        md5(:prefix || '-session-' || item::text)::uuid,
                        md5(:prefix || '-location-' || item::text)::uuid,
                        :prefix || '-session-' || item::text,
                        'Scale session ' || item::text,
                        now(), 'public', 'published', 'pending', false,
                        '{}'::jsonb, now(), now()
                    FROM generate_series(1, 100000) AS item
                    """
                ),
                {"prefix": prefix},
            )
            await session.execute(text("ANALYZE locations"))

            bbox = BoundingBox(west=29, south=-10, east=31, north=10)
            clusters = await list_atlas_clusters(
                session,
                bbox=bbox,
                habitats=[habitat],
                zoom=3,
                limit=250,
            )
            dawn_candidates = await list_dawn_candidate_locations(
                session,
                target_longitude=30.0,
                limit=128,
            )
            expected_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM locations
                    WHERE habitat = :habitat
                      AND ST_Intersects(
                          public_point,
                          ST_MakeEnvelope(29, -10, 31, 10, 4326)
                      )
                    """
                ),
                {"habitat": habitat},
            )
            plan = (
                await session.execute(
                    text(
                        """
                        EXPLAIN (FORMAT JSON)
                        SELECT id
                        FROM locations
                        WHERE ST_Intersects(
                            public_point,
                            ST_MakeEnvelope(29, -10, 31, 10, 4326)
                        )
                        """
                    )
                )
            ).scalar_one()
            dawn_plan = (
                await session.execute(
                    text(
                        """
                        EXPLAIN (FORMAT JSON)
                        SELECT id
                        FROM locations
                        WHERE public_point IS NOT NULL
                        ORDER BY public_point <-> ST_MakeLine(
                            ST_SetSRID(ST_MakePoint(30, -90), 4326),
                            ST_SetSRID(ST_MakePoint(30, 90), 4326)
                        )
                        LIMIT 128
                        """
                    )
                )
            ).scalar_one()

            assert expected_count and expected_count > 0
            assert sum(cluster.count for cluster in clusters) == expected_count
            assert len(clusters) <= 250
            assert "ix_locations_public_point_gist" in str(plan)
            assert len(dawn_candidates) == 128
            assert "ix_locations_public_point_gist" in str(dawn_plan)
        finally:
            await transaction.rollback()
    await engine.dispose()
