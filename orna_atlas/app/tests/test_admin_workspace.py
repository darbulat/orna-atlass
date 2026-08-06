from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from orna_atlas.app.core.domain_errors import ForbiddenError, NotFoundError, ValidationError
from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.security import CurrentUser, get_current_admin
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.main import app
from orna_atlas.app.modules.admin import service as admin_service
from orna_atlas.app.modules.admin.context import build_admin_etag
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.collections.schemas import CollectionUpdate
from orna_atlas.app.modules.collections.schemas import CollectionCreate
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionUpdate
from orna_atlas.app.modules.users import service as users_service
from orna_atlas.app.modules.memberships import service as memberships_service
from orna_atlas.app.modules.memberships.schemas import MembershipUpdate
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.users.schemas import UserRoleUpdate
from orna_atlas.app.modules.media.schemas import MediaAssetCreate, RecordingSegmentBatchCreate
from orna_atlas.app.core.domain_types import MediaKind


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


@pytest.mark.asyncio
async def test_collection_link_only_update_invalidates_previous_etag(monkeypatch) -> None:
    collection = _admin_collection()
    original_etag = build_admin_etag(
        resource_id=collection.id,
        updated_at=collection.updated_at,
    )
    new_location_id = uuid4()
    update_calls = 0

    async def fake_update(_session, current, _data):
        nonlocal update_calls
        update_calls += 1
        current.updated_at = current.updated_at + timedelta(microseconds=1)
        return current

    monkeypatch.setattr(
        collections_service,
        "require_collection_for_update",
        AsyncMock(return_value=collection),
    )
    monkeypatch.setattr(
        collections_service.repository,
        "validate_location_ids",
        AsyncMock(),
    )
    monkeypatch.setattr(
        collections_service.repository,
        "update_collection",
        fake_update,
    )
    audit = AsyncMock()
    monkeypatch.setattr(collections_service, "add_audit_event", audit)
    db = AsyncMock()

    await collections_service.update_collection(
        db,
        collection.id,
        CollectionUpdate(location_ids=[new_location_id]),
        if_match=original_etag,
    )

    with pytest.raises(HTTPException) as exc_info:
        await collections_service.update_collection(
            db,
            collection.id,
            CollectionUpdate(location_ids=[]),
            if_match=original_etag,
        )

    assert exc_info.value.status_code == 412
    assert update_calls == 1
    assert audit.await_count == 1


def _admin_user(*, has_membership: bool = True, active: bool = True) -> SimpleNamespace:
    membership = None
    if has_membership:
        membership = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            status="active",
            plan="member",
            starts_at=None,
            expires_at=None,
            is_entitled=True,
        )
    return SimpleNamespace(
        id=uuid4(),
        email="member@example.com",
        role="member",
        is_active=active,
        created_at=datetime.now(UTC),
        membership=membership,
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


@pytest.mark.asyncio
async def test_admin_users_list_forwards_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}
    user = _admin_user()

    async def fake_list_for_admin(
        _session,
        *,
        email: str | None,
        role: str | None,
        is_active: bool | None,
        membership_status: str | None,
        limit: int,
        offset: int,
    ):
        captured["email"] = email
        captured["role"] = role
        captured["is_active"] = is_active
        captured["membership_status"] = membership_status
        captured["limit"] = limit
        captured["offset"] = offset
        return [user]

    monkeypatch.setattr(users_service.repository, "list_for_admin", fake_list_for_admin)
    monkeypatch.setattr(
        users_service.memberships_repository,
        "active_grant_user_ids",
        AsyncMock(return_value={user.id}),
    )

    rows = await users_service.list_admin(
        AsyncMock(),
        email="member",
        role="member",
        is_active=True,
        membership_status="active",
        limit=11,
        offset=3,
    )

    assert captured == {
        "email": "member",
        "role": "member",
        "is_active": True,
        "membership_status": "active",
        "limit": 11,
        "offset": 3,
    }
    assert rows[0].membership.status == "active"


@pytest.mark.asyncio
async def test_admin_projection_uses_active_grant_union_over_cancelled_membership(monkeypatch) -> None:
    user = _admin_user(has_membership=True)
    user.membership.status = "cancelled"
    monkeypatch.setattr(
        users_service.repository,
        "list_for_admin",
        AsyncMock(return_value=[user]),
    )
    monkeypatch.setattr(
        users_service.memberships_repository,
        "active_grant_user_ids",
        AsyncMock(return_value={user.id}),
    )

    rows = await users_service.list_admin(
        AsyncMock(),
        email=None,
        role=None,
        is_active=None,
        membership_status="active",
        limit=50,
        offset=0,
    )

    assert rows[0].membership.status == "active"
    assert rows[0].membership.is_entitled is True


