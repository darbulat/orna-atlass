import asyncio
from dataclasses import dataclass
from email.message import EmailMessage
import hashlib
import json
import secrets
import smtplib
import ssl
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID

from redis.exceptions import RedisError

from orna_atlas.app.core.async_utils import finish_cancelled_compensation
from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ServiceUnavailableError
from orna_atlas.app.integrations.redis import get_redis_client

AccountTokenKind = Literal["email_verification", "password_reset"]
EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = 60 * 60
_TOKEN_PREFIX = "auth:"

_PREPARE_TOKEN_SCRIPT = """
-- account_token_prepare_v3
local version = redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[2])
local ok, payload = pcall(cjson.decode, ARGV[1])
if not ok or type(payload) ~= 'table' then return {0, '', ''} end
payload.issue_version = tostring(version)
payload.state = 'pending'
local stored = redis.call('SET', KEYS[1], cjson.encode(payload), 'EX', ARGV[2], 'NX')
if not stored then return {0, '', ''} end
local previous = redis.call('GET', KEYS[3]) or ''
return {1, tostring(version), previous}
"""

_ACTIVATE_TOKEN_SCRIPT = """
-- account_token_activate_v3
local stored = redis.call('GET', KEYS[1])
if not stored then return 0 end
local ok, payload = pcall(cjson.decode, stored)
if not ok or type(payload) ~= 'table' or payload.issue_version ~= ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 0
end
if payload.state == 'active' or payload.state == 'claimed'
    or payload.state == 'finalized' then
  if redis.call('GET', KEYS[2]) == ARGV[2] then return 1 end
  return 0
end
if payload.state ~= 'pending' then redis.call('DEL', KEYS[1]); return 0 end
local current_digest = redis.call('GET', KEYS[2]) or ''
if current_digest ~= '' and current_digest ~= ARGV[2] then
  local current_key = ARGV[3] .. current_digest
  local current_stored = redis.call('GET', current_key)
  if current_stored then
    local current_ok, current_payload = pcall(cjson.decode, current_stored)
    if current_ok and type(current_payload) == 'table'
        and tonumber(current_payload.issue_version) > tonumber(payload.issue_version) then
      redis.call('DEL', KEYS[1])
      return 0
    end
  end
end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return 0 end
payload.state = 'active'
redis.call('SET', KEYS[1], cjson.encode(payload), 'PX', ttl, 'XX')
redis.call('SET', KEYS[2], ARGV[2], 'PX', ttl)
if current_digest ~= '' and current_digest ~= ARGV[2] then
  redis.call('DEL', ARGV[3] .. current_digest)
end
return 1
"""

_ROLLBACK_TOKEN_SCRIPT = """
-- account_token_rollback_v3
local stored = redis.call('GET', KEYS[1])
if not stored then return 1 end
local ok, payload = pcall(cjson.decode, stored)
if not ok or type(payload) ~= 'table'
    or (payload.state ~= 'active' and payload.state ~= 'claimed'
        and payload.state ~= 'finalized') then
  redis.call('DEL', KEYS[1])
end
return 1
"""

_CLAIM_TOKEN_SCRIPT = """
-- account_token_claim_v1
local stored = redis.call('GET', KEYS[1])
if not stored then return {0, ''} end
local ok, payload = pcall(cjson.decode, stored)
if not ok or type(payload) ~= 'table' or type(payload.user_id) ~= 'string' then
  redis.call('DEL', KEYS[1])
  return {-1, ''}
end
local current_key = ARGV[1] .. payload.user_id
if redis.call('GET', current_key) ~= ARGV[2] then
  if payload.state == 'pending' then return {0, ''} end
  redis.call('DEL', KEYS[1])
  return {0, ''}
end
if payload.state == 'claimed' and payload.claim_id == ARGV[3] then
  return {1, stored}
end
if payload.state ~= 'active' then return {0, ''} end
payload.state = 'claimed'
payload.claim_id = ARGV[3]
redis.call('SET', KEYS[1], cjson.encode(payload), 'XX', 'KEEPTTL')
return {1, stored}
"""

