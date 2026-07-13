from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.core.rate_limit import rate_limit
from orna_atlas.app.core.security import (
    CurrentUser,
    _resolve_active_user,
    create_access_token,
    decode_access_token,
    get_current_admin,
    hash_password,
    verify_password,
)
from orna_atlas.app.main import app
from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.users import service as users_service


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)


def test_access_token_round_trip_and_tamper_rejection() -> None:
    user_id = uuid4()
    token, expires_at = create_access_token(user_id, "member", "member@example.com")

    current = decode_access_token(token)

    assert current.id == str(user_id)
    assert current.role == "member"
    assert expires_at > datetime.now(UTC)
    with pytest.raises(HTTPException) as error:
        decode_access_token(f"{token[:-1]}x")
    assert error.value.status_code == 401


def test_production_rejects_insecure_auth_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(APP_ENVIRONMENT="production")


def test_production_accepts_hardened_auth_configuration() -> None:
    settings = Settings(
        APP_ENVIRONMENT="production",
        AUTH_SECRET_KEY="x" * 32,
        LOCAL_ADMIN_ENABLED=False,
        AUTH_COOKIE_SECURE=True,
    )

    assert settings.environment == "production"


def test_local_admin_is_disabled_by_default_and_rejected_in_staging() -> None:
    assert not Settings(_env_file=None).local_admin_enabled
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            APP_ENVIRONMENT="staging",
            LOCAL_ADMIN_ENABLED=True,
        )


@pytest.mark.asyncio
async def test_local_admin_header_is_disabled_when_setting_is_off(monkeypatch) -> None:
    settings = Settings(LOCAL_ADMIN_ENABLED=False)
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as error:
        await get_current_admin(claims=None, x_orna_admin="local", session=AsyncMock())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_database_role_overrides_stale_token_claim(monkeypatch) -> None:
    user_id = uuid4()
    claims = CurrentUser(id=str(user_id), role="admin", email="member@example.com")
    stored = SimpleNamespace(
        id=user_id, role="member", email="member@example.com", is_active=True
    )
    lookup = AsyncMock(return_value=stored)
    monkeypatch.setattr("orna_atlas.app.modules.users.repository.get_by_id", lookup)

    current = await _resolve_active_user(AsyncMock(), claims)

    assert current.role == "member"
    lookup.assert_awaited_once()


def test_membership_entitlement_honors_status_and_expiry() -> None:
    active = Membership(status="active", expires_at=datetime.now(UTC) + timedelta(minutes=1))
    expired = Membership(status="active", expires_at=datetime.now(UTC) - timedelta(minutes=1))
    cancelled = Membership(status="cancelled", expires_at=None)

    assert active.is_entitled
    assert not expired.is_entitled
    assert not cancelled.is_entitled


