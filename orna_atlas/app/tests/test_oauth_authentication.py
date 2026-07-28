import asyncio
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.requests import Request
from starlette.responses import Response

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ServiceUnavailableError,
)
from orna_atlas.app.core.security import CurrentUser
from orna_atlas.app.main import app
from orna_atlas.app.modules.auth import oauth, router as auth_router, service

_TEST_APPLE_KEY = ec.generate_private_key(ec.SECP256R1()).private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()


@pytest.fixture(autouse=True)
def clear_oauth_jwks_cache() -> None:
    oauth._clear_jwks_cache()


def oauth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "OAUTH_CALLBACK_BASE_URL": "https://api.example.com/api/v1/auth/oauth",
        "OAUTH_FRONTEND_URL": "https://atlas.example.com/membership",
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
        "APPLE_CLIENT_ID": "com.example.web",
        "APPLE_TEAM_ID": "TEAM123456",
        "APPLE_KEY_ID": "KEY123456",
        "APPLE_PRIVATE_KEY": _TEST_APPLE_KEY,
        "FACEBOOK_CLIENT_ID": "facebook-client",
        "FACEBOOK_CLIENT_SECRET": "facebook-secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_oauth_authorization_uses_opaque_state_nonce_and_pkce() -> None:
    authorization = oauth.create_authorization("google", oauth_settings())
    query = parse_qs(urlparse(authorization.url).query)

    assert query["client_id"] == ["google-client"]
    assert query["redirect_uri"] == [
        "https://api.example.com/api/v1/auth/oauth/google/callback"
    ]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] == [authorization.nonce]
    assert query["state"] == [authorization.state]
    assert authorization.code_verifier not in authorization.url
    assert authorization.code_verifier not in authorization.state
    assert authorization.nonce not in authorization.state
    with pytest.raises(jwt.DecodeError):
        jwt.decode(authorization.state, options={"verify_signature": False})

    apple_query = parse_qs(
        urlparse(oauth.create_authorization("apple", oauth_settings()).url).query
    )
    assert apple_query["response_mode"] == ["form_post"]


def test_oauth_state_normalizes_unsafe_return_path() -> None:
    authorization = oauth.create_authorization(
        "google", oauth_settings(), return_to="//evil.example"
    )
    assert authorization.return_to == "/membership"


def _signed_id_token(
    *,
    issuer: str,
    audience: str | list[str],
    nonce: str,
    email_verified: object = True,
    authorized_party: str | None = None,
):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": "provider-user-123",
        "email": "Listener@Example.com",
        "email_verified": email_verified,
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    if authorized_party is not None:
        claims["azp"] = authorized_party
    token = jwt.encode(
        claims,
        key,
        algorithm="RS256",
        headers={"kid": "provider-key"},
    )
    public_jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public_jwk.update({"kid": "provider-key", "alg": "RS256", "use": "sig"})
    return token, public_jwk


@pytest.mark.asyncio
async def test_google_identity_requires_verified_email_and_matching_nonce(monkeypatch) -> None:
    token, jwk = _signed_id_token(
        issuer="https://accounts.google.com",
        audience="google-client",
        nonce="expected-nonce",
    )
    monkeypatch.setattr(oauth, "fetch_json", AsyncMock(return_value={"keys": [jwk]}))

    identity = await oauth.verify_google_id_token(
        token,
        nonce="expected-nonce",
        settings=oauth_settings(),
    )

    assert identity.provider == "google"
    assert identity.subject == "provider-user-123"
    assert identity.email == "listener@example.com"
    assert identity.email_verified is True

    with pytest.raises(AuthenticationError, match="identity token"):
        await oauth.verify_google_id_token(
            token,
            nonce="different-nonce",
            settings=oauth_settings(),
        )


