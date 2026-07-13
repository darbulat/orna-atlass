from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import secrets
from typing import Literal
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, status
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


def create_access_token(user_id: UUID | str, role: Role, email: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.access_token_ttl_seconds)
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {"sub": str(user_id), "role": role, "email": email, "exp": int(expires_at.timestamp())}
    payload = _b64encode(json.dumps(claims, separators=(",", ":")).encode())
    signature = _b64encode(
        hmac.new(settings.auth_secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}", expires_at


def decode_access_token(token: str) -> CurrentUser:
    try:
        header, payload, signature = token.split(".")
        expected = _b64encode(
            hmac.new(
                get_settings().auth_secret_key.encode(),
                f"{header}.{payload}".encode(),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(_b64decode(payload))
        if int(claims["exp"]) <= int(datetime.now(UTC).timestamp()):
            raise ValueError("expired")
        if claims["role"] not in {"member", "editor", "admin"}:
            raise ValueError("invalid role")
        return CurrentUser(id=str(UUID(claims["sub"])), role=claims["role"], email=claims["email"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
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