def test_admin_users_routes_project_membership_or_absent(monkeypatch) -> None:
    row_with_membership = _admin_user(has_membership=True)
    row_without_membership = _admin_user(has_membership=False)

    async def fake_list_for_admin(
        _session,
        *,
        email: str | None,
        role: str | None,
        is_active: bool | None,
        membership_status: str | None,
        limit: int,
        offset: int,
    ):
        return [row_with_membership, row_without_membership]

    async def fake_get_for_admin(_session, _user_id):
        return row_with_membership

    monkeypatch.setattr(users_service.repository, "list_for_admin", fake_list_for_admin)
    monkeypatch.setattr(users_service.repository, "get_for_admin", fake_get_for_admin)
    monkeypatch.setattr(
        users_service.memberships_repository,
        "active_grant_user_ids",
        AsyncMock(return_value={row_with_membership.id}),
    )
    _set_admin_overrides()

    client = TestClient(app)
    try:
        list_response = client.get("/api/v1/admin/users?limit=50&offset=0")
        detail_response = client.get(f"/api/v1/admin/users/{row_with_membership.id}")
    finally:
        _clear_admin_overrides()

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload[0]["user"]["id"] == str(row_with_membership.id)
    assert payload[0]["membership"]["status"] == "active"
    assert payload[1]["membership"]["status"] == "inactive"
    assert payload[1]["membership"]["plan"] == "none"

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["user"]["id"] == str(row_with_membership.id)
    assert detail_payload["membership"]["status"] == "active"


@pytest.mark.asyncio
async def test_update_role_rejects_self_role_change(monkeypatch) -> None:
    actor_id = uuid4()
    user = SimpleNamespace(id=actor_id, is_active=True, role="admin")

    monkeypatch.setattr(users_service.repository, "get_by_id_for_update", AsyncMock(return_value=user))

    with pytest.raises(ForbiddenError, match="Admins cannot modify their own role"):
        await users_service.update_role(
            AsyncMock(),
            actor_id,
            UserRoleUpdate(role="member"),
            actor_user_id=actor_id,
        )


