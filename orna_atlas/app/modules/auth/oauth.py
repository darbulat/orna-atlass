from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import asyncio
import base64
from collections import OrderedDict
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt
from email_validator import EmailNotValidError, validate_email
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm
from redis.exceptions import RedisError

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ServiceUnavailableError
from orna_atlas.app.integrations.redis import get_redis_client

OAuthProvider = Literal["google", "apple", "facebook"]
OAUTH_STATE_TTL_SECONDS = 600
JWKS_CACHE_TTL_SECONDS = 300
JWKS_CACHE_MAX_ENTRIES = 8

_jwks_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_jwks_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class OAuthAuthorization:
    provider: OAuthProvider
    url: str
    state: str
    nonce: str
    code_verifier: str
    return_to: str


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: OAuthProvider
    subject: str
    email: str
    email_verified: bool


_PROVIDER_AUTH_URLS: dict[OAuthProvider, str] = {
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
    "apple": "https://appleid.apple.com/auth/authorize",
    "facebook": "https://www.facebook.com/v22.0/dialog/oauth",
}


def configured_providers(settings: Settings) -> list[OAuthProvider]:
    providers: list[OAuthProvider] = []
    if settings.google_client_id and settings.google_client_secret:
        providers.append("google")
    if all(
        (
            settings.apple_client_id,
            settings.apple_team_id,
            settings.apple_key_id,
            settings.apple_private_key,
        )
    ):
        providers.append("apple")
    if settings.facebook_client_id and settings.facebook_client_secret:
        providers.append("facebook")
    return providers


def _clear_jwks_cache() -> None:
    _jwks_cache.clear()
    _jwks_locks.clear()


def _safe_return_to(value: str | None) -> str:
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        return "/membership"
    return value.split("#", 1)[0]


def _oauth_state_key(raw_state: str) -> str:
    digest = hashlib.sha256(raw_state.encode()).hexdigest()
    return f"oauth:state:{digest}"


async def register_oauth_state(
    authorization: OAuthAuthorization, *, ttl_seconds: int
) -> None:
    client = get_redis_client()
    transaction = json.dumps(
        {
            "provider": authorization.provider,
            "nonce": authorization.nonce,
            "code_verifier": authorization.code_verifier,
            "return_to": authorization.return_to,
        },
        separators=(",", ":"),
    )
    try:
        stored = await client.set(
            _oauth_state_key(authorization.state), transaction, ex=ttl_seconds, nx=True
        )
        if not stored:
            raise AuthenticationError("OAuth state could not be registered")
    except RedisError as exc:
        raise ServiceUnavailableError("OAuth state service unavailable") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass


async def consume_oauth_state(
    raw_state: str, *, expected_provider: OAuthProvider
) -> dict[str, str] | None:
    client = get_redis_client()
    try:
        stored = await client.getdel(_oauth_state_key(raw_state))
    except RedisError as exc:
        raise ServiceUnavailableError("OAuth state service unavailable") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass
    if stored is None:
        return None
    try:
        payload = json.loads(stored)
        required = ("provider", "nonce", "code_verifier", "return_to")
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(key), str) or not payload[key] for key in required
        ):
            raise ValueError("missing OAuth transaction field")
        if payload["provider"] != expected_provider:
            raise ValueError("provider mismatch")
        payload["return_to"] = _safe_return_to(payload["return_to"])
        return payload
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Invalid or expired OAuth state") from exc


def _client_id(provider: OAuthProvider, settings: Settings) -> str:
    value = getattr(settings, f"{provider}_client_id")
    if not value:
        raise AuthenticationError(f"{provider.title()} sign-in is not configured")
    return value


def _callback_url(provider: OAuthProvider, settings: Settings) -> str:
    return f"{settings.oauth_callback_base_url.rstrip('/')}/{provider}/callback"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def create_authorization(
    provider: OAuthProvider,
    settings: Settings,
    *,
    return_to: str | None = None,
) -> OAuthAuthorization:
    client_id = _client_id(provider, settings)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    safe_return_to = _safe_return_to(return_to)
    state = secrets.token_urlsafe(32)
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": _callback_url(provider, settings),
        "response_type": "code",
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params.update(
            {
                "scope": "openid email",
                "nonce": nonce,
                "access_type": "offline",
                "prompt": "select_account",
            }
        )
    elif provider == "apple":
        params.update({"scope": "name email", "nonce": nonce, "response_mode": "form_post"})
    else:
        params.update({"scope": "email", "auth_type": "rerequest"})
    return OAuthAuthorization(
        provider=provider,
        url=f"{_PROVIDER_AUTH_URLS[provider]}?{urlencode(params)}",
        state=state,
        nonce=nonce,
        code_verifier=verifier,
        return_to=safe_return_to,
    )


