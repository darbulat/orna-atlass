from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from orna_atlas.app.core.rate_limit import rate_limit
from orna_atlas.app.core.security import (
    CurrentUser,
    _resolve_active_user,
    create_access_token,
    decode_access_token,
    get_current_admin,
    hash_password,
    public_jwks,
    verify_password,
)
from orna_atlas.app import main as main_module
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


def _rsa_private_key_and_pem() -> tuple[rsa.RSAPrivateKey, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return private_key, private_pem


def _rsa_jwk(private_key: rsa.RSAPrivateKey, kid: str, *, private: bool) -> dict[str, object]:
    key = private_key if private else private_key.public_key()
    payload = json.loads(RSAAlgorithm.to_jwk(key))
    payload.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return payload


def test_rs256_jwks_prefers_current_key_sanitizes_private_config_and_keeps_old_key(
    monkeypatch,
) -> None:
    current_private_key, current_private_pem = _rsa_private_key_and_pem()
    replacement_private_key, _ = _rsa_private_key_and_pem()
    old_private_key, _ = _rsa_private_key_and_pem()
    replacement = _rsa_jwk(replacement_private_key, "current", private=True)
    replacement["k"] = "symmetric-material-must-not-leak"
    old_public = _rsa_jwk(old_private_key, "old-2025", private=False)
    settings = Settings(
        _env_file=None,
        AUTH_SIGNING_ALGORITHM="RS256",
        AUTH_KEY_ID="current",
        AUTH_PRIVATE_KEY=current_private_pem,
        AUTH_JWKS_JSON=json.dumps({"keys": [replacement, old_public]}),
    )
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    token, _ = create_access_token(uuid4(), "member", "member@example.com")
    current = decode_access_token(token)
    jwks = public_jwks()

    assert current.email == "member@example.com"
    assert [key["kid"] for key in jwks["keys"]] == ["current", "old-2025"]
    expected_current = _rsa_jwk(current_private_key, "current", private=False)
    assert jwks["keys"][0]["n"] == expected_current["n"]
    assert jwks["keys"][0]["n"] != replacement["n"]
    assert jwks["keys"][1]["n"] == old_public["n"]
    private_fields = {"d", "p", "q", "dp", "dq", "qi", "oth", "k"}
    assert all(private_fields.isdisjoint(key) for key in jwks["keys"])


def test_hs256_never_publishes_configured_symmetric_material(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        AUTH_SIGNING_ALGORITHM="HS256",
        AUTH_SECRET_KEY="do-not-publish-this-secret",
        AUTH_JWKS_JSON=json.dumps(
            {"keys": [{"kty": "oct", "kid": "symmetric", "k": "also-secret"}]}
        ),
    )
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    assert public_jwks() == {"keys": []}


@pytest.mark.parametrize(
    ("configured", "expected_message"),
    [
        ("not-json", "must contain valid JSON"),
        (json.dumps({"keys": {}}), "keys list"),
        (
            json.dumps({"keys": [{"kty": "oct", "kid": "symmetric", "k": "secret"}]}),
            "must be an RSA key",
        ),
        (
            json.dumps({"keys": [{"kty": "RSA", "kid": "broken", "n": "invalid"}]}),
            ".e must be a non-empty string",
        ),
    ],
)
def test_rs256_rejects_malformed_or_non_rsa_jwks_config(
    monkeypatch, configured: str, expected_message: str
) -> None:
    _, private_pem = _rsa_private_key_and_pem()
    settings = Settings(
        _env_file=None,
        AUTH_SIGNING_ALGORITHM="RS256",
        AUTH_PRIVATE_KEY=private_pem,
        AUTH_JWKS_JSON=configured,
    )
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    with pytest.raises(ValueError, match=expected_message):
        public_jwks()


def test_rs256_rejects_duplicate_configured_key_ids(monkeypatch) -> None:
    _, current_private_pem = _rsa_private_key_and_pem()
    first_old_key, _ = _rsa_private_key_and_pem()
    second_old_key, _ = _rsa_private_key_and_pem()
    configured = {
        "keys": [
            _rsa_jwk(first_old_key, "duplicate", private=False),
            _rsa_jwk(second_old_key, "duplicate", private=False),
        ]
    }
    settings = Settings(
        _env_file=None,
        AUTH_SIGNING_ALGORITHM="RS256",
        AUTH_PRIVATE_KEY=current_private_pem,
        AUTH_JWKS_JSON=json.dumps(configured),
    )
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    with pytest.raises(ValueError, match="duplicate kid 'duplicate'"):
        public_jwks()


def test_rs256_app_startup_rejects_malformed_rotation_config(monkeypatch) -> None:
    _, private_pem = _rsa_private_key_and_pem()
    settings = Settings(
        _env_file=None,
        AUTH_SIGNING_ALGORITHM="RS256",
        AUTH_PRIVATE_KEY=private_pem,
        AUTH_JWKS_JSON="not-json",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr("orna_atlas.app.core.security.get_settings", lambda: settings)

    with pytest.raises(ValueError, match="must contain valid JSON"):
        main_module.create_app()


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
    recording = SimpleNamespace(
        id=uuid4(),
        access_level="members_only",
        location=SimpleNamespace(coordinate_visibility="exact_public"),
    )

    with pytest.raises(AuthenticationError) as error:
        await sessions_service.authorize_playback_grant(AsyncMock(), recording, None)
    assert error.value.detail == "Membership required"


@pytest.mark.asyncio
async def test_members_only_playback_rejects_inactive_member(monkeypatch) -> None:
    recording = SimpleNamespace(
        id=uuid4(),
        access_level="members_only",
        location=SimpleNamespace(coordinate_visibility="exact_public"),
    )
    user = CurrentUser(id=str(uuid4()), role="member", email="member@example.com")
    monkeypatch.setattr(sessions_service, "has_playback_entitlement", AsyncMock(return_value=False))

    with pytest.raises(ForbiddenError) as error:
        await sessions_service.authorize_playback_grant(AsyncMock(), recording, user)
    assert error.value.detail == "Active membership required"


@pytest.mark.asyncio
async def test_entitled_playback_creates_audit_event(monkeypatch) -> None:
    recording = SimpleNamespace(
        id=uuid4(),
        access_level="members_only",
        location=SimpleNamespace(coordinate_visibility="exact_public"),
    )
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

    with pytest.raises(NotFoundError) as error:
        await sessions_service.require_visible_session(AsyncMock(), "protected-session", user)

    assert error.value.detail == "Session not found"
    assert lookup.await_args.kwargs["access_levels"] == ("public",)


def test_playback_grant_fails_closed_without_ready_rendition() -> None:
    recording = SimpleNamespace(id=uuid4(), media_assets=[])

    with pytest.raises(ConflictError) as error:
        sessions_service.create_playback_grant(recording)
    assert error.value.detail == "Playable rendition is not ready"


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
