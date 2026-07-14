from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import secrets
from typing import Literal
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Cookie, Depends, Header, HTTPException, status
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.db.session import get_db_session

from orna_atlas.app.core.config import get_settings

Role = Literal["member", "editor", "admin"]
ACCESS_COOKIE = "orna_access"
REFRESH_COOKIE = "orna_refresh"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: Role = "member"
    email: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _require_canonical_jwt(token: str) -> None:
    """Reject alternate base64url spellings before signature verification.

    Some decoders accept non-zero padding bits in an unpadded JWT segment.  Those
    strings decode to the same signature bytes, which makes a one-character token
    mutation appear valid even though the compact JWT representation changed.
    """
    segments = token.split(".")
    if len(segments) != 3 or any(not segment for segment in segments):
        raise ValueError("invalid JWT compact serialization")
    for segment in segments:
        if _b64encode(_b64decode(segment)) != segment:
            raise ValueError("non-canonical JWT base64url segment")


def create_access_token(user_id: UUID | str, role: Role, email: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.access_token_ttl_seconds)
    claims = {"sub": str(user_id), "role": role, "email": email, "exp": int(expires_at.timestamp())}
    signing_key = (
        settings.auth_private_key
        if settings.auth_signing_algorithm == "RS256"
        else settings.auth_secret_key
    )
    token = jwt.encode(
        claims,
        signing_key,
        algorithm=settings.auth_signing_algorithm,
        headers={"kid": settings.auth_key_id},
    )
    return token, expires_at


def _public_jwk() -> dict[str, object] | None:
    settings = get_settings()
    if settings.auth_signing_algorithm != "RS256" or not settings.auth_private_key:
        return None
    private_key = serialization.load_pem_private_key(
        settings.auth_private_key.encode(), password=None
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("AUTH_PRIVATE_KEY must contain an RSA private key")
    public_key = private_key.public_key()
    payload = json.loads(RSAAlgorithm.to_jwk(public_key))
    payload.update({"kid": settings.auth_key_id, "use": "sig", "alg": "RS256"})
    return payload


def _sanitized_public_rsa_jwk(
    configured_key: object, *, index: int
) -> dict[str, object]:
    """Validate a configured rotation key and retain public RSA material only."""
    if not isinstance(configured_key, dict):
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}] must be an object")
    if configured_key.get("kty") != "RSA":
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}] must be an RSA key")

    key_id = configured_key.get("kid")
    if not isinstance(key_id, str) or not key_id.strip():
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}].kid must be a non-empty string")
    if configured_key.get("alg") not in {None, "RS256"}:
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}].alg must be RS256")
    if configured_key.get("use") not in {None, "sig"}:
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}].use must be sig")
    key_ops = configured_key.get("key_ops")
    if key_ops is not None and key_ops not in (["verify"], ["sign"]):
        raise ValueError(
            f"AUTH_JWKS_JSON keys[{index}].key_ops must contain only sign or verify"
        )

    modulus = configured_key.get("n")
    exponent = configured_key.get("e")
    if not isinstance(modulus, str) or not modulus:
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}].n must be a non-empty string")
    if not isinstance(exponent, str) or not exponent:
        raise ValueError(f"AUTH_JWKS_JSON keys[{index}].e must be a non-empty string")

    # Whitelisting kty/n/e before parsing intentionally discards every private
    # parameter (d, p, q, dp, dq, qi, oth), as well as a stray symmetric `k`.
    try:
        public_key = RSAAlgorithm.from_jwk({"kty": "RSA", "n": modulus, "e": exponent})
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("not an RSA public key")
        sanitized = json.loads(RSAAlgorithm.to_jwk(public_key))
    except Exception as exc:
        raise ValueError(
            f"AUTH_JWKS_JSON keys[{index}] does not contain valid RSA public material"
        ) from exc

    sanitized.update({"kid": key_id, "use": "sig", "alg": "RS256"})
    return sanitized


