from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID


class HlsTokenError(ValueError):
    pass


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_hls_token(asset_id: UUID, *, expires_at: datetime, secret: str) -> str:
    expiry = int(expires_at.timestamp())
    payload = f"{asset_id}.{expiry}"
    return f"{expiry}.{_signature(payload, secret)}"


def verify_hls_token(
    token: str,
    asset_id: UUID,
    *,
    secret: str,
    now: datetime | None = None,
) -> int:
    try:
        expiry_text, supplied = token.split(".", 1)
        expiry = int(expiry_text)
    except (ValueError, TypeError) as exc:
        raise HlsTokenError("Malformed HLS token") from exc
    expected = _signature(f"{asset_id}.{expiry}", secret)
    if not hmac.compare_digest(supplied, expected):
        raise HlsTokenError("Invalid HLS token")
    current = int((now or datetime.now(UTC)).timestamp())
    if expiry < current:
        raise HlsTokenError("Expired HLS token")
    return expiry
