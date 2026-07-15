"""Migration-backed API proof that exact/hidden coordinates never leak publicly."""

from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.main import app
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import LocationUpdate

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use disposable PostgreSQL/Redis services",
    ),
]


async def _insert_privacy_fixture(session_factory):
    suffix = uuid4().hex
    habitat = f"privacy-{suffix}"
    collection_id = uuid4()
    locations: dict[str, tuple[UUID, str]] = {}
    sessions: dict[str, tuple[UUID, str]] = {}
    async with session_factory() as session:
        for kind, exact_lat, exact_lon, public_lat, public_lon, visibility in (
            ("exact", 10.0, 30.0, None, None, "exact_public"),
            ("approximate", 20.0, 40.0, 21.0, 41.0, "approximate_public"),
            ("hidden", 30.0, 50.0, None, None, "hidden_public"),
        ):
            location_id = uuid4()
            session_id = uuid4()
            location_slug = f"privacy-{kind}-{suffix}"
            session_slug = f"privacy-session-{kind}-{suffix}"
            locations[kind] = (location_id, location_slug)
            sessions[kind] = (session_id, session_slug)
            await session.execute(
                text(
                    """
                    INSERT INTO locations (
                        id, slug, name, habitat, exact_latitude, exact_longitude,
                        public_latitude, public_longitude, coordinate_visibility,
                        sensitivity_level, timezone, metadata, created_at, updated_at
                    ) VALUES (
                        :id, :slug, :name, :habitat, :exact_latitude, :exact_longitude,
                        :public_latitude, :public_longitude, :visibility,
                        'none', 'UTC', '{"private_note":"secret"}'::jsonb, now(), now()
                    )
                    """
                ),
                {
                    "id": location_id,
                    "slug": location_slug,
                    "name": f"Privacy {suffix} {kind}",
                    "habitat": habitat,
                    "exact_latitude": exact_lat,
                    "exact_longitude": exact_lon,
                    "public_latitude": public_lat,
                    "public_longitude": public_lon,
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
                    "slug": session_slug,
                    "title": f"Privacy {suffix} session {kind}",
                },
            )
        await session.execute(
            text(
                """
                INSERT INTO collections (
                    id, slug, title, is_public, sort_order, metadata, created_at, updated_at
                ) VALUES (
                    :id, :slug, 'Privacy integration', true, 0, '{}'::jsonb, now(), now()
                )
                """
            ),
            {"id": collection_id, "slug": f"privacy-collection-{suffix}"},
        )
        for sort_order, (location_id, _) in enumerate(locations.values()):
            await session.execute(
                text(
                    """
                    INSERT INTO collection_locations (id, collection_id, location_id, sort_order)
                    VALUES (:id, :collection_id, :location_id, :sort_order)
                    """
                ),
                {
                    "id": uuid4(),
                    "collection_id": collection_id,
                    "location_id": location_id,
                    "sort_order": sort_order,
                },
            )
        for sort_order, (session_id, _) in enumerate(sessions.values()):
            await session.execute(
                text(
                    """
                    INSERT INTO collection_sessions (id, collection_id, session_id, sort_order)
                    VALUES (:id, :collection_id, :session_id, :sort_order)
                    """
                ),
                {
                    "id": uuid4(),
                    "collection_id": collection_id,
                    "session_id": session_id,
                    "sort_order": sort_order,
                },
            )
        await session.commit()
    return {
        "suffix": suffix,
        "habitat": habitat,
        "collection_id": collection_id,
        "collection_slug": f"privacy-collection-{suffix}",
        "locations": locations,
        "sessions": sessions,
    }


async def _delete_privacy_fixture(session_factory, fixture) -> None:
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM collections WHERE id = :id"),
            {"id": fixture["collection_id"]},
        )
        await session.execute(
            text("DELETE FROM locations WHERE id = ANY(:ids)"),
            {"ids": [item[0] for item in fixture["locations"].values()]},
        )
        await session.commit()


async def _hide_location(session_factory, location_id: UUID) -> None:
    async with session_factory() as session:
        await locations_service.update_location(
            session,
            location_id,
            LocationUpdate(coordinate_visibility="hidden_public"),
        )


