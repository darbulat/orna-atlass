import inspect
import json
import ssl
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Request, Response

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import ServiceUnavailableError
from orna_atlas.app.modules.auth import magic, router
from orna_atlas.app.modules.auth.schemas import MagicLinkRequest


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert ex == magic.MAGIC_LINK_TTL_SECONDS
        assert nx is True
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def aclose(self) -> None:
        self.closed = True


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_FROM_EMAIL": "signin@example.test",
        "MAGIC_LINK_CALLBACK_URL": "https://api.example.test/api/v1/auth/magic-link/consume",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_magic_link_consume_query_does_not_preempt_terminal_redirect() -> None:
    query = inspect.signature(router.consume_magic_link).parameters["token"].default

    assert query.default == ""
    assert not hasattr(query, "min_length")
    assert not hasattr(query, "max_length")


@pytest.mark.asyncio
async def test_malformed_magic_link_uses_terminal_redirect_and_clears_cookie(monkeypatch) -> None:
    configured = settings()
    monkeypatch.setattr(router, "get_settings", lambda: configured)
    consume = AsyncMock()
    monkeypatch.setattr(router.magic, "consume_magic_link", consume)

    response = await router.consume_magic_link(
        Request({"type": "http", "headers": []}), "", AsyncMock()
    )

    assert response.status_code == 303
    assert parse_qs(urlparse(response.headers["location"]).query) == {
        "magic": ["error"],
        "magic_error": ["invalid_or_expired"],
    }
    assert f"{magic.MAGIC_LINK_BROWSER_COOKIE}=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    consume.assert_not_awaited()


@pytest.mark.parametrize(("created", "outcome"), [(True, "signup"), (False, "login")])
@pytest.mark.asyncio
async def test_magic_link_redirect_distinguishes_signup_from_login(
    monkeypatch, created: bool, outcome: str
) -> None:
    configured = settings()
    monkeypatch.setattr(router, "get_settings", lambda: configured)
    monkeypatch.setattr(
        router.magic,
        "consume_magic_link",
        AsyncMock(return_value={"email": "listener@example.com", "return_to": "/membership"}),
    )
    monkeypatch.setattr(
        router.service,
        "authenticate_magic_link",
        AsyncMock(return_value=(SimpleNamespace(access_token="access"), "refresh", created)),
    )

    response = await router.consume_magic_link(
        Request({"type": "http", "headers": []}), "x" * 32, AsyncMock()
    )

    assert parse_qs(urlparse(response.headers["location"]).query)["magic"] == [outcome]


def test_magic_link_return_path_is_internal_only() -> None:
    assert magic.safe_return_to("/sessions/forest?source=paywall#ignored") == "/sessions/forest?source=paywall"
    assert magic.safe_return_to("//evil.example/path") == "/membership"
    assert magic.safe_return_to("/\\evil") == "/membership"
    assert magic.safe_return_to("/ok\x7f") == "/membership"
    assert magic.safe_return_to("/ok%0d%0aLocation:https://attacker.example") == "/membership"
    assert magic.safe_return_to("/%2f%2fattacker.example") == "/membership"
    assert magic.safe_return_to("/ok%5cattacker") == "/membership"


@pytest.mark.asyncio
async def test_magic_link_request_binds_token_to_an_httponly_browser_cookie(monkeypatch) -> None:
    configured = settings()
    captured: dict[str, str] = {}

    async def capture_send_magic_link(**kwargs: object) -> None:
        captured["browser_nonce"] = str(kwargs["browser_nonce"])

    monkeypatch.setattr(router, "get_settings", lambda: configured)
    monkeypatch.setattr(router.magic, "send_magic_link", capture_send_magic_link)
    response = Response()

    accepted = await router.request_magic_link(
        MagicLinkRequest(email="listener@example.com", return_to="/sessions/forest"),
        response,
    )

    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    browser_cookie = cookie[magic.MAGIC_LINK_BROWSER_COOKIE]
    assert accepted.accepted is True
    assert browser_cookie.value == captured["browser_nonce"]
    assert browser_cookie["httponly"] is True
    assert browser_cookie["samesite"].lower() == "lax"
    assert browser_cookie["path"] == f"{configured.api_prefix}/auth/magic-link/consume"


