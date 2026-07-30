from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Literal
from urllib.parse import urlsplit

import httpx

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ServiceUnavailableError, ValidationError


CallbackStatus = Literal["paid", "failed", "refunded"]


@dataclass(frozen=True)
class HostedCheckout:
    provider_order_id: str
    checkout_url: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class BerekeCallback:
    event_id: str
    merchant_reference: str
    provider_order_id: str
    status: CallbackStatus
    amount_minor: int
    currency: str
    occurred_at: datetime


def sign_callback(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def parse_callback(body: bytes, signature: str | None, secret: str | None) -> BerekeCallback:
    if not signature or not secret:
        raise AuthenticationError("Invalid Bereke callback signature")
    supplied = signature.removeprefix("sha256=").lower()
    if not hmac.compare_digest(supplied, sign_callback(body, secret)):
        raise AuthenticationError("Invalid Bereke callback signature")
    try:
        payload = json.loads(body)
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            raise ValueError("timezone required")
        callback = BerekeCallback(
            event_id=str(payload["event_id"]),
            merchant_reference=str(payload["merchant_reference"]),
            provider_order_id=str(payload["provider_order_id"]),
            status=payload["status"],
            amount_minor=int(payload["amount_minor"]),
            currency=str(payload["currency"]).upper(),
            occurred_at=occurred_at.astimezone(UTC),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid Bereke callback") from exc
    if callback.status not in {"paid", "failed", "refunded"}:
        raise ValidationError("Invalid Bereke callback status")
    if not all((callback.event_id, callback.merchant_reference, callback.provider_order_id)):
        raise ValidationError("Invalid Bereke callback identifiers")
    return callback


class BerekeHostedCheckoutClient:
    """Narrow adapter for the merchant-specific hosted-checkout contract.

    Bereke supplies the endpoint and credentials during acquiring onboarding. Billing remains
    disabled unless every setting is present, so a missing or incompatible provider contract
    cannot become invented success data.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_checkout(
        self,
        *,
        merchant_reference: str,
        amount_minor: int,
        currency: str,
        description: str,
    ) -> HostedCheckout:
        settings = self.settings
        if not settings.billing_enabled or not all(
            (
                settings.bereke_checkout_create_url,
                settings.bereke_merchant_id,
                settings.bereke_api_key,
                settings.bereke_callback_url,
                settings.billing_frontend_url,
            )
        ):
            raise ServiceUnavailableError("Secure checkout is temporarily unavailable")
        payload = {
            "merchant_id": settings.bereke_merchant_id,
            "merchant_reference": merchant_reference,
            "amount_minor": amount_minor,
            "currency": currency,
            "description": description,
            "return_url": f"{settings.billing_frontend_url}?payment_return={merchant_reference}",
            "callback_url": settings.bereke_callback_url,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    settings.bereke_checkout_create_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.bereke_api_key}",
                        "Idempotency-Key": merchant_reference,
                    },
                )
            response.raise_for_status()
            result = response.json()
            checkout_url = str(result["checkout_url"])
            provider_order_id = str(result["order_id"])
            if not checkout_url or not provider_order_id or provider_order_id == "None":
                raise ValueError("missing checkout identifiers")
            parsed = urlsplit(checkout_url)
            allowed_hosts = set(settings.bereke_checkout_hosts)
            if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in allowed_hosts:
                raise ValueError("untrusted checkout URL")
            expires_at_value = result.get("expires_at")
            expires_at = (
                datetime.fromisoformat(str(expires_at_value).replace("Z", "+00:00"))
                if expires_at_value
                else None
            )
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    raise ValueError("checkout expiry timezone required")
                expires_at = expires_at.astimezone(UTC)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ServiceUnavailableError("Secure checkout is temporarily unavailable") from exc
        return HostedCheckout(
            provider_order_id=provider_order_id,
            checkout_url=checkout_url,
            expires_at=expires_at,
        )