@pytest.mark.asyncio
async def test_oidc_multi_audience_requires_matching_authorized_party(monkeypatch) -> None:
    for authorized_party in (None, "other-client"):
        oauth._clear_jwks_cache()
        token, jwk = _signed_id_token(
            issuer="https://accounts.google.com",
            audience=["google-client", "other-client"],
            nonce="expected-nonce",
            authorized_party=authorized_party,
        )
        monkeypatch.setattr(oauth, "fetch_json", AsyncMock(return_value={"keys": [jwk]}))
        with pytest.raises(AuthenticationError, match="identity token"):
            await oauth.verify_google_id_token(
                token, nonce="expected-nonce", settings=oauth_settings()
            )

    oauth._clear_jwks_cache()
    token, jwk = _signed_id_token(
        issuer="https://accounts.google.com",
        audience=["google-client", "other-client"],
        nonce="expected-nonce",
        authorized_party="google-client",
    )
    monkeypatch.setattr(oauth, "fetch_json", AsyncMock(return_value={"keys": [jwk]}))
    identity = await oauth.verify_google_id_token(
        token, nonce="expected-nonce", settings=oauth_settings()
    )
    assert identity.subject == "provider-user-123"


@pytest.mark.asyncio
async def test_oidc_jwks_cache_hits_and_refreshes_once_for_key_rotation(monkeypatch) -> None:
    first_token, first_jwk = _signed_id_token(
        issuer="https://accounts.google.com",
        audience="google-client",
        nonce="first-nonce",
    )
    rotated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    second_token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "google-client",
            "sub": "rotated-subject",
            "email": "rotated@example.com",
            "email_verified": True,
            "nonce": "second-nonce",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        rotated_key,
        algorithm="RS256",
        headers={"kid": "rotated-key"},
    )
    second_jwk = json.loads(RSAAlgorithm.to_jwk(rotated_key.public_key()))
    second_jwk.update({"kid": "rotated-key", "alg": "RS256", "use": "sig"})
    provider_fetch = AsyncMock(
        side_effect=[{"keys": [first_jwk]}, {"keys": [second_jwk]}]
    )
    monkeypatch.setattr(oauth, "fetch_json", provider_fetch)

    first = await oauth.verify_google_id_token(
        first_token, nonce="first-nonce", settings=oauth_settings()
    )
    cached = await oauth.verify_google_id_token(
        first_token, nonce="first-nonce", settings=oauth_settings()
    )
    rotated = await oauth.verify_google_id_token(
        second_token, nonce="second-nonce", settings=oauth_settings()
    )

    assert first.subject == cached.subject == "provider-user-123"
    assert rotated.subject == "rotated-subject"
    assert provider_fetch.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_unknown_key_refresh_is_deduplicated(monkeypatch) -> None:
    jwks_url = "https://issuer.example/jwks"
    stale = {"keys": [{"kid": "old-key"}]}
    oauth._jwks_cache[jwks_url] = (
        oauth.time.monotonic() + oauth.JWKS_CACHE_TTL_SECONDS,
        stale,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch_rotated_keys(url: str) -> dict[str, object]:
        assert url == jwks_url
        started.set()
        await release.wait()
        return {"keys": [{"kid": "rotated-key"}]}

    provider_fetch = AsyncMock(side_effect=fetch_rotated_keys)
    monkeypatch.setattr(oauth, "fetch_json", provider_fetch)
    refreshes = [
        asyncio.create_task(
            oauth._get_jwks(
                jwks_url,
                force_refresh=True,
                stale_payload=stale,
            )
        )
        for _ in range(2)
    ]
    await started.wait()
    release.set()

    first, second = await asyncio.gather(*refreshes)

    assert first == second == {"keys": [{"kid": "rotated-key"}]}
    assert provider_fetch.await_count == 1


@pytest.mark.asyncio
async def test_oidc_jwks_outage_fails_closed_as_unavailable(monkeypatch) -> None:
    token, _ = _signed_id_token(
        issuer="https://accounts.google.com",
        audience="google-client",
        nonce="expected-nonce",
    )
    monkeypatch.setattr(
        oauth,
        "fetch_json",
        AsyncMock(side_effect=ServiceUnavailableError("provider unavailable")),
    )

    with pytest.raises(ServiceUnavailableError, match="provider unavailable"):
        await oauth.verify_google_id_token(
            token, nonce="expected-nonce", settings=oauth_settings()
        )


@pytest.mark.asyncio
async def test_social_login_refuses_implicit_link_to_existing_email(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="listener@example.com",
        role="member",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db = AsyncMock()
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )
    monkeypatch.setattr(service.repository, "get_oauth_identity", AsyncMock(return_value=None))
    monkeypatch.setattr(service.users_repository, "get_by_email", AsyncMock(return_value=user))
    create_identity = AsyncMock()
    monkeypatch.setattr(service.repository, "create_oauth_identity", create_identity)

    with pytest.raises(service.OAuthLinkRequired) as exc_info:
        await service.authenticate_oauth_identity(db, identity)

    assert exc_info.value.target_user_id == user.id
    assert exc_info.value.identity == identity
    create_identity.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reauthenticated_user_explicitly_links_oauth_identity(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="listener@example.com",
        role="member",
        is_active=True,
    )
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user.id,
        return_to="/library",
        reauthenticated_user_id=user.id,
    )
    session = AsyncMock()
    monkeypatch.setattr(
        service.users_repository,
        "get_by_id_for_update",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(service.repository, "get_oauth_identity", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity_for_user_provider",
        AsyncMock(return_value=None),
        raising=False,
    )
    create_identity = AsyncMock()
    monkeypatch.setattr(service.repository, "create_oauth_identity", create_identity)
    audit = AsyncMock()
    monkeypatch.setattr(service, "add_audit_event", audit)

    await service.link_oauth_identity(session, current_user_id=user.id, intent=intent)

    create_identity.assert_awaited_once_with(
        session,
        user_id=user.id,
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
    )
    audit.assert_awaited_once_with(
        session,
        event_type="auth.oauth_identity_linked",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=user.id,
        metadata={"provider": "google"},
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_link_uniqueness_race_resolves_as_idempotent_success(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, email="listener@example.com", is_active=True)
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user_id,
        return_to="/membership",
        reauthenticated_user_id=user_id,
    )
    winner = SimpleNamespace(user_id=user_id, provider="google", subject=intent.subject)
    session = AsyncMock()
    monkeypatch.setattr(
        service.users_repository,
        "get_by_id_for_update",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity",
        AsyncMock(side_effect=[None, winner]),
    )
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity_for_user_provider",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service.repository,
        "create_oauth_identity",
        AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique"))),
    )
    audit = AsyncMock()
    monkeypatch.setattr(service, "add_audit_event", audit)

    await service.link_oauth_identity(session, current_user_id=user_id, intent=intent)

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_link_race_never_moves_subject_from_another_account(monkeypatch) -> None:
    user_id = uuid4()
    other_user_id = uuid4()
    user = SimpleNamespace(id=user_id, email="listener@example.com", is_active=True)
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user_id,
        return_to="/membership",
        reauthenticated_user_id=user_id,
    )
    winner = SimpleNamespace(user_id=other_user_id, provider="google", subject=intent.subject)
    session = AsyncMock()
    monkeypatch.setattr(
        service.users_repository,
        "get_by_id_for_update",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity",
        AsyncMock(side_effect=[None, winner]),
    )
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity_for_user_provider",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service.repository,
        "create_oauth_identity",
        AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique"))),
    )

    with pytest.raises(ConflictError, match="another account"):
        await service.link_oauth_identity(
            session,
            current_user_id=user_id,
            intent=intent,
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_social_login_creates_passwordless_user_for_new_verified_email(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="listener@example.com",
        role="member",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )
    monkeypatch.setattr(service.repository, "get_oauth_identity", AsyncMock(return_value=None))
    monkeypatch.setattr(service.users_repository, "get_by_email", AsyncMock(return_value=None))
    create_user = AsyncMock(return_value=user)
    monkeypatch.setattr(service.users_repository, "create", create_user)
    monkeypatch.setattr(service.repository, "create_oauth_identity", AsyncMock())
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())
    issued = (SimpleNamespace(user=user), "refresh-token")
    monkeypatch.setattr(service, "issue_token_pair", AsyncMock(return_value=issued))

    assert await service.authenticate_oauth_identity(AsyncMock(), identity) == issued
    create_user.assert_awaited_once_with(
        ANY,
        email="listener@example.com",
        password_hash=None,
        email_verified=True,
    )


