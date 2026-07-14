from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orna_atlas.app.core.domain_errors import NotFoundError, ServiceUnavailableError
from orna_atlas.app.integrations import redis as redis_integration
from orna_atlas.app.main import app
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.locations import repository as locations_repository
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions import service as sessions_service


def _parameter(schema: dict, path: str, name: str) -> dict:
    parameters = schema["paths"][path]["get"]["parameters"]
    return next(parameter for parameter in parameters if parameter["name"] == name)


def test_public_pagination_bounds_are_in_openapi() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    for path in ("/api/v1/locations", "/api/v1/sessions", "/api/v1/collections"):
        limit = _parameter(schema, path, "limit")["schema"]
        offset = _parameter(schema, path, "offset")["schema"]
        assert limit["minimum"] == 1
        assert limit["maximum"] == 100
        assert offset["minimum"] == 0

    featured = _parameter(schema, "/api/v1/sessions/featured", "limit")["schema"]
    assert featured["minimum"] == 1
    assert featured["maximum"] == 50


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_invalid_location_pagination_returns_422(query: str) -> None:
    response = TestClient(app).get(f"/api/v1/locations?{query}")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_location_and_session_queries_share_hidden_location_filter() -> None:
    location_db = AsyncMock()
    location_result = MagicMock()
    location_result.scalars.return_value = []
    location_db.execute.return_value = location_result

    session_db = AsyncMock()
    session_result = MagicMock()
    session_result.scalars.return_value = []
    session_db.execute.return_value = session_result

    await locations_repository.list_locations(location_db)
    await sessions_repository.list_sessions(session_db)
    await sessions_repository.list_featured_sessions(session_db)

    location_sql = str(location_db.execute.await_args.args[0])
    session_statements = [str(call.args[0]) for call in session_db.execute.await_args_list]
    assert "locations.coordinate_visibility !=" in location_sql
    assert all("locations.coordinate_visibility !=" in statement for statement in session_statements)
    assert "media_assets.processing_status" in session_statements[1]
    assert "media_assets.kind" in session_statements[1]


def test_collection_projection_excludes_hidden_locations_and_their_sessions() -> None:
    hidden_location = SimpleNamespace(coordinate_visibility="hidden_public")
    hidden_session = SimpleNamespace(access_level="public", location=hidden_location)
    collection = SimpleNamespace(
        id=uuid4(),
        slug="sensitive-habitats",
        title="Sensitive habitats",
        description=None,
        sort_order=0,
        metadata_={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        location_links=[SimpleNamespace(location=hidden_location)],
        session_links=[SimpleNamespace(session=hidden_session)],
    )

    detail = collections_service.detail_from_collection(collection)

    assert detail.location_count == 0
    assert detail.session_count == 0
    assert detail.locations == []
    assert detail.sessions == []


class FakeRedis:
    def __init__(self) -> None:
        self.deleted: tuple[str, ...] = ()
        self.closed = False

    async def scan_iter(self, *, match: str, count: int):
        assert match == "atlas:*"
        assert count == 100
        for key in ("atlas:points:one", "atlas:dawn:current:two"):
            yield key

    async def delete(self, *keys: str) -> None:
        self.deleted = keys

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_atlas_cache_invalidation_removes_all_atlas_namespaces(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(redis_integration, "get_redis_client", lambda: client)

    await redis_integration.invalidate_atlas_cache()

    assert client.deleted == ("atlas:points:one", "atlas:dawn:current:two")
    assert client.closed


@pytest.mark.asyncio
async def test_location_mutation_invalidates_cache_only_after_persistence(monkeypatch) -> None:
    events: list[str] = []
    location = SimpleNamespace(id=uuid4(), slug="new-location")

    async def persist(_session, _data):
        events.append("persisted")
        return location

    async def invalidate():
        events.append("invalidated")

    monkeypatch.setattr(
        locations_service.repository,
        "get_location_by_slug_for_admin",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(locations_service.repository, "create_location", persist)
    monkeypatch.setattr(locations_service, "invalidate_atlas_cache", invalidate)
    data = SimpleNamespace(slug="new-location")

    result = await locations_service.create_location(AsyncMock(), data)

    assert result is location
    assert events == ["persisted", "invalidated"]


def test_playback_storage_failure_is_not_reported_as_success(monkeypatch) -> None:
    rendition = SimpleNamespace(
        kind="streaming_rendition",
        processing_status="ready",
        storage_key="sessions/example/rendition.wav",
    )
    recording = SimpleNamespace(id=uuid4(), media_assets=[rendition])
    client = SimpleNamespace(
        is_configured=lambda: True,
        object_exists=MagicMock(side_effect=TimeoutError("storage timeout")),
    )
    monkeypatch.setattr(sessions_service, "get_object_storage_client", lambda: client)

    with pytest.raises(ServiceUnavailableError):
        sessions_service.create_playback_grant(recording)


@pytest.mark.asyncio
async def test_hidden_location_playback_is_not_discoverable_to_anonymous_user() -> None:
    recording = SimpleNamespace(
        id=uuid4(),
        access_level="public",
        location=SimpleNamespace(coordinate_visibility="hidden_public"),
    )

    with pytest.raises(NotFoundError) as error:
        await sessions_service.authorize_playback_grant(AsyncMock(), recording, None)

    assert error.value.detail == "Session not found"


def test_docker_context_excludes_local_secrets_and_media() -> None:
    patterns = set(Path(".dockerignore").read_text().splitlines())

    assert {".env", ".git", "web/node_modules", "web/.next", "*.jpg", "*.png"} <= patterns