@pytest.mark.asyncio
async def test_terminal_magic_link_auth_failure_clears_browser_cookie(monkeypatch) -> None:
    configured = settings()
    session = AsyncMock()
    request = Request({
        "type": "http",
        "headers": [(b"cookie", f"{magic.MAGIC_LINK_BROWSER_COOKIE}=requesting-browser".encode())],
    })
    monkeypatch.setattr(router, "get_settings", lambda: configured)
    monkeypatch.setattr(
        router.magic,
        "consume_magic_link",
        AsyncMock(return_value={"email": "listener@example.com", "return_to": "/membership"}),
    )
    monkeypatch.setattr(
        router.service,
        "authenticate_magic_link",
        AsyncMock(side_effect=ServiceUnavailableError("unavailable")),
    )

    response = await router.consume_magic_link(request, "x" * 32, session)

    assert response.status_code == 303
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert f"{magic.MAGIC_LINK_BROWSER_COOKIE}=\"\"" in response.headers["set-cookie"]
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_magic_link_unexpected_failure_clears_cookie_even_if_rollback_fails(monkeypatch) -> None:
    configured = settings()
    session = AsyncMock()
    session.rollback.side_effect = RuntimeError("rollback unavailable")
    request = Request({
        "type": "http",
        "headers": [(b"cookie", f"{magic.MAGIC_LINK_BROWSER_COOKIE}=requesting-browser".encode())],
    })
    monkeypatch.setattr(router, "get_settings", lambda: configured)
    monkeypatch.setattr(
        router.magic,
        "consume_magic_link",
        AsyncMock(return_value={"email": "listener@example.com", "return_to": "/membership"}),
    )
    monkeypatch.setattr(
        router.service,
        "authenticate_magic_link",
        AsyncMock(side_effect=RuntimeError("unexpected authentication failure")),
    )

    response = await router.consume_magic_link(request, "x" * 32, session)

    assert response.status_code == 303
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert f"{magic.MAGIC_LINK_BROWSER_COOKIE}=\"\"" in response.headers["set-cookie"]
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_magic_link_is_opaque_one_time_and_email_delivery_is_real_boundary(monkeypatch) -> None:
    redis = FakeRedis()
    delivered: dict[str, str] = {}
    monkeypatch.setattr(magic, "get_redis_client", lambda: redis)

    def capture_email(_settings: Settings, recipient: str, callback_url: str) -> None:
        delivered.update(recipient=recipient, callback_url=callback_url)

    monkeypatch.setattr(magic, "_send_email", capture_email)

    await magic.send_magic_link(
        settings=settings(),
        email="Listener@Example.test",
        return_to="/sessions/forest?source=paywall",
        browser_nonce="requesting-browser",
    )

    assert delivered["recipient"] == "listener@example.test"
    token = parse_qs(urlparse(delivered["callback_url"]).query)["token"][0]
    assert len(token) >= 32
    assert token not in next(iter(redis.values))
    stored = json.loads(next(iter(redis.values.values())))
    assert stored == {
        "email": "listener@example.test",
        "return_to": "/sessions/forest?source=paywall",
        "browser_nonce_digest": magic._browser_nonce_digest("requesting-browser"),
    }

    assert await magic.consume_magic_link(token, None) is None
    assert await magic.consume_magic_link(token, "attacker-browser") is None
    assert redis.values, "a scanner or different browser must not consume the token"
    claims = await magic.consume_magic_link(token, "requesting-browser")
    assert claims == {
        "email": "listener@example.test",
        "return_to": "/sessions/forest?source=paywall",
    }
    assert await magic.consume_magic_link(token, "requesting-browser") is None


@pytest.mark.asyncio
async def test_magic_link_fails_truthfully_without_delivery_provider() -> None:
    with pytest.raises(ServiceUnavailableError, match="not configured"):
        await magic.send_magic_link(
            settings=settings(SMTP_HOST=None, SMTP_FROM_EMAIL=None),
            email="listener@example.test",
            return_to="/membership",
            browser_nonce="requesting-browser",
        )


def test_smtp_starttls_uses_a_verified_default_context(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def starttls(self, *, context) -> None:
            observed["context"] = context

        def send_message(self, _message) -> None:
            observed["sent"] = True

    monkeypatch.setattr(magic.smtplib, "SMTP", FakeSMTP)
    magic._send_email(
        settings(), "listener@example.test", "https://api.example.test/callback"
    )

    context = observed["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert observed["sent"] is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SMTP_STARTTLS": False}, "SMTP_STARTTLS"),
        (
            {
                "MAGIC_LINK_CALLBACK_URL": "http://api.example.test/api/v1/auth/magic-link/consume"
            },
            "HTTPS",
        ),
        (
            {
                "MAGIC_LINK_CALLBACK_URL": "https://user:pass@api.example.test/api/v1/auth/magic-link/consume"
            },
            "credentials",
        ),
        (
            {"MAGIC_LINK_CALLBACK_URL": "https://api.example.test/wrong"},
            "callback path",
        ),
        (
            {"MAGIC_LINK_CALLBACK_URL": "https://api.example.test:bad/api/v1/auth/magic-link/consume"},
            "valid production HTTPS URL",
        ),
        (
            {"MAGIC_LINK_CALLBACK_URL": "https://-bad-.example/api/v1/auth/magic-link/consume"},
            "valid production HTTPS URL",
        ),
        ({"SMTP_USERNAME": "listener", "SMTP_PASSWORD": None}, "configured together"),
        ({"SMTP_HOST": "   "}, "must not be blank"),
        ({"SMTP_FROM_EMAIL": "   "}, "must not be blank"),
        ({"OAUTH_FRONTEND_URL": "http://orna.land/membership"}, "OAUTH_FRONTEND_URL"),
    ],
)
def test_production_rejects_unsafe_magic_link_delivery(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        settings(
            APP_ENVIRONMENT="production",
            AUTH_SECRET_KEY="a" * 32,
            HLS_TOKEN_SECRET="b" * 32,
            AUTH_COOKIE_SECURE=True,
            **overrides,
        )


def test_production_accepts_a_fully_secure_magic_link_delivery_configuration() -> None:
    configured = settings(
        APP_ENVIRONMENT="production",
        AUTH_SECRET_KEY="a" * 32,
        HLS_TOKEN_SECRET="b" * 32,
        AUTH_COOKIE_SECURE=True,
        OAUTH_FRONTEND_URL="https://orna.land/membership",
    )

    assert configured.smtp_starttls is True