@pytest.mark.asyncio
async def test_social_signup_does_not_commit_user_without_identity(monkeypatch) -> None:
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )
    user = SimpleNamespace(id=uuid4(), email=identity.email, is_active=True)
    session = AsyncMock()
    monkeypatch.setattr(service.repository, "get_oauth_identity", AsyncMock(return_value=None))
    monkeypatch.setattr(service.users_repository, "get_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(service.users_repository, "create", AsyncMock(return_value=user))
    monkeypatch.setattr(
        service.repository,
        "create_oauth_identity",
        AsyncMock(side_effect=RuntimeError("identity insert failed")),
    )

    with pytest.raises(RuntimeError, match="identity insert failed"):
        await service.authenticate_oauth_identity(session, identity)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_social_login_recovers_from_same_identity_creation_race(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email="listener@example.com",
        role="member",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    stored_identity = SimpleNamespace(user=user)
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )
    monkeypatch.setattr(
        service.repository,
        "get_oauth_identity",
        AsyncMock(side_effect=[None, stored_identity]),
    )
    monkeypatch.setattr(service.users_repository, "get_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.users_repository,
        "create",
        AsyncMock(side_effect=IntegrityError("insert", {}, Exception("race"))),
    )
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())
    issued = (SimpleNamespace(user=user), "refresh-token")
    monkeypatch.setattr(service, "issue_token_pair", AsyncMock(return_value=issued))
    session = AsyncMock()

    assert await service.authenticate_oauth_identity(session, identity) == issued
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_social_login_never_links_unverified_email() -> None:
    identity = oauth.VerifiedIdentity(
        provider="facebook",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=False,
    )

    with pytest.raises(AuthenticationError, match="verified email"):
        await service.authenticate_oauth_identity(AsyncMock(), identity)