_FINALIZE_TOKEN_CLAIM_SCRIPT = """
-- account_token_finalize_claim_v1
local stored = redis.call('GET', KEYS[1])
if not stored then return 0 end
local ok, payload = pcall(cjson.decode, stored)
if not ok or type(payload) ~= 'table' or type(payload.user_id) ~= 'string' then
  return 0
end
local current_key = ARGV[1] .. payload.user_id
if payload.state == 'finalized' then
  if redis.call('GET', current_key) == ARGV[2] then return 1 end
  return 0
end
if payload.state ~= 'claimed' or payload.claim_id ~= ARGV[3] then
  return 0
end
if redis.call('GET', current_key) ~= ARGV[2] then return 0 end
payload.state = 'finalized'
payload.claim_id = nil
redis.call('SET', KEYS[1], cjson.encode(payload), 'XX', 'KEEPTTL')
return 1
"""

_ROLLBACK_TOKEN_CLAIM_SCRIPT = """
-- account_token_rollback_claim_v1
local stored = redis.call('GET', KEYS[1])
if not stored then return 0 end
local ok, payload = pcall(cjson.decode, stored)
if not ok or type(payload) ~= 'table' or payload.state ~= 'claimed'
    or payload.claim_id ~= ARGV[1] then
  return 0
end
payload.state = 'active'
payload.claim_id = nil
redis.call('SET', KEYS[1], cjson.encode(payload), 'XX', 'KEEPTTL')
return 1
"""


@dataclass(frozen=True)
class TokenClaim:
    claim_id: str
    claims: dict[str, str]


async def _eval_idempotent_mutation(
    script: str,
    numkeys: int,
    *args: str,
    abort_on_cancellation: bool = False,
) -> tuple[Any, asyncio.CancelledError | None]:
    cancellation: asyncio.CancelledError | None = None
    last_error: RedisError | None = None
    for _attempt in range(2):
        client = get_redis_client()
        task = asyncio.ensure_future(client.eval(script, numkeys, *args))
        result: Any = None
        succeeded = False
        try:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError as exc:
                    if cancellation is None:
                        cancellation = exc
                    if abort_on_cancellation:
                        task.cancel()
                        break
            if abort_on_cancellation and cancellation is not None:
                try:
                    await task
                except BaseException:
                    pass
                raise cancellation
            result = task.result()
            succeeded = True
        except RedisError as exc:
            last_error = exc
        finally:
            if cancellation is not None:
                await finish_cancelled_compensation(client.aclose())
            else:
                try:
                    await client.aclose()
                except asyncio.CancelledError as exc:
                    cancellation = exc
                    await finish_cancelled_compensation(client.aclose())
                except RedisError:
                    pass
        if succeeded:
            return result, cancellation
        if cancellation is not None:
            raise cancellation
    raise ServiceUnavailableError("Account token service unavailable") from last_error


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _token_key(kind: AccountTokenKind, raw_token: str) -> str:
    return f"{_TOKEN_PREFIX}{kind}:{_token_digest(raw_token)}"


def _token_key_from_digest(kind: AccountTokenKind, digest: str) -> str:
    return f"{_TOKEN_PREFIX}{kind}:{digest}"


def _current_token_key(kind: AccountTokenKind, user_id: UUID | str) -> str:
    return f"{_TOKEN_PREFIX}{kind}:current:{user_id}"


def _current_token_prefix(kind: AccountTokenKind) -> str:
    return f"{_TOKEN_PREFIX}{kind}:current:"


def _token_version_key(kind: AccountTokenKind, user_id: UUID | str) -> str:
    return f"{_token_version_prefix(kind)}{user_id}"


def _token_version_prefix(kind: AccountTokenKind) -> str:
    return f"{_TOKEN_PREFIX}{kind}:version:"