def _assert_public_location(payload: dict, *, latitude: float, longitude: float) -> None:
    assert payload["latitude"] == latitude
    assert payload["longitude"] == longitude
    assert "exact_latitude" not in payload
    assert "exact_longitude" not in payload
    assert "public_latitude" not in payload
    assert "public_longitude" not in payload
    assert "metadata" not in payload
    assert "created_at" not in payload
    assert "updated_at" not in payload


def test_public_api_uses_one_privacy_projection_across_all_flows() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = asyncio.run(_insert_privacy_fixture(session_factory))

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        with TestClient(app) as client:
            locations_response = client.get("/api/v1/locations?limit=100")
            assert locations_response.status_code == 200
            locations = {
                item["slug"]: item
                for item in locations_response.json()
                if fixture["suffix"] in item["slug"]
            }
            exact_slug = fixture["locations"]["exact"][1]
            approximate_slug = fixture["locations"]["approximate"][1]
            hidden_slug = fixture["locations"]["hidden"][1]
            assert set(locations) == {exact_slug, approximate_slug}
            _assert_public_location(locations[exact_slug], latitude=10.0, longitude=30.0)
            _assert_public_location(
                locations[approximate_slug],
                latitude=21.0,
                longitude=41.0,
            )
            assert client.get(f"/api/v1/locations/{hidden_slug}").status_code == 404

            sessions_response = client.get("/api/v1/sessions?limit=100")
            assert sessions_response.status_code == 200
            visible_sessions = [
                item
                for item in sessions_response.json()
                if fixture["suffix"] in item["slug"]
            ]
            assert {item["slug"] for item in visible_sessions} == {
                fixture["sessions"]["exact"][1],
                fixture["sessions"]["approximate"][1],
            }
            assert (
                client.get(
                    f"/api/v1/sessions/{fixture['sessions']['hidden'][1]}"
                ).status_code
                == 404
            )

            collection_response = client.get(
                f"/api/v1/collections/{fixture['collection_slug']}"
            )
            assert collection_response.status_code == 200
            collection = collection_response.json()
            assert {item["slug"] for item in collection["locations"]} == {
                exact_slug,
                approximate_slug,
            }
            assert {item["slug"] for item in collection["sessions"]} == {
                fixture["sessions"]["exact"][1],
                fixture["sessions"]["approximate"][1],
            }
            for item in collection["locations"]:
                assert "exact_latitude" not in item
                assert "metadata" not in item

            search_response = client.get(
                "/api/v1/search",
                params={"q": fixture["suffix"], "limit": 25},
            )
            assert search_response.status_code == 200
            search_slugs = {item["slug"] for item in search_response.json()}
            assert hidden_slug not in search_slugs
            assert fixture["sessions"]["hidden"][1] not in search_slugs
            assert {exact_slug, approximate_slug} <= search_slugs

            atlas_response = client.get(
                "/api/v1/atlas/points",
                params={
                    "zoom": 5,
                    "habitat": fixture["habitat"],
                    "limit": 20,
                },
            )
            assert atlas_response.status_code == 200
            atlas_points = {item["slug"]: item for item in atlas_response.json()["points"]}
            assert set(atlas_points) == {exact_slug, approximate_slug}
            _assert_public_location(atlas_points[exact_slug], latitude=10.0, longitude=30.0)
            _assert_public_location(
                atlas_points[approximate_slug],
                latitude=21.0,
                longitude=41.0,
            )

            # The first response is now in Redis. A committed privacy change must
            # invalidate it before the same URL is read again.
            asyncio.run(
                _hide_location(
                    session_factory,
                    fixture["locations"]["exact"][0],
                )
            )
            refreshed_atlas = client.get(
                "/api/v1/atlas/points",
                params={
                    "zoom": 5,
                    "habitat": fixture["habitat"],
                    "limit": 20,
                },
            )
            assert refreshed_atlas.status_code == 200
            assert {
                item["slug"] for item in refreshed_atlas.json()["points"]
            } == {approximate_slug}
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        asyncio.run(_delete_privacy_fixture(session_factory, fixture))
        asyncio.run(engine.dispose())