@pytest.mark.asyncio
async def test_facebook_rejects_expired_debug_token(monkeypatch) -> None:
    monkeypatch.setattr(
        oauth,
        "_post_form",
        AsyncMock(return_value={"access_token": "provider-access-token"}),
    )
    provider_fetch = AsyncMock(
        side_effect=[
            {
                "data": {
                    "is_valid": True,
                    "app_id": "facebook-client",
                    "user_id": "facebook-subject",
                    "expires_at": int(datetime.now(UTC).timestamp()) - 1,
                }
            },
            {"id": "facebook-subject", "email": "listener@example.com"},
        ]
    )
    monkeypatch.setattr(oauth, "fetch_json", provider_fetch)

    with pytest.raises(AuthenticationError, match="Facebook access token"):
        await oauth.exchange_code(
            "facebook",
            "authorization-code",
            {"code_verifier": "v" * 64, "nonce": "n" * 32},
            oauth_settings(),
        )
    debug_call, profile_call = provider_fetch.await_args_list
    assert debug_call.kwargs["params"] == {"input_token": "provider-access-token"}
    assert debug_call.kwargs["headers"]["Authorization"].startswith("Bearer facebook-client|")
    assert "access_token" not in profile_call.kwargs["params"]
    assert profile_call.kwargs["headers"] == {
        "Authorization": "Bearer provider-access-token"
    }


def test_provider_identity_rejects_malformed_email() -> None:
    with pytest.raises(AuthenticationError, match="valid email"):
        oauth._identity_from_claims(
            "google",
            {
                "sub": "provider-subject",
                "email": "not-an-email",
                "email_verified": True,
            },
        )


@pytest.mark.asyncio
async def test_oauth_state_is_single_use(monkeypatch) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, bytes] = {}

        async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
            assert ex == 600
            assert nx is True
            if key in self.values:
                return False
            self.values[key] = value.encode()
            return True

        async def getdel(self, key: str) -> bytes | None:
            return self.values.pop(key, None)

        async def aclose(self) -> None:
            return None

    client = FakeRedis()
    monkeypatch.setattr(oauth, "get_redis_client", lambda: client)
    authorization = oauth.create_authorization(
        "google", oauth_settings(), return_to="/membership"
    )

    await oauth.register_oauth_state(authorization, ttl_seconds=600)
    transaction = await oauth.consume_oauth_state(
        authorization.state, expected_provider="google"
    )
    assert transaction == {
        "provider": "google",
        "nonce": authorization.nonce,
        "code_verifier": authorization.code_verifier,
        "return_to": "/membership",
    }
    assert (
        await oauth.consume_oauth_state(
            authorization.state, expected_provider="google"
        )
        is None
    )

    swapped = oauth.create_authorization("google", oauth_settings())
    await oauth.register_oauth_state(swapped, ttl_seconds=600)
    with pytest.raises(AuthenticationError, match="OAuth state"):
        await oauth.consume_oauth_state(swapped.state, expected_provider="apple")