def _fragment_url(settings: Settings, parameter: str, raw_token: str) -> str:
    parsed = urlsplit(settings.oauth_frontend_url)
    fragment = urlencode({parameter: raw_token})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, fragment))


def _send_email(settings: Settings, recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ServiceUnavailableError("Account email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ServiceUnavailableError("Account email delivery failed") from exc


async def _issue_token(
    *,
    settings: Settings,
    kind: AccountTokenKind,
    user_id: UUID,
    email: str,
    ttl_seconds: int,
    subject: str,
    body_builder,
) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ServiceUnavailableError("Account email delivery is not configured")
    raw_token = secrets.token_urlsafe(32)
    digest = _token_digest(raw_token)
    token_key = _token_key(kind, raw_token)
    current_key = _current_token_key(kind, user_id)
    version_key = _token_version_key(kind, user_id)
    payload = json.dumps(
        {"kind": kind, "user_id": str(user_id), "email": email.lower()},
        separators=(",", ":"),
    )
    client = get_redis_client()
    cancellation: asyncio.CancelledError | None = None
    try:
        prepared_result = await client.eval(
            _PREPARE_TOKEN_SCRIPT,
            3,
            token_key,
            version_key,
            current_key,
            payload,
            ttl_seconds,
        )
        if not prepared_result or int(prepared_result[0]) != 1:
            raise AuthenticationError("Account token could not be registered")
        issue_version = str(prepared_result[1])
        send_task = asyncio.create_task(asyncio.to_thread(
            _send_email,
            settings,
            email.lower(),
            subject,
            body_builder(raw_token),
        ))
        try:
            while not send_task.done():
                try:
                    await asyncio.shield(send_task)
                except asyncio.CancelledError as exc:
                    if cancellation is None:
                        cancellation = exc
            send_task.result()
        except BaseException:
            if cancellation is not None:
                await finish_cancelled_compensation(
                    client.eval(_ROLLBACK_TOKEN_SCRIPT, 1, token_key)
                )
                raise cancellation
            await client.eval(_ROLLBACK_TOKEN_SCRIPT, 1, token_key)
            raise
        try:
            activated, activation_cancellation = await _eval_idempotent_mutation(
                _ACTIVATE_TOKEN_SCRIPT,
                2,
                token_key,
                current_key,
                issue_version,
                digest,
                f"{_TOKEN_PREFIX}{kind}:",
            )
        except ServiceUnavailableError:
            await client.eval(_ROLLBACK_TOKEN_SCRIPT, 1, token_key)
            raise
        cancellation = cancellation or activation_cancellation
        if cancellation is not None:
            raise cancellation
        if int(activated or 0) != 1:
            raise ServiceUnavailableError("Account token was superseded before activation")
    except RedisError as exc:
        try:
            await client.eval(_ROLLBACK_TOKEN_SCRIPT, 1, token_key)
        except RedisError:
            pass
        raise ServiceUnavailableError("Account token service unavailable") from exc
    finally:
        if cancellation is not None:
            await finish_cancelled_compensation(client.aclose())
        else:
            try:
                await client.aclose()
            except asyncio.CancelledError as exc:
                cancellation = exc
                await finish_cancelled_compensation(client.aclose())
                raise cancellation
            except RedisError:
                pass


async def send_email_verification(*, settings: Settings, user_id: UUID, email: str) -> None:
    def body(raw_token: str) -> str:
        callback_url = _fragment_url(settings, "verify_email_token", raw_token)
        return (
            "Verify your email address for ORNA Atlas. "
            f"This one-time link expires in 24 hours.\n\n{callback_url}\n\n"
            "If you did not request this, you can ignore this email."
        )

    await _issue_token(
        settings=settings,
        kind="email_verification",
        user_id=user_id,
        email=email,
        ttl_seconds=EMAIL_VERIFICATION_TTL_SECONDS,
        subject="Verify your ORNA Atlas email",
        body_builder=body,
    )


async def send_password_reset(*, settings: Settings, user_id: UUID, email: str) -> None:
    def body(raw_token: str) -> str:
        callback_url = _fragment_url(settings, "reset_password_token", raw_token)
        return (
            "Reset your ORNA Atlas password. "
            f"This one-time link expires in 1 hour.\n\n{callback_url}\n\n"
            "If you did not request this, you can ignore this email."
        )

    await _issue_token(
        settings=settings,
        kind="password_reset",
        user_id=user_id,
        email=email,
        ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
        subject="Reset your ORNA Atlas password",
        body_builder=body,
    )


def _validated_claims(
    expected_kind: AccountTokenKind, serialized_payload: str,
) -> dict[str, str]:
    payload = json.loads(serialized_payload)
    if (
        payload.get("kind") != expected_kind
        or not isinstance(payload.get("user_id"), str)
        or not isinstance(payload.get("email"), str)
    ):
        raise ValueError("invalid account token payload")
    return {
        "kind": expected_kind,
        "user_id": payload["user_id"],
        "email": payload["email"].lower(),
    }


async def claim_token(
    expected_kind: AccountTokenKind, raw_token: str,
) -> TokenClaim | None:
    if not 32 <= len(raw_token) <= 256:
        return None
    digest = _token_digest(raw_token)
    claim_id = secrets.token_urlsafe(16)
    try:
        result, cancellation = await _eval_idempotent_mutation(
            _CLAIM_TOKEN_SCRIPT,
            1,
            _token_key(expected_kind, raw_token),
            _current_token_prefix(expected_kind),
            digest,
            claim_id,
        )
        if cancellation is not None:
            if result and int(result[0]) == 1:
                await finish_cancelled_compensation(
                    _eval_idempotent_mutation(
                        _ROLLBACK_TOKEN_CLAIM_SCRIPT,
                        1,
                        _token_key(expected_kind, raw_token),
                        claim_id,
                        abort_on_cancellation=True,
                    )
                )
            raise cancellation
        if not result or int(result[0]) == 0:
            return None
        if int(result[0]) != 1:
            raise ValueError("invalid account token payload")
        return TokenClaim(
            claim_id=claim_id,
            claims=_validated_claims(expected_kind, result[1]),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Invalid or expired account token") from exc


async def finalize_token_claim(
    expected_kind: AccountTokenKind, raw_token: str, claim_id: str,
) -> bool:
    if not 32 <= len(raw_token) <= 256:
        return False
    digest = _token_digest(raw_token)
    client = get_redis_client()
    try:
        result = await client.eval(
            _FINALIZE_TOKEN_CLAIM_SCRIPT,
            1,
            _token_key(expected_kind, raw_token),
            _current_token_prefix(expected_kind),
            digest,
            claim_id,
        )
        return int(result or 0) == 1
    except RedisError as exc:
        raise ServiceUnavailableError("Account token service unavailable") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass


async def rollback_token_claim(
    expected_kind: AccountTokenKind, raw_token: str, claim_id: str,
) -> bool:
    if not 32 <= len(raw_token) <= 256:
        return False
    client = get_redis_client()
    try:
        result = await client.eval(
            _ROLLBACK_TOKEN_CLAIM_SCRIPT,
            1,
            _token_key(expected_kind, raw_token),
            claim_id,
        )
        return int(result or 0) == 1
    except RedisError as exc:
        raise ServiceUnavailableError("Account token service unavailable") from exc
    finally:
        try:
            await client.aclose()
        except RedisError:
            pass


async def consume_token(
    expected_kind: AccountTokenKind, raw_token: str,
) -> dict[str, str] | None:
    claim = await claim_token(expected_kind, raw_token)
    if claim is None:
        return None
    await finalize_token_claim(expected_kind, raw_token, claim.claim_id)
    return claim.claims