def public_jwks() -> dict[str, list[dict[str, object]]]:
    settings = get_settings()
    # A shared HS256 secret must never cross the public JWKS boundary. Configured
    # rotation keys are meaningful only while asymmetric signing is active.
    if settings.auth_signing_algorithm != "RS256":
        return {"keys": []}

    current = _public_jwk()
    if current is None:
        raise ValueError("AUTH_PRIVATE_KEY is required to publish an RS256 JWKS")

    keys = [current]
    configured = settings.auth_jwks_json
    if not configured:
        return {"keys": keys}
    try:
        payload = json.loads(configured)
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_JWKS_JSON must contain valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise ValueError("AUTH_JWKS_JSON must be a JWKS object with a keys list")

    current_key_id = current["kid"]
    current_material = (current["n"], current["e"])
    configured_key_ids: set[str] = set()
    published_material = {current_material}
    for index, configured_key in enumerate(payload["keys"]):
        sanitized = _sanitized_public_rsa_jwk(configured_key, index=index)
        key_id = sanitized["kid"]
        if key_id in configured_key_ids:
            raise ValueError(f"AUTH_JWKS_JSON contains duplicate kid {key_id!r}")
        configured_key_ids.add(key_id)

        # Configuration cannot shadow the active signer. The public key derived
        # from AUTH_PRIVATE_KEY is authoritative for its kid.
        if key_id == current_key_id:
            continue
        material = (sanitized["n"], sanitized["e"])
        if material in published_material:
            raise ValueError(
                f"AUTH_JWKS_JSON kid {key_id!r} duplicates published RSA material"
            )
        published_material.add(material)
        keys.append(sanitized)
    return {"keys": keys}


def _verification_key(token: str):
    settings = get_settings()
    if settings.auth_signing_algorithm == "HS256":
        return settings.auth_secret_key
    header = jwt.get_unverified_header(token)
    key_id = header.get("kid")
    for key in jwt.PyJWKSet.from_dict(public_jwks()).keys:
        if key.key_id == key_id:
            return key.key
    raise ValueError("unknown signing key")


def decode_access_token(token: str) -> CurrentUser:
    try:
        _require_canonical_jwt(token)
        settings = get_settings()
        claims = jwt.decode(
            token,
            _verification_key(token),
            algorithms=[settings.auth_signing_algorithm],
            options={"require": ["sub", "role", "email", "exp"]},
        )
        if claims["role"] not in {"member", "editor", "admin"}:
            raise ValueError("invalid role")
        return CurrentUser(id=str(UUID(claims["sub"])), role=claims["role"], email=claims["email"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=actual_salt, n=2**14, r=8, p=1)
    return f"scrypt${_b64encode(actual_salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        candidate = hash_password(password, salt=_b64decode(salt)).rsplit("$", 1)[1]
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def _bearer_token(authorization: str | None, cookie_token: str | None) -> str | None:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return cookie_token


async def get_optional_user(
    authorization: str | None = Header(default=None),
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> CurrentUser | None:
    token = _bearer_token(authorization, access_cookie)
    return decode_access_token(token) if token else None


async def _resolve_active_user(session: AsyncSession, claims: CurrentUser) -> CurrentUser:
    from orna_atlas.app.modules.users import repository

    user = await repository.get_by_id(session, UUID(claims.id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")
    return CurrentUser(id=str(user.id), role=user.role, email=user.email)


async def get_optional_active_user(
    claims: CurrentUser | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser | None:
    return await _resolve_active_user(session, claims) if claims is not None else None


async def get_current_user(
    current_user: CurrentUser | None = Depends(get_optional_active_user),
) -> CurrentUser:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


async def get_current_admin(
    claims: CurrentUser | None = Depends(get_optional_user),
    x_orna_admin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    settings = get_settings()
    if claims is None and settings.local_admin_enabled and x_orna_admin == "local":
        return CurrentUser(id="local-admin", role="admin", email="local@orna.invalid")
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    current_user = await _resolve_active_user(session, claims)
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user