@pytest.mark.asyncio
async def test_oauth_link_intent_requires_matching_post_conflict_authentication(monkeypatch) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, bytes] = {}

        async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
            assert ex == oauth.OAUTH_LINK_TTL_SECONDS
            assert nx is True
            if key in self.values:
                return False
            self.values[key] = value.encode()
            return True

        async def get(self, key: str) -> bytes | None:
            return self.values.get(key)

        async def eval(self, script: str, numkeys: int, key: str, user_id: str) -> int:
            assert "oauth_link_mark_reauthenticated_v1" in script
            assert numkeys == 1
            stored = self.values.get(key)
            if stored is None:
                return 0
            payload = json.loads(stored)
            if payload["target_user_id"] != user_id or payload["state"] != "pending":
                return 0
            payload["state"] = "reauthenticated"
            payload["reauthenticated_user_id"] = user_id
            self.values[key] = json.dumps(payload).encode()
            return 1

        async def getdel(self, key: str) -> bytes | None:
            return self.values.pop(key, None)

        async def delete(self, key: str) -> int:
            return 1 if self.values.pop(key, None) is not None else 0

        async def aclose(self) -> None:
            return None

    client = FakeRedis()
    monkeypatch.setattr(oauth, "get_redis_client", lambda: client)
    target_user_id = uuid4()
    other_user_id = uuid4()
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )

    raw_intent = await oauth.register_oauth_link_intent(
        identity,
        target_user_id=target_user_id,
        return_to="/library",
    )

    assert raw_intent.encode() not in next(iter(client.values)).encode()
    pending = await oauth.get_oauth_link_intent(raw_intent)
    assert pending is not None
    assert pending.provider == "google"
    assert pending.target_user_id == target_user_id
    assert pending.return_to == "/library"
    assert pending.reauthenticated_user_id is None
    assert await oauth.mark_oauth_link_reauthenticated(raw_intent, other_user_id) is False
    assert await oauth.mark_oauth_link_reauthenticated(raw_intent, target_user_id) is True

    ready = await oauth.consume_oauth_link_intent(raw_intent)
    assert ready is not None
    assert ready.reauthenticated_user_id == target_user_id
    assert await oauth.consume_oauth_link_intent(raw_intent) is None

    cancelled_intent = await oauth.register_oauth_link_intent(
        identity,
        target_user_id=target_user_id,
        return_to="/membership",
    )
    assert await oauth.cancel_oauth_link_intent(cancelled_intent) is True
    assert await oauth.get_oauth_link_intent(cancelled_intent) is None


@pytest.mark.asyncio
async def test_callback_redirects_controlled_provider_failure_and_clears_state_cookie(
    monkeypatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/oauth/google/callback",
            "headers": [(b"cookie", b"orna_oauth_state_google=opaque-state")],
        }
    )
    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        AsyncMock(
            return_value={
                "provider": "google",
                "nonce": "nonce",
                "code_verifier": "verifier",
                "return_to": "/membership",
            }
        ),
    )
    monkeypatch.setattr(
        oauth,
        "exchange_code",
        AsyncMock(side_effect=AuthenticationError("provider token was invalid")),
    )

    response = await auth_router._complete_oauth_callback(
        "google",
        request,
        "opaque-state",
        "sensitive-authorization-code",
        None,
        AsyncMock(),
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert "oauth=error" in location
    assert "oauth_error=failed" in location
    assert "sensitive-authorization-code" not in location
    assert "provider+token" not in location
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_callback_creates_opaque_link_intent_for_existing_account(monkeypatch) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/oauth/google/callback",
            "headers": [(b"cookie", b"orna_oauth_state_google=opaque-state")],
        }
    )
    identity = oauth.VerifiedIdentity(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        email_verified=True,
    )
    target_user_id = uuid4()
    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        AsyncMock(
            return_value={
                "provider": "google",
                "nonce": "nonce",
                "code_verifier": "verifier",
                "return_to": "/library",
            }
        ),
    )
    monkeypatch.setattr(oauth, "exchange_code", AsyncMock(return_value=identity))
    monkeypatch.setattr(
        service,
        "authenticate_oauth_identity",
        AsyncMock(
            side_effect=service.OAuthLinkRequired(
                target_user_id=target_user_id,
                identity=identity,
            )
        ),
    )
    register_link = AsyncMock(return_value="opaque-link-intent")
    monkeypatch.setattr(oauth, "register_oauth_link_intent", register_link)
    monkeypatch.setattr(auth_router, "get_settings", lambda: oauth_settings(AUTH_COOKIE_SECURE=True))

    response = await auth_router._complete_oauth_callback(
        "google",
        request,
        "opaque-state",
        "authorization-code",
        None,
        AsyncMock(),
    )

    register_link.assert_awaited_once_with(
        identity,
        target_user_id=target_user_id,
        return_to="/library",
    )
    assert response.status_code == 303
    assert "oauth_error=account_conflict" in response.headers["location"]
    assert "provider-user-123" not in response.headers["location"]
    assert "listener%40example.com" not in response.headers["location"]
    cookies = response.headers.getlist("set-cookie")
    link_cookie = next(cookie for cookie in cookies if cookie.startswith("orna_oauth_link="))
    assert "opaque-link-intent" in link_cookie
    assert "HttpOnly" in link_cookie
    assert "Secure" in link_cookie
    assert "SameSite=lax" in link_cookie
    assert "Path=/api/v1/auth" in link_cookie


