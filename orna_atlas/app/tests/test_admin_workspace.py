from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from orna_atlas.app.core.domain_errors import NotFoundError
from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.main import app
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.sessions import service as sessions_service


def _admin_location(*, archived: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        slug="location-admin-view",
        name="Location Admin View",
        description="admin view test",
        country_code="US",
        region="Test Region",
        habitat="wetland",
        exact_latitude=57.123,
        exact_longitude=30.456,
        public_latitude=57.12,
        public_longitude=30.45,
        coordinate_visibility="exact_public",
        sensitivity_level="none",
        timezone="UTC",
        metadata_={"source": "admin-workspace"},
        archived_at=datetime.now(UTC) if archived else None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _admin_session(*, archived: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        location_id=uuid4(),
        slug="session-admin-view",
        title="Session Admin View",
        description="admin session test",
        recorded_at=datetime.now(UTC),
        duration_seconds=120,
        recorder="recorder",
        weather="cloudy",
        access_level="public",
        publication_status="draft",
        processing_status="pending",
        is_featured=False,
        featured_sort_order=None,
        metadata_={"source": "admin-workspace"},
        archived_at=datetime.now(UTC) if archived else None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        media_assets=[],
    )


def _admin_collection(*, is_public: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        slug="collection-admin-view",
        title="Admin collection",
        description="admin collection test",
        is_public=is_public,
        sort_order=1,
        metadata_={"source": "admin-workspace"},
        location_links=[],
        session_links=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _set_admin_overrides() -> None:
    app.dependency_overrides[get_current_admin] = lambda: CurrentUser(
        id=str(uuid4()), role="admin", email="admin@example.com"
    )
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()


def _clear_admin_overrides() -> None:
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_db_session, None)


def test_admin_locations_list_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/admin/locations")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_locations_list_forwards_paging_and_archived_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = [_admin_location()]

    async def fake_list_locations_for_admin(
        _session,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
    ):
        captured["include_archived"] = include_archived
        captured["limit"] = limit
        captured["offset"] = offset
        return expected

    monkeypatch.setattr(locations_service.repository, "list_locations_for_admin", fake_list_locations_for_admin)

    rows = await locations_service.list_locations_for_admin(
        AsyncMock(), include_archived=True, limit=11, offset=3
    )

    assert captured == {"include_archived": True, "limit": 11, "offset": 3}
    assert rows[0].slug == expected[0].slug


@pytest.mark.asyncio
async def test_admin_locations_require_existing_record_raises_for_missing(monkeypatch) -> None:
    monkeypatch.setattr(locations_service.repository, "get_location_for_admin", AsyncMock(return_value=None))
    with pytest.raises(NotFoundError):
        await locations_service.require_location_for_admin(AsyncMock(), UUID(int=0))


def test_admin_locations_detail_route_returns_admin_projection(monkeypatch) -> None:
    row = _admin_location()
    monkeypatch.setattr(
        locations_service.repository,
        "get_location_for_admin",
        AsyncMock(return_value=row),
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get(f"/api/v1/admin/locations/{row.id}")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(row.id)
    assert payload["slug"] == row.slug
    assert payload["metadata"] == row.metadata_
    assert payload["exact_latitude"] == row.exact_latitude


def test_admin_locations_list_route_includes_archived_rows_when_requested(monkeypatch) -> None:
    active = _admin_location(archived=False)
    archived = _admin_location(archived=True)

    async def fake_list_locations_for_admin(_session, *, include_archived: bool, limit: int, offset: int):
        if include_archived:
            return [archived, active]
        return [active]

    monkeypatch.setattr(
        locations_service.repository,
        "list_locations_for_admin",
        fake_list_locations_for_admin,
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get("/api/v1/admin/locations?include_archived=true&limit=50&offset=0")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(archived.id), str(active.id)]
    assert payload[0]["archived_at"] == archived.archived_at.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_admin_sessions_list_forwards_paging_and_archived_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = [_admin_session()]

    async def fake_list_sessions_for_admin(
        _session,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
    ):
        captured["include_archived"] = include_archived
        captured["limit"] = limit
        captured["offset"] = offset
        return expected

    monkeypatch.setattr(
        sessions_service.repository,
        "list_sessions_for_admin",
        fake_list_sessions_for_admin,
    )

    rows = await sessions_service.list_sessions_for_admin(
        AsyncMock(), include_archived=True, limit=12, offset=5
    )

    assert captured == {"include_archived": True, "limit": 12, "offset": 5}
    assert rows[0].slug == expected[0].slug


def test_admin_sessions_list_route_includes_archived_rows_when_requested(monkeypatch) -> None:
    active = _admin_session(archived=False)
    archived = _admin_session(archived=True)

    async def fake_list_sessions_for_admin(
        _session,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
    ):
        if include_archived:
            return [archived, active]
        return [active]

    monkeypatch.setattr(
        sessions_service.repository,
        "list_sessions_for_admin",
        fake_list_sessions_for_admin,
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get("/api/v1/admin/sessions?include_archived=true&limit=50&offset=0")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(archived.id), str(active.id)]


def test_admin_session_detail_route_returns_session_payload(monkeypatch) -> None:
    row = _admin_session()

    async def get_session_for_admin(_session, session_id):
        assert session_id == row.id
        return row

    monkeypatch.setattr(
        sessions_service.repository,
        "get_session_for_admin",
        get_session_for_admin,
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get(f"/api/v1/admin/sessions/{row.id}")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(row.id)
    assert payload["slug"] == row.slug
    assert payload["metadata"] == row.metadata_


@pytest.mark.asyncio
async def test_admin_collections_list_forwards_paging(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = [_admin_collection()]

    async def fake_list_collections_for_admin(_session, *, limit: int, offset: int):
        captured["limit"] = limit
        captured["offset"] = offset
        return expected

    monkeypatch.setattr(
        collections_service.repository,
        "list_collections_for_admin",
        fake_list_collections_for_admin,
    )

    rows = await collections_service.list_collections_for_admin(AsyncMock(), limit=13, offset=7)

    assert captured == {"limit": 13, "offset": 7}
    assert rows[0].slug == expected[0].slug


def test_admin_collections_list_route_returns_items(monkeypatch) -> None:
    row = _admin_collection()

    async def fake_list_collections_for_admin(_session, *, limit: int, offset: int):
        assert limit == 50
        assert offset == 0
        return [row]

    monkeypatch.setattr(
        collections_service.repository,
        "list_collections_for_admin",
        fake_list_collections_for_admin,
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get("/api/v1/admin/collections?limit=50&offset=0")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(row.id)]
    assert payload[0]["slug"] == row.slug


def test_admin_collection_detail_route_returns_collection_payload(monkeypatch) -> None:
    row = _admin_collection()

    async def get_collection(_session, collection_id):
        assert collection_id == row.id
        return row

    monkeypatch.setattr(
        collections_service.repository,
        "get_collection",
        get_collection,
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        response = client.get(f"/api/v1/admin/collections/{row.id}")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(row.id)
    assert payload["slug"] == row.slug
    assert payload["is_public"] == row.is_public


def test_admin_me_route_returns_typed_identity(monkeypatch) -> None:
    _set_admin_overrides()
    client = TestClient(app)

    try:
        response = client.get("/api/v1/admin/me")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["id"], str)
    assert payload["is_admin"] is True
    assert payload["role"] == "admin"


def test_admin_read_routes_set_no_store_headers(monkeypatch) -> None:
    row = _admin_location()
    _set_admin_overrides()
    monkeypatch.setattr(
        locations_service.repository,
        "list_locations_for_admin",
        AsyncMock(return_value=[row]),
    )

    client = TestClient(app)
    try:
        response = client.get("/api/v1/admin/locations")
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"


def test_admin_cookie_based_mutation_rejects_missing_or_untrusted_origin(monkeypatch) -> None:
    row = _admin_location()
    _set_admin_overrides()

    async def fake_create_location(*_args, **kwargs):
        return row

    monkeypatch.setattr(locations_service, "create_location", fake_create_location)

    client = TestClient(app)
    payload = {
        "slug": "location-cookie",
        "name": "Cookie Location",
        "description": None,
        "exact_latitude": 1.23,
        "exact_longitude": 4.56,
    }
    trusted_origin = get_settings().cors_origins[0]

    try:
        response_no_origin = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token"},
        )
        response_bad_origin = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token", "Origin": "https://evil.example.com"},
        )
        response_ok = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token", "Origin": trusted_origin},
        )
    finally:
        _clear_admin_overrides()

    assert response_no_origin.status_code == 403
    assert response_bad_origin.status_code == 403
    assert response_ok.status_code == 201