@pytest.mark.asyncio
async def test_update_role_rejects_last_active_admin_demotion(monkeypatch) -> None:
    actor_id = uuid4()
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, is_active=True, role="admin")

    monkeypatch.setattr(users_service.repository, "get_by_id_for_update", AsyncMock(return_value=user))
    monkeypatch.setattr(users_service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(users_service.repository, "count_active_admins", AsyncMock(return_value=1))
    monkeypatch.setattr(users_service.repository, "acquire_role_change_lock", AsyncMock())

    with pytest.raises(ForbiddenError, match="At least one active admin must remain"):
        await users_service.update_role(
            AsyncMock(),
            user_id,
            UserRoleUpdate(role="member"),
            actor_user_id=actor_id,
        )

    users_service.repository.acquire_role_change_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_role_allows_role_changes_on_safe_input(monkeypatch) -> None:
    actor_id = uuid4()
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, is_active=True, role="admin")
    db = AsyncMock()

    monkeypatch.setattr(users_service.repository, "get_by_id_for_update", AsyncMock(return_value=user))
    monkeypatch.setattr(users_service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(users_service.repository, "count_active_admins", AsyncMock(return_value=2))
    monkeypatch.setattr(users_service.repository, "acquire_role_change_lock", AsyncMock())
    monkeypatch.setattr(users_service.repository, "save", AsyncMock())
    monkeypatch.setattr(users_service, "add_audit_event", AsyncMock())

    saved = await users_service.update_role(
        db,
        user_id,
        UserRoleUpdate(role="editor"),
        actor_user_id=actor_id,
    )

    assert saved.role == "editor"
    users_service.repository.save.assert_awaited_once_with(db)
    users_service.add_audit_event.assert_awaited_once()
    users_service.repository.count_active_admins.assert_awaited_once_with(db)
    users_service.repository.acquire_role_change_lock.assert_awaited_once_with(db)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_role_uses_aggregate_user_membership_revision(monkeypatch) -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    user = SimpleNamespace(
        id=user_id,
        is_active=True,
        role="member",
        updated_at=now,
    )
    membership = SimpleNamespace(updated_at=now + timedelta(seconds=1))
    save = AsyncMock()
    monkeypatch.setattr(
        users_service.repository,
        "get_by_id_for_update",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        users_service.memberships_repository,
        "get_for_user",
        AsyncMock(return_value=membership),
    )
    monkeypatch.setattr(users_service.repository, "save", save)

    with pytest.raises(HTTPException) as exc_info:
        await users_service.update_role(
            AsyncMock(),
            user_id,
            UserRoleUpdate(role="editor"),
            actor_user_id=uuid4(),
            if_match=build_admin_etag(resource_id=user_id, updated_at=now),
        )

    assert exc_info.value.status_code == 412
    save.assert_not_awaited()


def test_admin_users_role_update_route_rejects_self_role_change() -> None:
    actor_id = uuid4()

    _set_admin_overrides()
    app.dependency_overrides[get_current_admin] = lambda: CurrentUser(
        id=str(actor_id), role="admin", email="admin@example.com"
    )

    client = TestClient(app)
    try:
        response = client.patch(
            f"/api/v1/admin/users/{actor_id}/role",
            json={"role": "member"},
            headers={"If-Match": 'W/"self"'},
        )
    finally:
        _clear_admin_overrides()

    assert response.status_code == 403
    assert response.json()["detail"] == "Admins cannot modify their own role"


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
        response_spoofed_local = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token", "X-Orna-Admin": "local"},
        )
        response_basic_spoof = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token", "Authorization": "Basic spoof"},
        )
        response_malformed_bearer = client.post(
            "/api/v1/admin/locations",
            json=payload,
            headers={"Cookie": "orna_access=token", "Authorization": "Bearer"},
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
    assert response_spoofed_local.status_code == 403
    assert response_basic_spoof.status_code == 403
    assert response_malformed_bearer.status_code == 403
    assert response_ok.status_code == 201


@pytest.mark.asyncio
async def test_audit_media_asset_registered_event_is_emitted(monkeypatch) -> None:
    actor_id = uuid4()
    db = AsyncMock()
    session_id = uuid4()
    asset_id = uuid4()
    recording = SimpleNamespace(id=session_id, media_assets=[], processing_status="ready")
    asset = SimpleNamespace(id=asset_id, session=recording, kind=MediaKind.SOURCE_AUDIO, processing_jobs=[])

    async def assert_audit_precedes_commit(*_args, **_kwargs):
        assert db.commit.await_count == 0

    audit = AsyncMock(side_effect=assert_audit_precedes_commit)

    async def fake_require_session_for_admin(_session, _session_id):
        assert _session_id == session_id
        return recording

    monkeypatch.setattr(media_service.sessions_service, "require_session_for_admin", fake_require_session_for_admin)
    monkeypatch.setattr(media_service.repository, "get_asset_by_storage_key", AsyncMock(return_value=None))
    monkeypatch.setattr(media_service.repository, "active_source_assets_for_update", AsyncMock(return_value=[]))
    monkeypatch.setattr(media_service.repository, "archive_assets", AsyncMock())
    monkeypatch.setattr(media_service.repository, "schedule_storage_cleanup", AsyncMock())
    monkeypatch.setattr(media_service.repository, "create_media_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(media_service, "add_audit_event", audit)

    data = MediaAssetCreate(
        kind=MediaKind.SOURCE_AUDIO,
        storage_key="sessions/recordings/a.wav",
        enqueue_processing=False,
    )
    await media_service.create_asset_for_session(
        db,
        session_id,
        data,
        actor_user_id=actor_id,
        actor_mode="token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    audit.assert_awaited_once()
    args = audit.await_args.kwargs
    assert args["event_type"] == "media.asset_registered"
    assert args["subject_type"] == "media_asset"
    assert args["subject_id"] == str(asset_id)
    assert args["actor_user_id"] == actor_id


@pytest.mark.asyncio
async def test_audit_media_asset_processing_retried_event_is_emitted(monkeypatch) -> None:
    actor_id = uuid4()
    db = AsyncMock()
    session_id = uuid4()
    asset_id = uuid4()
    recording = SimpleNamespace(id=session_id, media_assets=[])
    asset = SimpleNamespace(
        id=asset_id,
        session_id=session_id,
        session=recording,
        kind=MediaKind.SOURCE_AUDIO,
        is_active=True,
        archived_at=None,
        metadata_={},
        processing_status="failed",
    )

    async def assert_audit_precedes_commit(*_args, **_kwargs):
        assert db.commit.await_count == 0

    audit = AsyncMock(side_effect=assert_audit_precedes_commit)

    monkeypatch.setattr(media_service.repository, "get_asset_for_processing", AsyncMock(return_value=asset))
    monkeypatch.setattr(media_service.repository, "active_processing_job", AsyncMock(return_value=None))
    monkeypatch.setattr(media_service.repository, "create_processing_job", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(media_service, "_enqueue_or_mark_failed", AsyncMock())
    monkeypatch.setattr(media_service, "processing_status_for_session", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(media_service, "add_audit_event", audit)

    await media_service.retry_asset_processing(
        db,
        asset_id,
        actor_user_id=actor_id,
        actor_mode="token",
        ip_address="127.0.0.2",
        user_agent="pytest",
    )

    audit.assert_awaited_once()
    args = audit.await_args.kwargs
    assert args["event_type"] == "media.processing_retried"
    assert args["subject_type"] == "media_asset"
    assert args["subject_id"] == str(asset_id)
    assert args["actor_user_id"] == actor_id


@pytest.mark.asyncio
async def test_audit_media_asset_archived_event_is_emitted(monkeypatch) -> None:
    actor_id = uuid4()
    db = AsyncMock()
    asset_id = uuid4()
    session = SimpleNamespace(id=uuid4(), media_assets=[])
    asset = SimpleNamespace(id=asset_id, archived_at=None, session=session)
    audit = AsyncMock()

    monkeypatch.setattr(media_service, "require_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(media_service.repository, "archive_assets", AsyncMock())
    monkeypatch.setattr(media_service.repository, "schedule_storage_cleanup", AsyncMock())
    monkeypatch.setattr(media_service, "_clear_processing_caches", AsyncMock())
    monkeypatch.setattr(media_service, "add_audit_event", audit)

    await media_service.archive_asset(
        db,
        asset_id,
        actor_user_id=actor_id,
        actor_mode="token",
        ip_address="127.0.0.3",
        user_agent="pytest",
    )

    audit.assert_awaited_once()
    args = audit.await_args.kwargs
    assert args["event_type"] == "media.asset_archived"
    assert args["subject_type"] == "media_asset"
    assert args["subject_id"] == str(asset_id)
    assert args["actor_user_id"] == actor_id


@pytest.mark.asyncio
async def test_audit_hls_retry_is_committed_with_queued_transition(monkeypatch) -> None:
    actor_id = uuid4()
    db = AsyncMock()
    session_id = uuid4()
    recording = SimpleNamespace(id=session_id, processing_status="failed")
    job = SimpleNamespace(
        id=uuid4(),
        status="failed",
        error_code="queue_unavailable",
        error_message="down",
        finished_at=datetime.now(UTC),
        queue_job_id=None,
    )

    async def assert_audit_precedes_commit(*_args, **_kwargs):
        assert db.commit.await_count == 0

    audit = AsyncMock(side_effect=assert_audit_precedes_commit)
    monkeypatch.setattr(
        media_service.sessions_service,
        "require_session_for_admin",
        AsyncMock(return_value=recording),
    )
    monkeypatch.setattr(
        media_service.repository,
        "latest_hls_processing_job",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(media_service, "add_audit_event", audit)
    monkeypatch.setattr(media_service.asyncio, "to_thread", AsyncMock(return_value="queue-1"))

    result = await media_service.retry_hls_processing(
        db,
        session_id,
        actor_user_id=actor_id,
        actor_mode="token",
        ip_address="127.0.0.4",
        user_agent="pytest",
    )

    assert result is job
    assert db.commit.await_count == 2
    assert audit.await_args is not None
    args = audit.await_args.kwargs
    assert args["event_type"] == "media.processing_retried"
    assert args["subject_type"] == "recording_session"
    assert args["subject_id"] == str(session_id)


@pytest.mark.asyncio
async def test_audit_media_purge_request_is_committed_before_cleanup(monkeypatch) -> None:
    actor_id = uuid4()
    db = AsyncMock()
    asset_id = uuid4()
    recording = SimpleNamespace(id=uuid4(), media_assets=[])
    asset = SimpleNamespace(
        id=asset_id,
        archived_at=datetime.now(UTC),
        is_active=False,
        storage_key="sessions/recordings/archived.wav",
        session=recording,
    )
    storage = SimpleNamespace(is_configured=lambda: True)

    async def assert_audit_precedes_commit(*_args, **_kwargs):
        assert db.commit.await_count == 0

    audit = AsyncMock(side_effect=assert_audit_precedes_commit)
    monkeypatch.setattr(media_service, "require_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(
        media_service.repository,
        "schedule_storage_cleanup",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(media_service, "add_audit_event", audit)
    monkeypatch.setattr(media_service, "_clear_processing_caches", AsyncMock())

    await media_service.purge_archived_asset(
        db,
        asset_id,
        actor_user_id=actor_id,
        actor_mode="token",
        ip_address="127.0.0.5",
        user_agent="pytest",
    )

    db.commit.assert_awaited_once()
    assert audit.await_args is not None
    args = audit.await_args.kwargs
    assert args["event_type"] == "media.asset_purge_requested"
    assert args["subject_type"] == "media_asset"
    assert args["subject_id"] == str(asset_id)


@pytest.mark.asyncio
async def test_audit_filters_admin_service_forwards_query_args(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = []
    created_from = datetime(2026, 1, 1, tzinfo=UTC)
    created_to = datetime(2026, 1, 2, tzinfo=UTC)
    actor_id = uuid4()

    async def fake_list_audit_events(
        _session,
        *,
        event_type,
        actor_user_id,
        subject_type,
        subject_id,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
        offset: int,
    ) -> list[object]:
        captured["event_type"] = event_type
        captured["actor_user_id"] = actor_user_id
        captured["subject_type"] = subject_type
        captured["subject_id"] = subject_id
        captured["created_from"] = created_from
        captured["created_to"] = created_to
        captured["limit"] = limit
        captured["offset"] = offset
        return expected

    monkeypatch.setattr(admin_service.repository, "list_audit_events", fake_list_audit_events)

    result = await admin_service.list_audit_events(
        AsyncMock(),
        event_type="media.asset_registered",
        actor_user_id=actor_id,
        subject_type="media_asset",
        subject_id="asset-123",
        created_from=created_from,
        created_to=created_to,
        limit=11,
        offset=5,
    )

    assert result is expected
    assert captured == {
        "event_type": "media.asset_registered",
        "actor_user_id": actor_id,
        "subject_type": "media_asset",
        "subject_id": "asset-123",
        "created_from": created_from,
        "created_to": created_to,
        "limit": 11,
        "offset": 5,
    }


def test_admin_audit_route_forwards_only_supported_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_list_audit_events(_session, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(admin_service, "list_audit_events", fake_list_audit_events)
    _set_admin_overrides()
    client = TestClient(app)
    try:
        response = client.get(
            "/api/v1/admin/audit-events",
            params={
                "event_type": "location.updated",
                "subject_type": "location",
                "subject_id": "location-1",
                "limit": 25,
                "offset": 5,
            },
        )
    finally:
        _clear_admin_overrides()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert captured["event_type"] == "location.updated"
    assert captured["subject_type"] == "location"
    assert captured["subject_id"] == "location-1"
    assert "ip_address" not in captured
    assert "user_agent" not in captured


@pytest.mark.asyncio
async def test_audit_filters_admin_service_rejects_invalid_windows() -> None:
    with pytest.raises(ValidationError, match="created_from must be timezone-aware"):
        await admin_service.list_audit_events(AsyncMock(), created_from=datetime(2026, 1, 1))

    with pytest.raises(ValidationError, match="created_from must be before or equal created_to"):
        await admin_service.list_audit_events(
            AsyncMock(),
            created_from=datetime(2026, 1, 2, tzinfo=UTC),
            created_to=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_admin_list_filters_are_forwarded_to_repositories(monkeypatch) -> None:
    db = AsyncMock()
    location_row = _admin_location()
    session_row = _admin_session()
    collection_row = _admin_collection()

    location_list = AsyncMock(return_value=[location_row])
    session_list = AsyncMock(return_value=[session_row])
    collection_list = AsyncMock(return_value=[collection_row])
    monkeypatch.setattr(locations_service.repository, "list_locations_for_admin", location_list)
    monkeypatch.setattr(sessions_service.repository, "list_sessions_for_admin", session_list)
    monkeypatch.setattr(collections_service.repository, "list_collections_for_admin", collection_list)

    await locations_service.list_locations_for_admin(
        db,
        include_archived=True,
        q="taiga",
        coordinate_visibility="hidden",
        sensitivity_level="protected",
        limit=25,
        offset=5,
    )
    await sessions_service.list_sessions_for_admin(
        db,
        include_archived=True,
        q="dawn",
        location_id=session_row.location_id,
        publication_status="draft",
        processing_status="pending",
        access_level="members_only",
        limit=25,
        offset=5,
    )
    await collections_service.list_collections_for_admin(
        db,
        q="field",
        is_public=False,
        limit=25,
        offset=5,
    )

    location_list.assert_awaited_once_with(
        db,
        include_archived=True,
        q="taiga",
        coordinate_visibility="hidden",
        sensitivity_level="protected",
        limit=25,
        offset=5,
    )
    session_list.assert_awaited_once_with(
        db,
        include_archived=True,
        q="dawn",
        location_id=session_row.location_id,
        publication_status="draft",
        processing_status="pending",
        access_level="members_only",
        limit=25,
        offset=5,
    )
    collection_list.assert_awaited_once_with(
        db,
        q="field",
        is_public=False,
        limit=25,
        offset=5,
    )


def test_admin_location_detail_exposes_etag_and_update_requires_if_match(monkeypatch) -> None:
    row = _admin_location()
    monkeypatch.setattr(
        locations_service.repository,
        "get_location_for_admin",
        AsyncMock(return_value=row),
    )
    update = AsyncMock(return_value=row)
    monkeypatch.setattr(locations_service, "update_location", update)
    _set_admin_overrides()

    client = TestClient(app)
    try:
        detail = client.get(f"/api/v1/admin/locations/{row.id}")
        missing_precondition = client.patch(
            f"/api/v1/admin/locations/{row.id}",
            json={"name": "Updated name"},
        )
    finally:
        _clear_admin_overrides()

    assert detail.status_code == 200
    assert detail.headers["etag"].startswith('"')
    assert missing_precondition.status_code == 428
    assert missing_precondition.json()["detail"] == "If-Match required for this operation"
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_admin_revision_is_rejected_before_location_write(monkeypatch) -> None:
    row = _admin_location()
    persist = AsyncMock()
    monkeypatch.setattr(
        locations_service,
        "require_location_for_admin_for_update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(locations_service.repository, "update_location", persist)

    with pytest.raises(HTTPException) as exc_info:
        await locations_service.update_location(
            AsyncMock(),
            row.id,
            locations_service.LocationUpdate(name="Stale update"),
            if_match='"stale"',
        )

    assert exc_info.value.status_code == 412
    persist.assert_not_awaited()


def test_admin_account_detail_revisions_and_mutations_require_if_match(monkeypatch) -> None:
    row = _admin_user(has_membership=True)

    async def fake_get_for_admin(_session, _user_id):
        return row

    monkeypatch.setattr(users_service.repository, "get_for_admin", fake_get_for_admin)
    monkeypatch.setattr(
        users_service.memberships_repository,
        "active_grant_user_ids",
        AsyncMock(return_value={row.id}),
    )
    _set_admin_overrides()
    client = TestClient(app)
    try:
        detail = client.get(f"/api/v1/admin/users/{row.id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["revision"] == detail.headers["etag"]
        assert "membership_revision" not in payload

        role = client.patch(
            f"/api/v1/admin/users/{row.id}/role",
            json={"role": "editor"},
        )
        membership = client.put(
            f"/api/v1/admin/memberships/{row.id}",
            json={"status": "active", "plan": "member"},
        )
    finally:
        _clear_admin_overrides()

    assert role.status_code == 428
    assert membership.status_code == 428


def test_admin_openapi_documents_preconditions_literals_and_search_bounds() -> None:
    schema = app.openapi()

    def string_option(parameter: dict) -> dict:
        parameter_schema = parameter["schema"]
        return next(
            option
            for option in parameter_schema.get("anyOf", [parameter_schema])
            if option.get("type") == "string"
        )

    operations = [
        ("/api/v1/admin/locations/{location_id}", "patch"),
        ("/api/v1/admin/locations/{location_id}", "delete"),
        ("/api/v1/admin/sessions/{session_id}", "patch"),
        ("/api/v1/admin/sessions/{session_id}", "delete"),
        ("/api/v1/admin/collections/{collection_id}", "patch"),
        ("/api/v1/admin/users/{user_id}/role", "patch"),
        ("/api/v1/admin/memberships/{user_id}", "put"),
    ]
    for path, method in operations:
        operation = schema["paths"][path][method]
        if_match = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["in"] == "header" and parameter["name"].lower() == "if-match"
        )
        assert if_match["required"] is True
        assert {"412", "428"}.issubset(operation["responses"])
        for status_code in ("412", "428"):
            assert operation["responses"][status_code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/AdminErrorResponse"
            }

    for path, path_item in schema["paths"].items():
        if not path.startswith("/api/v1/admin/"):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status_code in ("401", "403"):
                assert operation["responses"][status_code]["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/AdminErrorResponse"
                }

    identity = schema["components"]["schemas"]["AdminIdentityRead"]
    assert identity["properties"]["mode"]["enum"] == ["token", "local"]
    for path in (
        "/api/v1/admin/locations",
        "/api/v1/admin/sessions",
        "/api/v1/admin/collections",
    ):
        q_parameter = next(
            parameter
            for parameter in schema["paths"][path]["get"]["parameters"]
            if parameter["name"] == "q"
        )
        assert string_option(q_parameter)["maxLength"] == 200
    email_parameter = next(
        parameter
        for parameter in schema["paths"]["/api/v1/admin/users"]["get"]["parameters"]
        if parameter["name"] == "email"
    )
    assert string_option(email_parameter)["maxLength"] == 200

    enum_parameters = {
        ("/api/v1/admin/locations", "coordinate_visibility"): "CoordinateVisibility",
        ("/api/v1/admin/locations", "sensitivity_level"): "SensitivityLevel",
        ("/api/v1/admin/sessions", "publication_status"): "PublicationStatus",
        ("/api/v1/admin/sessions", "processing_status"): "ProcessingStatus",
        ("/api/v1/admin/sessions", "access_level"): "SessionAccess",
        ("/api/v1/admin/users", "role"): "UserRole",
        ("/api/v1/admin/users", "membership_status"): "MembershipStatus",
    }
    for (path, name), schema_name in enum_parameters.items():
        parameter = next(
            item
            for item in schema["paths"][path]["get"]["parameters"]
            if item["name"] == name
        )
        options = parameter["schema"].get("anyOf", [parameter["schema"]])
        assert {"$ref": f"#/components/schemas/{schema_name}"} in options


def test_every_admin_operation_denies_non_admin_before_domain_work() -> None:
    async def deny_admin():
        raise HTTPException(status_code=403, detail="Admin role required")

    app.dependency_overrides[get_current_admin] = deny_admin
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    client = TestClient(app)
    try:
        for raw_path, path_item in app.openapi()["paths"].items():
            if not raw_path.startswith("/api/v1/admin"):
                continue
            path = raw_path
            for parameter in ("location_id", "session_id", "collection_id", "user_id", "asset_id"):
                path = path.replace(f"{{{parameter}}}", str(uuid4()))
            for method in path_item:
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                response = client.request(
                    method.upper(),
                    path,
                    json={} if method in {"post", "put", "patch"} else None,
                    headers={"If-Match": '"deny"'},
                )
                assert response.status_code == 403, (method, raw_path, response.text)
                assert response.headers.get("cache-control") == "no-store"
    finally:
        _clear_admin_overrides()


def test_admin_errors_and_empty_successes_are_no_store(monkeypatch) -> None:
    _clear_admin_overrides()
    client = TestClient(app)
    anonymous = client.get("/api/v1/admin/me")
    assert anonymous.status_code == 401
    assert anonymous.headers.get("cache-control") == "no-store"

    _set_admin_overrides()
    location_id = uuid4()
    delete_location = AsyncMock(return_value=None)
    monkeypatch.setattr(locations_service, "delete_location", delete_location)
    try:
        response = client.delete(
            f"/api/v1/admin/locations/{location_id}",
            headers={"If-Match": '"current"'},
        )
    finally:
        _clear_admin_overrides()

    assert response.status_code == 204
    assert response.headers.get("cache-control") == "no-store"
    delete_location.assert_awaited_once()


def _assert_audit_contract(call_args, *, event_type: str, subject_type: str, subject_id: UUID) -> None:
    payload = call_args.kwargs
    assert payload["event_type"] == event_type
    assert payload["subject_type"] == subject_type
    assert payload["subject_id"] == str(subject_id)
    assert payload["actor_user_id"] is not None
    assert payload["ip_address"] == "192.0.2.20"
    assert payload["user_agent"] == "admin-audit-test"
    assert isinstance(payload["metadata"].get("changed_fields"), list)
    assert "exact_latitude" not in payload["metadata"]
    assert "exact_longitude" not in payload["metadata"]


@pytest.mark.asyncio
async def test_location_audit_acceptance_contracts_are_atomic(monkeypatch) -> None:
    actor_id = uuid4()
    row = _admin_location()
    row.sessions = []
    db = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(locations_service.repository, "get_location_by_slug_for_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(locations_service.repository, "create_location", AsyncMock(return_value=row))
    monkeypatch.setattr(locations_service, "require_location_for_admin_for_update", AsyncMock(return_value=row))
    monkeypatch.setattr(locations_service.repository, "update_location", AsyncMock(return_value=row))
    monkeypatch.setattr(locations_service.repository, "archive_location", AsyncMock())
    monkeypatch.setattr(locations_service.media_repository, "archive_assets", AsyncMock())
    monkeypatch.setattr(locations_service.media_repository, "schedule_storage_cleanup", AsyncMock())
    monkeypatch.setattr(locations_service, "invalidate_atlas_cache", AsyncMock())
    monkeypatch.setattr(locations_service, "add_audit_event", audit)
    context = dict(actor_user_id=actor_id, actor_mode="token", ip_address="192.0.2.20", user_agent="admin-audit-test")

    await locations_service.create_location(
        db,
        LocationCreate(slug="audit-location", name="Audit location", exact_latitude=1, exact_longitude=2),
        **context,
    )
    await locations_service.update_location(db, row.id, LocationUpdate(name="Updated"), **context)
    await locations_service.delete_location(db, row.id, **context)

    assert db.commit.await_count == 3
    for call_args, event_type in zip(
        audit.await_args_list,
        ("location.created", "location.updated", "location.archived"),
        strict=True,
    ):
        _assert_audit_contract(call_args, event_type=event_type, subject_type="location", subject_id=row.id)


@pytest.mark.asyncio
async def test_session_and_collection_audit_acceptance_contracts(monkeypatch) -> None:
    actor_id = uuid4()
    session_row = _admin_session()
    collection_row = _admin_collection()
    db = AsyncMock()
    session_audit = AsyncMock()
    collection_audit = AsyncMock()
    context = dict(actor_user_id=actor_id, actor_mode="token", ip_address="192.0.2.20", user_agent="admin-audit-test")

    monkeypatch.setattr(sessions_service, "require_location_for_admin", AsyncMock())
    monkeypatch.setattr(sessions_service.repository, "get_session_by_slug_for_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions_service.repository, "create_session", AsyncMock(return_value=session_row))
    monkeypatch.setattr(sessions_service, "require_session_for_admin_for_update", AsyncMock(return_value=session_row))
    monkeypatch.setattr(sessions_service.repository, "update_session", AsyncMock(return_value=session_row))
    monkeypatch.setattr(sessions_service.repository, "archive_session", AsyncMock())
    monkeypatch.setattr(sessions_service.media_repository, "archive_assets", AsyncMock())
    monkeypatch.setattr(sessions_service.media_repository, "schedule_storage_cleanup", AsyncMock())
    monkeypatch.setattr(sessions_service, "invalidate_atlas_cache", AsyncMock())
    monkeypatch.setattr(sessions_service, "add_audit_event", session_audit)

    await sessions_service.create_session(
        db,
        SessionCreate(location_id=session_row.location_id, slug="audit-session", title="Audit session", recorded_at=datetime.now(UTC)),
        **context,
    )
    await sessions_service.update_session(db, session_row.id, SessionUpdate(title="Updated"), **context)
    await sessions_service.delete_session(db, session_row.id, **context)

    monkeypatch.setattr(collections_service.repository, "get_collection_by_slug_for_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(collections_service.repository, "validate_location_ids", AsyncMock())
    monkeypatch.setattr(collections_service.repository, "validate_session_ids", AsyncMock())
    monkeypatch.setattr(collections_service.repository, "create_collection", AsyncMock(return_value=collection_row))
    monkeypatch.setattr(collections_service, "require_collection_for_update", AsyncMock(return_value=collection_row))
    monkeypatch.setattr(collections_service.repository, "update_collection", AsyncMock(return_value=collection_row))
    monkeypatch.setattr(collections_service, "add_audit_event", collection_audit)

    await collections_service.create_collection(
        db,
        CollectionCreate(slug="audit-collection", title="Audit collection"),
        **context,
    )
    await collections_service.update_collection(db, collection_row.id, CollectionUpdate(title="Updated"), **context)

    for call_args, event_type in zip(
        session_audit.await_args_list,
        ("session.created", "session.updated", "session.archived"),
        strict=True,
    ):
        _assert_audit_contract(call_args, event_type=event_type, subject_type="recording_session", subject_id=session_row.id)
    for call_args, event_type in zip(
        collection_audit.await_args_list,
        ("collection.created", "collection.updated"),
        strict=True,
    ):
        _assert_audit_contract(call_args, event_type=event_type, subject_type="collection", subject_id=collection_row.id)


@pytest.mark.asyncio
async def test_segments_role_and_membership_audit_contracts(monkeypatch) -> None:
    actor_id = uuid4()
    session_id = uuid4()
    recording = SimpleNamespace(id=session_id, processing_status="pending")
    asset = SimpleNamespace(id=uuid4())
    segment = SimpleNamespace(id=uuid4())
    job = SimpleNamespace(id=uuid4(), queue_job_id=None)
    db = AsyncMock()
    media_audit = AsyncMock()
    context = dict(actor_user_id=actor_id, actor_mode="token", ip_address="192.0.2.20", user_agent="admin-audit-test")
    storage = SimpleNamespace(is_configured=lambda: True, object_exists=lambda _key: True)
    monkeypatch.setattr(media_service.sessions_service, "require_session_for_admin", AsyncMock(return_value=recording))
    monkeypatch.setattr(media_service.repository, "list_recording_segments", AsyncMock(return_value=[]))
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)
    monkeypatch.setattr(media_service.repository, "get_asset_by_storage_key", AsyncMock(return_value=None))
    monkeypatch.setattr(media_service.repository, "create_media_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(media_service.repository, "create_recording_segment", AsyncMock(return_value=segment))
    monkeypatch.setattr(media_service.repository, "create_hls_processing_job", AsyncMock(return_value=job))
    monkeypatch.setattr(media_service.asyncio, "to_thread", AsyncMock(side_effect=[True, "queue-1"]))
    monkeypatch.setattr(media_service, "add_audit_event", media_audit)

    await media_service.register_recording_segments(
        db,
        session_id,
        RecordingSegmentBatchCreate(segments=[{"sequence_number": 1, "storage_key": "sessions/audit/source.wav"}]),
        **context,
    )
    _assert_audit_contract(
        media_audit.await_args,
        event_type="media.segments_registered",
        subject_type="recording_session",
        subject_id=session_id,
    )

    user_id = uuid4()
    user = SimpleNamespace(id=user_id, role="member", is_active=True, updated_at=datetime.now(UTC))
    role_audit = AsyncMock()
    monkeypatch.setattr(users_service.repository, "get_by_id_for_update", AsyncMock(return_value=user))
    monkeypatch.setattr(users_service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(users_service.repository, "save", AsyncMock())
    monkeypatch.setattr(users_service, "add_audit_event", role_audit)
    await users_service.update_role(db, user_id, UserRoleUpdate(role="editor"), **context)
    _assert_audit_contract(role_audit.await_args, event_type="user.role_updated", subject_type="user", subject_id=user_id)

    membership = SimpleNamespace(id=uuid4(), updated_at=datetime.now(UTC))
    membership_audit = AsyncMock()
    monkeypatch.setattr(memberships_service, "require_user_for_update", AsyncMock(return_value=user))
    monkeypatch.setattr(memberships_service.repository, "get_for_user", AsyncMock(return_value=membership))
    monkeypatch.setattr(memberships_service.repository, "upsert", AsyncMock(return_value=membership))
    monkeypatch.setattr(memberships_service.repository, "revoke_grant", AsyncMock())
    monkeypatch.setattr(memberships_service, "add_audit_event", membership_audit)
    await memberships_service.update_membership(
        db,
        user_id,
        MembershipUpdate(
            status="cancelled",
            plan="member",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
        **context,
    )
    _assert_audit_contract(
        membership_audit.await_args,
        event_type="membership.updated",
        subject_type="membership",
        subject_id=membership.id,
    )
    membership_audit_call = membership_audit.await_args
    assert membership_audit_call is not None
    assert set(membership_audit_call.kwargs["metadata"]["changed_fields"]) == {
        "status",
        "plan",
        "expires_at",
    }


def test_unhandled_admin_error_is_not_cacheable() -> None:
    @app.get("/api/v1/admin/_test-unhandled-error", include_in_schema=False)
    async def raise_unhandled_admin_error() -> None:
        raise RuntimeError("admin test failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/admin/_test-unhandled-error")

    assert response.status_code == 500
    assert response.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_membership_audit_reports_every_effectively_overwritten_field(monkeypatch) -> None:
    db = AsyncMock()
    user_id = uuid4()
    current = SimpleNamespace(
        id=uuid4(),
        status="active",
        plan="premium",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        updated_at=datetime.now(UTC),
    )
    persisted = SimpleNamespace(id=current.id)
    audit = AsyncMock()
    monkeypatch.setattr(
        memberships_service,
        "require_user_for_update",
        AsyncMock(return_value=SimpleNamespace(id=user_id, updated_at=datetime.now(UTC))),
    )
    monkeypatch.setattr(
        memberships_service.repository,
        "get_for_user",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        memberships_service.repository,
        "upsert",
        AsyncMock(return_value=persisted),
    )
    monkeypatch.setattr(memberships_service.repository, "revoke_grant", AsyncMock())
    monkeypatch.setattr(memberships_service, "add_audit_event", audit)

    await memberships_service.update_membership(
        db,
        user_id,
        MembershipUpdate(status="cancelled"),
        actor_user_id=uuid4(),
    )

    assert audit.await_args is not None
    assert audit.await_args.kwargs["metadata"]["changed_fields"] == [
        "expires_at",
        "plan",
        "status",
    ]


@pytest.mark.asyncio
async def test_audit_insert_failure_prevents_domain_commit(monkeypatch) -> None:
    row = _admin_location()
    db = AsyncMock()
    monkeypatch.setattr(locations_service.repository, "get_location_by_slug_for_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(locations_service.repository, "create_location", AsyncMock(return_value=row))
    monkeypatch.setattr(locations_service, "add_audit_event", AsyncMock(side_effect=RuntimeError("audit unavailable")))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await locations_service.create_location(
            db,
            LocationCreate(slug="atomicity", name="Atomicity", exact_latitude=1, exact_longitude=2),
            actor_user_id=uuid4(),
        )

    db.commit.assert_not_awaited()