@pytest.mark.asyncio
async def test_successful_oauth_login_marks_pending_link_reauthenticated(monkeypatch) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/oauth/apple/callback",
            "headers": [
                (
                    b"cookie",
                    b"orna_oauth_state_apple=opaque-state; orna_oauth_link=opaque-link-intent",
                )
            ],
        }
    )
    user_id = uuid4()
    payload = SimpleNamespace(user=SimpleNamespace(id=user_id))
    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        AsyncMock(
            return_value={
                "provider": "apple",
                "nonce": "nonce",
                "code_verifier": "verifier",
                "return_to": "/membership",
            }
        ),
    )
    monkeypatch.setattr(
        oauth,
        "exchange_code",
        AsyncMock(
            return_value=oauth.VerifiedIdentity(
                provider="apple",
                subject="apple-user",
                email="listener@example.com",
                email_verified=True,
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "authenticate_oauth_identity",
        AsyncMock(return_value=(payload, "refresh")),
    )
    monkeypatch.setattr(auth_router, "_set_auth_cookies", lambda *args: None)
    mark = AsyncMock(return_value=True)
    monkeypatch.setattr(oauth, "mark_oauth_link_reauthenticated", mark)

    response = await auth_router._complete_oauth_callback(
        "apple",
        request,
        "opaque-state",
        "authorization-code",
        None,
        AsyncMock(),
    )

    assert response.status_code == 303
    mark.assert_awaited_once_with("opaque-link-intent", user_id)


@pytest.mark.asyncio
async def test_pending_and_confirm_routes_require_ready_matching_intent(monkeypatch) -> None:
    user_id = uuid4()
    current_user = CurrentUser(id=str(user_id), email="listener@example.com")
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user_id,
        return_to="/library",
        reauthenticated_user_id=user_id,
    )
    monkeypatch.setattr(oauth, "get_oauth_link_intent", AsyncMock(return_value=intent))

    pending_response = await auth_router.pending_oauth_link(
        Response(), "opaque-link-intent", current_user
    )
    assert pending_response.pending is True
    assert pending_response.provider == "google"
    assert pending_response.ready is True

    monkeypatch.setattr(oauth, "consume_oauth_link_intent", AsyncMock(return_value=intent))
    link_identity = AsyncMock()
    monkeypatch.setattr(service, "link_oauth_identity", link_identity)
    response = Response()

    linked = await auth_router.confirm_oauth_link(
        auth_router.OAuthLinkConfirmRequest(confirmed=True),
        response,
        "opaque-link-intent",
        current_user,
        AsyncMock(),
    )

    assert linked.status == "linked"
    assert linked.provider == "google"
    assert linked.return_to == "/library"
    link_identity.assert_awaited_once_with(
        ANY,
        current_user_id=user_id,
        intent=intent,
    )
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_failed_oauth_link_confirmation_clears_consumed_cookie(monkeypatch) -> None:
    user_id = uuid4()
    current_user = CurrentUser(id=str(user_id), email="listener@example.com")
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user_id,
        return_to="/membership",
        reauthenticated_user_id=user_id,
    )
    monkeypatch.setattr(
        oauth,
        "consume_oauth_link_intent",
        AsyncMock(return_value=intent),
    )
    monkeypatch.setattr(
        service,
        "link_oauth_identity",
        AsyncMock(side_effect=AuthenticationError("stale")),
    )

    result = await auth_router.confirm_oauth_link(
        auth_router.OAuthLinkConfirmRequest(confirmed=True),
        Response(),
        "opaque-link-intent",
        current_user,
        AsyncMock(),
    )

    assert result.status_code == 403
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert "listener@example.com" not in result.body.decode()
    assert "provider-user-123" not in result.body.decode()


