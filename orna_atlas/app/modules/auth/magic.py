import asyncio
from email.message import EmailMessage
import hashlib
import json
import secrets
import smtplib
import ssl
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit

from redis.exceptions import RedisError

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ServiceUnavailableError
from orna_atlas.app.integrations.redis import get_redis_client

MAGIC_LINK_TTL_SECONDS = 900
MAGIC_LINK_BROWSER_COOKIE = "orna_magic_browser"


def safe_return_to(value: str | None) -> str:
    decoded = unquote(value) if value else ""
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
    ):
        return "/membership"
    return value.split("#", 1)[0]


def _token_key(raw_token: str) -> str:
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    return f"auth:magic-link:{digest}"


def _browser_nonce_digest(browser_nonce: str) -> str:
    return hashlib.sha256(browser_nonce.encode()).hexdigest()


def _callback_url(settings: Settings, raw_token: str) -> str:
    parsed = urlsplit(settings.magic_link_callback_url)
    query = urlencode({"token": raw_token})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _send_email(settings: Settings, recipient: str, callback_url: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ServiceUnavailableError("Magic-link email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = "Your ORNA Atlas sign-in link"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "Open this one-time link to sign in to ORNA Atlas. "
        f"It expires in 15 minutes.\n\n{callback_url}\n\n"
        "If you did not request this link, you can ignore this email."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ServiceUnavailableError("Magic-link email delivery failed") from exc


async def send_magic_link(
    *, settings: Settings, email: str, return_to: str | None, browser_nonce: str
) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ServiceUnavailableError("Magic-link email delivery is not configured")
    raw_token = secrets.token_urlsafe(32)
    key = _token_key(raw_token)
    transaction = json.dumps(
        {
            "email": email.lower(),
            "return_to": safe_return_to(return_to),
            "browser_nonce_digest": _browser_nonce_digest(browser_nonce),
        },
        separators=(",", ":"),
    )
    client = get_redis_client()
    try:
        stored = await client.set(key, transaction, ex=MAGIC_LINK_TTL_SECONDS, nx=True)
        if not stored:
            raise AuthenticationError("Magic-link token could not be registered")
        try:
            await asyncio.to_thread(_send_email, settings, email.lower(), _callback_url(settings, raw_token))
        except ServiceUnavailableError:
            await client.delete(key)
            raise
    except RedisError as exc:
        raise ServiceUnavailableError("Magic-link state service unavailable") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass


async def consume_magic_link(
    raw_token: str, browser_nonce: str | None
) -> dict[str, str] | None:
    if len(raw_token) > 256 or not browser_nonce or len(browser_nonce) > 256:
        return None
    client = get_redis_client()
    try:
        key = _token_key(raw_token)
        stored = await client.get(key)
        if stored is None:
            return None
        payload = json.loads(stored)
        expected_digest = payload.get("browser_nonce_digest")
        if not isinstance(expected_digest, str) or not secrets.compare_digest(
            expected_digest, _browser_nonce_digest(browser_nonce)
        ):
            return None
        consumed = await client.getdel(key)
        if consumed is None or consumed != stored:
            return None
    except RedisError as exc:
        raise ServiceUnavailableError("Magic-link state service unavailable") from exc
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Invalid or expired magic link") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass
    try:
        payload = json.loads(consumed)
        email = payload.get("email")
        return_to = payload.get("return_to")
        if not isinstance(email, str) or not email or not isinstance(return_to, str):
            raise ValueError("missing magic-link transaction field")
        return {"email": email.lower(), "return_to": safe_return_to(return_to)}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Invalid or expired magic link") from exc