async def fetch_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        # Do not chain provider exceptions: request URLs can contain short-lived tokens.
        if exc.response.status_code >= 500:
            raise ServiceUnavailableError("OAuth provider is temporarily unavailable") from None
        raise AuthenticationError("OAuth provider request failed") from None
    except httpx.HTTPError:
        raise ServiceUnavailableError("OAuth provider is temporarily unavailable") from None
    except ValueError:
        raise AuthenticationError("OAuth provider request failed") from None
    if not isinstance(payload, dict):
        raise AuthenticationError("OAuth provider returned an invalid response")
    return payload


async def _get_jwks(
    url: str,
    *,
    force_refresh: bool = False,
    stale_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = time.monotonic()
    cached = _jwks_cache.get(url)
    if not force_refresh and cached is not None and cached[0] > now:
        _jwks_cache.move_to_end(url)
        return cached[1]

    lock = _jwks_locks.setdefault(url, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _jwks_cache.get(url)
        cache_was_refreshed = (
            force_refresh
            and stale_payload is not None
            and cached is not None
            and cached[0] > now
            and cached[1] is not stale_payload
        )
        if (
            (not force_refresh and cached is not None and cached[0] > now)
            or cache_was_refreshed
        ):
            assert cached is not None
            _jwks_cache.move_to_end(url)
            return cached[1]
        payload = await fetch_json(url)
        if not isinstance(payload.get("keys"), list):
            raise AuthenticationError("OAuth provider returned invalid signing keys")
        _jwks_cache[url] = (now + JWKS_CACHE_TTL_SECONDS, payload)
        _jwks_cache.move_to_end(url)
        while len(_jwks_cache) > JWKS_CACHE_MAX_ENTRIES:
            expired_url, _ = _jwks_cache.popitem(last=False)
            _jwks_locks.pop(expired_url, None)
        return payload


async def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            raise ServiceUnavailableError("OAuth provider is temporarily unavailable") from None
        raise AuthenticationError("OAuth provider request failed") from None
    except httpx.HTTPError:
        raise ServiceUnavailableError("OAuth provider is temporarily unavailable") from None
    except ValueError:
        raise AuthenticationError("OAuth provider request failed") from None
    if not isinstance(payload, dict) or payload.get("error"):
        raise AuthenticationError("OAuth provider rejected the authorization code")
    return payload


async def _verify_oidc_token(
    token: str,
    *,
    nonce: str,
    audience: str,
    issuers: tuple[str, ...],
    jwks_url: str,
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwks = await _get_jwks(jwks_url)
        candidates = [key for key in jwks.get("keys", []) if key.get("kid") == kid]
        if len(candidates) != 1:
            jwks = await _get_jwks(
                jwks_url,
                force_refresh=True,
                stale_payload=jwks,
            )
            candidates = [key for key in jwks.get("keys", []) if key.get("kid") == kid]
        if len(candidates) != 1:
            raise InvalidTokenError("unknown signing key")
        key = RSAAlgorithm.from_jwk(candidates[0])
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        token_audience = claims.get("aud")
        authorized_party = claims.get("azp")
        if isinstance(token_audience, list) and len(token_audience) > 1:
            if authorized_party != audience:
                raise InvalidTokenError("authorized party mismatch")
        elif authorized_party is not None and authorized_party != audience:
            raise InvalidTokenError("authorized party mismatch")
        if claims.get("iss") not in issuers or not hmac.compare_digest(
            str(claims.get("nonce", "")), nonce
        ):
            raise InvalidTokenError("issuer or nonce mismatch")
        return claims
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid OAuth identity token") from exc


def _verified_email(value: object) -> bool:
    return value is True or value == "true"


def _identity_from_claims(
    provider: OAuthProvider,
    claims: dict[str, Any],
) -> VerifiedIdentity:
    subject = claims.get("sub")
    email = claims.get("email")
    verified = _verified_email(claims.get("email_verified"))
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise AuthenticationError("OAuth identity is missing a valid subject")
    if not isinstance(email, str) or not email or len(email) > 320:
        raise AuthenticationError("OAuth identity did not provide an email address")
    try:
        normalized_email = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise AuthenticationError("OAuth identity did not provide a valid email address") from exc
    return VerifiedIdentity(
        provider=provider,
        subject=subject,
        email=normalized_email.lower(),
        email_verified=verified,
    )


async def verify_google_id_token(
    token: str,
    *,
    nonce: str,
    settings: Settings,
) -> VerifiedIdentity:
    claims = await _verify_oidc_token(
        token,
        nonce=nonce,
        audience=_client_id("google", settings),
        issuers=("https://accounts.google.com", "accounts.google.com"),
        jwks_url="https://www.googleapis.com/oauth2/v3/certs",
    )
    return _identity_from_claims("google", claims)


async def _verify_apple_id_token(
    token: str,
    *,
    nonce: str,
    settings: Settings,
) -> VerifiedIdentity:
    claims = await _verify_oidc_token(
        token,
        nonce=nonce,
        audience=_client_id("apple", settings),
        issuers=("https://appleid.apple.com",),
        jwks_url="https://appleid.apple.com/auth/keys",
    )
    return _identity_from_claims("apple", claims)


def _apple_client_secret(settings: Settings) -> str:
    private_key = settings.apple_private_key
    if private_key is None or not all(
        (
            settings.apple_team_id,
            settings.apple_key_id,
            settings.apple_client_id,
        )
    ):
        raise AuthenticationError("Apple sign-in is not configured")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.apple_team_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "aud": "https://appleid.apple.com",
            "sub": settings.apple_client_id,
        },
        private_key.replace("\\n", "\n"),
        algorithm="ES256",
        headers={"kid": settings.apple_key_id},
    )


async def _exchange_facebook_token(
    code: str,
    *,
    code_verifier: str,
    settings: Settings,
) -> VerifiedIdentity:
    client_id = _client_id("facebook", settings)
    client_secret = settings.facebook_client_secret
    if not client_secret:
        raise AuthenticationError("Facebook sign-in is not configured")
    token_payload = await _post_form(
        "https://graph.facebook.com/v22.0/oauth/access_token",
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _callback_url("facebook", settings),
            "code": code,
            "code_verifier": code_verifier,
        },
    )
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AuthenticationError("Facebook did not return an access token")
    proof = hmac.new(client_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()
    debug = await fetch_json(
        "https://graph.facebook.com/debug_token",
        params={"input_token": access_token},
        headers={"Authorization": f"Bearer {client_id}|{client_secret}"},
    )
    profile = await fetch_json(
        "https://graph.facebook.com/v22.0/me",
        params={"fields": "id,email", "appsecret_proof": proof},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    debug_data = debug.get("data")
    expires_at = debug_data.get("expires_at") if isinstance(debug_data, dict) else None
    if (
        not isinstance(debug_data, dict)
        or debug_data.get("is_valid") is not True
        or str(debug_data.get("app_id")) != client_id
        or str(debug_data.get("user_id")) != str(profile.get("id"))
        or not isinstance(expires_at, (int, float))
        or expires_at <= datetime.now(UTC).timestamp()
    ):
        raise AuthenticationError("Invalid Facebook access token")
    email = profile.get("email")
    subject = profile.get("id")
    if not isinstance(email, str) or not email or not isinstance(subject, str) or not subject:
        raise AuthenticationError("Facebook did not provide a verified email address")
    return _identity_from_claims(
        "facebook",
        {"sub": subject, "email": email, "email_verified": True},
    )


async def exchange_code(
    provider: OAuthProvider,
    code: str,
    state_claims: dict[str, str],
    settings: Settings,
) -> VerifiedIdentity:
    verifier = state_claims["code_verifier"]
    nonce = state_claims["nonce"]
    if provider == "facebook":
        return await _exchange_facebook_token(
            code,
            code_verifier=verifier,
            settings=settings,
        )
    token_url = (
        "https://oauth2.googleapis.com/token"
        if provider == "google"
        else "https://appleid.apple.com/auth/token"
    )
    client_secret = (
        settings.google_client_secret if provider == "google" else _apple_client_secret(settings)
    )
    if not client_secret:
        raise AuthenticationError(f"{provider.title()} sign-in is not configured")
    token_payload = await _post_form(
        token_url,
        {
            "client_id": _client_id(provider, settings),
            "client_secret": client_secret,
            "redirect_uri": _callback_url(provider, settings),
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
        },
    )
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise AuthenticationError("OAuth provider did not return an identity token")
    if provider == "google":
        return await verify_google_id_token(id_token, nonce=nonce, settings=settings)
    return await _verify_apple_id_token(id_token, nonce=nonce, settings=settings)