@pytest.mark.asyncio
async def test_oauth_link_database_failure_is_terminal_and_clears_cookie(monkeypatch) -> None:
    user_id = uuid4()
    intent = oauth.OAuthLinkIntent(
        provider="google",
        subject="provider-user-123",
        email="listener@example.com",
        target_user_id=user_id,
        return_to="/membership",
        reauthenticated_user_id=user_id,
    )
    monkeypatch.setattr(
        oauth,
        "consume_oauth_link_intent",
        AsyncMock(return_value=intent),
    )
    monkeypatch.setattr(
        service,
        "link_oauth_identity",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )
    session = AsyncMock()

    result = await auth_router.confirm_oauth_link(
        auth_router.OAuthLinkConfirmRequest(confirmed=True),
        Response(),
        "opaque-link-intent",
        CurrentUser(id=str(user_id), email="listener@example.com"),
        session,
    )

    assert result.status_code == 503
    assert "Max-Age=0" in result.headers["set-cookie"]
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_oauth_link_consumes_intent_and_clears_cookie(monkeypatch) -> None:
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(oauth, "cancel_oauth_link_intent", cancel)
    response = Response()

    result = await auth_router.cancel_oauth_link(response, "opaque-link-intent")

    assert result.status == "cancelled"
    cancel.assert_awaited_once_with("opaque-link-intent")
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_password_login_marks_only_matching_pending_link_as_reauthenticated(monkeypatch) -> None:
    user_id = uuid4()
    payload = SimpleNamespace(
        access_token="access",
        user=SimpleNamespace(id=user_id),
    )
    monkeypatch.setattr(
        service,
        "authenticate_password_login",
        AsyncMock(return_value=(payload, "refresh")),
    )
    monkeypatch.setattr(auth_router, "_set_auth_cookies", lambda *args: None)
    mark = AsyncMock(return_value=True)
    monkeypatch.setattr(oauth, "mark_oauth_link_reauthenticated", mark)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"cookie", b"orna_oauth_link=opaque-link-intent")],
            "client": ("127.0.0.1", 1234),
        }
    )

    result = await auth_router.login(
        SimpleNamespace(email="listener@example.com", password="correct-password"),
        request,
        Response(),
        AsyncMock(),
    )

    assert result is payload
    mark.assert_awaited_once_with("opaque-link-intent", user_id)


@pytest.mark.asyncio
async def test_callback_redirects_state_store_outage_and_clears_cookie(monkeypatch) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/oauth/google/callback",
            "headers": [(b"cookie", b"orna_oauth_state_google=opaque-state")],
        }
    )
    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        AsyncMock(side_effect=ServiceUnavailableError("redis unavailable")),
    )

    response = await auth_router._complete_oauth_callback(
        "google",
        request,
        "opaque-state",
        "authorization-code",
        None,
        AsyncMock(),
    )

    assert response.status_code == 303
    assert "oauth_error=unavailable" in response.headers["location"]
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_apple_form_post_callback_parses_bounded_form(monkeypatch) -> None:
    body = b"state=signed-state&code=authorization-code"
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/oauth/apple/callback",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        },
        receive,
    )
    response = SimpleNamespace()
    complete = AsyncMock(return_value=response)
    monkeypatch.setattr(auth_router, "_complete_oauth_callback", complete)
    session = AsyncMock()

    assert await auth_router.apple_oauth_callback(request, session) is response
    complete.assert_awaited_once_with(
        "apple", request, "signed-state", "authorization-code", None, session
    )