@pytest.mark.asyncio
async def test_members_only_playback_rejects_anonymous_user() -> None:
    recording = SimpleNamespace(id=uuid4(), access_level="members_only")

    with pytest.raises(HTTPException) as error:
        await sessions_service.authorize_playback_grant(AsyncMock(), recording, None)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_members_only_playback_rejects_inactive_member(monkeypatch) -> None:
    recording = SimpleNamespace(id=uuid4(), access_level="members_only")
    user = CurrentUser(id=str(uuid4()), role="member", email="member@example.com")
    monkeypatch.setattr(sessions_service, "has_playback_entitlement", AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as error:
        await sessions_service.authorize_playback_grant(AsyncMock(), recording, user)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_entitled_playback_creates_audit_event(monkeypatch) -> None:
    recording = SimpleNamespace(id=uuid4(), access_level="members_only")
    user = CurrentUser(id=str(uuid4()), role="member", email="member@example.com")
    grant = SimpleNamespace(session_id=recording.id)
    db = AsyncMock()
    entitlement = AsyncMock(return_value=True)
    audit = AsyncMock()
    monkeypatch.setattr(sessions_service, "has_playback_entitlement", entitlement)
    monkeypatch.setattr(sessions_service, "create_playback_grant", lambda _: grant)
    monkeypatch.setattr(sessions_service, "add_audit_event", audit)

    result = await sessions_service.authorize_playback_grant(db, recording, user)

    assert result is grant
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["event_type"] == "playback.grant_created"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_entitled_member_can_list_members_only_sessions(monkeypatch) -> None:
    user = CurrentUser(id=str(uuid4()), role="member", email="member@example.com")
    entitlement = AsyncMock(return_value=True)
    list_sessions = AsyncMock(return_value=[])
    monkeypatch.setattr(sessions_service, "has_playback_entitlement", entitlement)
    monkeypatch.setattr(sessions_service.repository, "list_sessions", list_sessions)

    await sessions_service.list_visible_sessions(AsyncMock(), user)

    assert list_sessions.await_args.kwargs["access_levels"] == ("public", "members_only")


@pytest.mark.asyncio
async def test_non_entitled_member_cannot_resolve_members_only_session(monkeypatch) -> None:
    user = CurrentUser(id=str(uuid4()), role="member", email="member@example.com")
    entitlement = AsyncMock(return_value=False)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(sessions_service, "has_playback_entitlement", entitlement)
    monkeypatch.setattr(sessions_service.repository, "get_visible_session_by_slug", lookup)

    with pytest.raises(HTTPException) as error:
        await sessions_service.require_visible_session(AsyncMock(), "protected-session", user)

    assert error.value.status_code == 404
    assert lookup.await_args.kwargs["access_levels"] == ("public",)


def test_playback_grant_fails_closed_without_ready_rendition() -> None:
    recording = SimpleNamespace(id=uuid4(), media_assets=[])

    with pytest.raises(HTTPException) as error:
        sessions_service.create_playback_grant(recording)
    assert error.value.status_code == 409


class FakeRedis:
    def __init__(self) -> None:
        self.count = 0
        self.closed = False
        self.keys: list[str] = []

    async def incr(self, key: str) -> int:
        self.keys.append(key)
        self.count += 1
        return self.count

    async def expire(self, _key: str, _seconds: int) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_rate_limit_rejects_requests_over_limit(monkeypatch) -> None:
    client = FakeRedis()
    dependency = rate_limit("test", lambda: 1)
    monkeypatch.setattr("orna_atlas.app.core.rate_limit.get_redis_client", lambda: client)
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"), headers={}, state=SimpleNamespace()
    )

    await dependency(request)
    with pytest.raises(HTTPException) as error:
        await dependency(request)

    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": str(get_settings().rate_limit_window_seconds)}
    assert client.closed


@pytest.mark.asyncio
async def test_auth_rate_limit_ignores_untrusted_authorization_header(monkeypatch) -> None:
    client = FakeRedis()
    dependency = rate_limit("auth-test", lambda: 10)
    monkeypatch.setattr("orna_atlas.app.core.rate_limit.get_redis_client", lambda: client)
    first = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"authorization": "Bearer attacker-value-one"},
    )
    second = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"authorization": "Bearer attacker-value-two"},
    )

    await dependency(first)
    await dependency(second)

    assert client.keys[0] == client.keys[1]


@pytest.mark.asyncio
async def test_first_admin_bootstrap_is_one_time_and_audited(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(), email="owner@example.com", role="member", is_active=True
    )
    db = AsyncMock()
    lock = AsyncMock()
    get_admin = AsyncMock(return_value=None)
    get_user = AsyncMock(return_value=user)
    audit = AsyncMock()
    monkeypatch.setattr(users_service.repository, "acquire_admin_bootstrap_lock", lock)
    monkeypatch.setattr(users_service.repository, "get_admin", get_admin)
    monkeypatch.setattr(users_service.repository, "get_by_email", get_user)
    monkeypatch.setattr(users_service.repository, "save", AsyncMock())
    monkeypatch.setattr(users_service, "add_audit_event", audit)

    result = await users_service.bootstrap_first_admin(db, "owner@example.com")

    assert result is user
    assert user.role == "admin"
    lock.assert_awaited_once_with(db)
    assert audit.await_args.kwargs["event_type"] == "user.admin_bootstrapped"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_admin_bootstrap_refuses_when_admin_exists(monkeypatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        users_service.repository, "acquire_admin_bootstrap_lock", AsyncMock()
    )
    monkeypatch.setattr(
        users_service.repository,
        "get_admin",
        AsyncMock(return_value=SimpleNamespace(role="admin")),
    )

    with pytest.raises(ValueError, match="already exists"):
        await users_service.bootstrap_first_admin(db, "owner@example.com")

    db.commit.assert_not_awaited()


def test_sprint8_routes_and_security_contract_are_documented() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/logout" in schema["paths"]
    assert "/api/v1/auth/refresh" in schema["paths"]
    assert "/api/v1/users/me" in schema["paths"]
    assert "/api/v1/memberships/me" in schema["paths"]
    assert "/api/v1/admin/users/{user_id}/role" in schema["paths"]
    assert "/api/v1/admin/memberships/{user_id}" in schema["paths"]
    assert "/api/v1/admin/audit-events" in schema["paths"]