def test_oauth_routes_are_documented_in_openapi() -> None:
    paths = app.openapi()["paths"]
    assert "200" in paths["/api/v1/auth/oauth/providers"]["get"]["responses"]
    assert "get" in paths["/api/v1/auth/oauth/{provider}/start"]
    assert "302" in paths["/api/v1/auth/oauth/{provider}/start"]["get"]["responses"]
    assert "get" in paths["/api/v1/auth/oauth/{provider}/callback"]
    assert "303" in paths["/api/v1/auth/oauth/{provider}/callback"]["get"]["responses"]
    apple_callback = paths["/api/v1/auth/oauth/apple/callback"]["post"]
    assert "303" in apple_callback["responses"]
    assert "application/x-www-form-urlencoded" in apple_callback["requestBody"]["content"]


def test_configured_oauth_providers_only_includes_complete_configurations() -> None:
    settings = oauth_settings(
        APPLE_CLIENT_ID=None,
        APPLE_TEAM_ID=None,
        APPLE_KEY_ID=None,
        APPLE_PRIVATE_KEY=None,
        FACEBOOK_CLIENT_ID=None,
        FACEBOOK_CLIENT_SECRET=None,
    )
    assert oauth.configured_providers(settings) == ["google"]


def test_production_oauth_requires_complete_provider_configuration() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_SECRET"):
        Settings(
            _env_file=None,
            APP_ENVIRONMENT="production",
            AUTH_SECRET_KEY="a" * 32,
            AUTH_COOKIE_SECURE=True,
            HLS_TOKEN_SECRET="h" * 32,
            GOOGLE_CLIENT_ID="google-client",
        )

    complete_google = {
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
    }
    with pytest.raises(ValidationError, match="OAUTH_CALLBACK_BASE_URL"):
        Settings(
            _env_file=None,
            APP_ENVIRONMENT="production",
            AUTH_SECRET_KEY="a" * 32,
            AUTH_COOKIE_SECURE=True,
            HLS_TOKEN_SECRET="h" * 32,
            OAUTH_CALLBACK_BASE_URL="https://",
            OAUTH_FRONTEND_URL="https://atlas.example.com/membership",
            **complete_google,
        )

    with pytest.raises(ValidationError, match="OAUTH_CALLBACK_BASE_URL"):
        Settings(
            _env_file=None,
            APP_ENVIRONMENT="production",
            AUTH_SECRET_KEY="a" * 32,
            AUTH_COOKIE_SECURE=True,
            HLS_TOKEN_SECRET="h" * 32,
            OAUTH_CALLBACK_BASE_URL="https://atlas.example.com:bad/api/v1/auth/oauth",
            OAUTH_FRONTEND_URL="https://atlas.example.com/membership",
            **complete_google,
        )

    ambiguous_urls = [
        "https://example.com\n.evil/path",
        "https://example.com /path",
        "https://example.com\\evil/path",
        "https://example.com/%0d%0aevil",
        "https://-invalid.example/path",
    ]
    for field_name in ("OAUTH_CALLBACK_BASE_URL", "OAUTH_FRONTEND_URL"):
        for invalid_url in ambiguous_urls:
            values = {
                "OAUTH_CALLBACK_BASE_URL": "https://atlas.example.com/api/v1/auth/oauth",
                "OAUTH_FRONTEND_URL": "https://atlas.example.com/membership",
                field_name: invalid_url,
            }
            with pytest.raises(ValidationError, match=field_name):
                Settings(
                    _env_file=None,
                    APP_ENVIRONMENT="production",
                    AUTH_SECRET_KEY="a" * 32,
                    AUTH_COOKIE_SECURE=True,
                    HLS_TOKEN_SECRET="h" * 32,
                    **values,
                    **complete_google,
                )


def test_apple_oauth_requires_a_p256_private_key() -> None:
    common = {
        "_env_file": None,
        "APPLE_CLIENT_ID": "apple-client",
        "APPLE_TEAM_ID": "apple-team",
        "APPLE_KEY_ID": "apple-key",
    }
    with pytest.raises(ValidationError, match="P-256"):
        Settings(**common, APPLE_PRIVATE_KEY="not-a-private-key")

    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    escaped = pem.replace("\n", "\\n")
    assert Settings(**common, APPLE_PRIVATE_KEY=escaped).apple_private_key == escaped
