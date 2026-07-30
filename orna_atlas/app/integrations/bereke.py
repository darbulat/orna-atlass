from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ServiceUnavailableError,
    ValidationError,
)


CallbackStatus = Literal["paid", "failed", "refunded"]
_CURRENCY_TO_NUMERIC = {"USD": "840", "KZT": "398"}
_NUMERIC_TO_CURRENCY = {value: key for key, value in _CURRENCY_TO_NUMERIC.items()}
_IGNORED_OPERATIONS = {"approved", "bindingcreated", "bindingdisabled"}
_FAILED_OPERATIONS = {"reversed", "declinedbytimeout", "cardpresentdeclined"}


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
    match_by_provider_order: bool = False


def _callback_message(parameters: Mapping[str, str]) -> bytes:
    signed = (
        (name, value)
        for name, value in parameters.items()
        if name not in {"checksum", "sign_alias"}
    )
    return "".join(f"{name};{value};" for name, value in sorted(signed)).encode()


def sign_callback(parameters: Mapping[str, str], secret: str) -> str:
    return hmac.new(secret.encode(), _callback_message(parameters), hashlib.sha256).hexdigest().upper()


def _verify_callback_signature(parameters: Mapping[str, str], secret: str | None) -> None:
    signature = parameters.get("checksum")
    if not signature or not secret:
        raise AuthenticationError("Invalid Bereke callback signature")
    if not hmac.compare_digest(signature.upper(), sign_callback(parameters, secret)):
        raise AuthenticationError("Invalid Bereke callback signature")


def _callback_kind(parameters: Mapping[str, str]) -> CallbackStatus | None:
    operation = parameters.get("operation", "").lower()
    status = parameters.get("status")
    if status not in {"0", "1"}:
        raise ValidationError("Invalid Bereke callback status")
    if operation in _IGNORED_OPERATIONS:
        return None
    if status == "0" or operation in _FAILED_OPERATIONS:
        return "failed"
    if operation == "deposited":
        return "paid"
    if operation == "refunded":
        return "refunded"
    return None


def _provider_currency(value: object) -> str:
    normalized = str(value).upper()
    currency = _NUMERIC_TO_CURRENCY.get(normalized, normalized)
    if currency not in {"USD", "KZT"}:
        raise ValidationError("Invalid Bereke order currency")
    return currency


def _occurred_at(provider_order: Mapping[str, Any], status: CallbackStatus) -> datetime:
    timestamp_field = {
        "paid": "depositedDate",
        "refunded": "refundedDate",
        "failed": "declinedDate",
    }[status]
    timestamp = provider_order.get(timestamp_field)
    if timestamp is None:
        return datetime.now(UTC)
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ValidationError("Invalid Bereke order timestamp") from exc


def parse_callback(
    parameters: Mapping[str, str],
    secret: str | None,
    provider_order: Mapping[str, Any] | None,
    *,
    require_deposited_status: bool = True,
    match_by_provider_order: bool = False,
) -> BerekeCallback | None:
    _verify_callback_signature(parameters, secret)
    provider_order_id = parameters.get("mdOrder", "").strip()
    merchant_reference = parameters.get("orderNumber", "").strip()
    if not provider_order_id or not merchant_reference:
        raise ValidationError("Invalid Bereke callback identifiers")
    callback_status = _callback_kind(parameters)
    if callback_status is None:
        return None
    if provider_order is None:
        raise ValidationError("Bereke order status is required")
    if str(provider_order.get("errorCode", "0")) != "0":
        raise ValidationError("Invalid Bereke order status response")
    if str(provider_order.get("orderNumber", "")).strip() != merchant_reference:
        raise ValidationError("Bereke callback order does not match")
    if (
        callback_status == "paid"
        and require_deposited_status
        and int(provider_order.get("orderStatus", -1)) != 2
    ):
        raise ValidationError("Bereke payment is not deposited")
    try:
        amount_minor = int(provider_order["amount"])
        currency = _provider_currency(provider_order["currency"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Invalid Bereke order amount") from exc
    if callback_status == "refunded":
        refunded_amount = provider_order.get("refundedAmount")
        if refunded_amount is not None and int(refunded_amount) < amount_minor:
            return None
    return BerekeCallback(
        event_id=f"bereke:{parameters['checksum'].lower()}",
        merchant_reference=merchant_reference,
        provider_order_id=provider_order_id,
        status=callback_status,
        amount_minor=amount_minor,
        currency=currency,
        occurred_at=_occurred_at(provider_order, callback_status),
        match_by_provider_order=match_by_provider_order,
    )


class BerekeHostedCheckoutClient:
    """Adapter for Bereke's hosted payment gateway REST and callback contracts."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _require_settings(self, *, checkout_enabled: bool) -> Settings:
        settings = self.settings
        common = (
            settings.bereke_checkout_create_url,
            settings.bereke_callback_url,
            settings.bereke_callback_secret,
            settings.billing_frontend_url,
        )
        credentials = (
            (settings.bereke_template_id,)
            if settings.billing_test_mode
            else (settings.bereke_merchant_id, settings.bereke_api_key)
        )
        if (
            (checkout_enabled and not settings.billing_enabled)
            or not all(common)
            or not all(credentials)
        ):
            raise ServiceUnavailableError("Secure checkout is temporarily unavailable")
        return settings

    async def create_checkout(
        self,
        *,
        merchant_reference: str,
        amount_minor: int,
        currency: str,
        description: str,
        customer_email: str | None = None,
    ) -> HostedCheckout:
        settings = self._require_settings(checkout_enabled=True)
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                if settings.billing_test_mode:
                    if amount_minor != 200 or currency != "KZT" or not customer_email:
                        raise ValueError("invalid test template checkout")
                    response = await client.post(
                        settings.bereke_checkout_create_url,
                        json={
                            "templateId": settings.bereke_template_id,
                            "language": "en",
                            "amount": amount_minor,
                            "currency": currency,
                            "addParams": {"email": customer_email},
                        },
                    )
                else:
                    numeric_currency = _CURRENCY_TO_NUMERIC[currency]
                    return_url = (
                        f"{settings.billing_frontend_url}?payment_return={merchant_reference}"
                    )
                    response = await client.post(
                        settings.bereke_checkout_create_url,
                        data={
                            "token": settings.bereke_api_key,
                            "orderNumber": merchant_reference,
                            "amount": str(amount_minor),
                            "currency": numeric_currency,
                            "description": description,
                            "returnUrl": return_url,
                            "failUrl": return_url,
                        },
                    )
            response.raise_for_status()
            result = response.json()
            if result.get("errorCode") not in (None, 0, "0"):
                raise ValueError("provider rejected checkout")
            checkout_url = str(result["formUrl"])
            provider_order_id = str(result["orderId"])
            if not checkout_url or not provider_order_id or provider_order_id == "None":
                raise ValueError("missing checkout identifiers")
            parsed = urlsplit(checkout_url)
            allowed_hosts = set(settings.bereke_checkout_hosts)
            if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in allowed_hosts:
                raise ValueError("untrusted checkout URL")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ServiceUnavailableError("Secure checkout is temporarily unavailable") from exc
        return HostedCheckout(provider_order_id=provider_order_id, checkout_url=checkout_url)

    async def resolve_callback(self, parameters: Mapping[str, str]) -> BerekeCallback | None:
        # Callback verification must remain available when new checkout is disabled.
        settings = self._require_settings(checkout_enabled=False)
        _verify_callback_signature(parameters, settings.bereke_callback_secret)
        if _callback_kind(parameters) is None:
            return None
        if settings.billing_test_mode:
            return parse_callback(
                parameters,
                settings.bereke_callback_secret,
                {
                    "orderNumber": parameters.get("orderNumber"),
                    "amount": 200,
                    "currency": "KZT",
                },
                require_deposited_status=False,
                match_by_provider_order=True,
            )
        provider_order_id = parameters.get("mdOrder", "").strip()
        if not provider_order_id:
            raise ValidationError("Invalid Bereke callback identifiers")
        status_url = urljoin(settings.bereke_checkout_create_url, "getOrderStatusExtended.do")
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.post(
                    status_url,
                    data={"token": settings.bereke_api_key, "orderId": provider_order_id},
                )
            response.raise_for_status()
            provider_order = response.json()
        except (httpx.HTTPError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ServiceUnavailableError("Bereke order verification is temporarily unavailable") from exc
        return parse_callback(
            parameters,
            settings.bereke_callback_secret,
            provider_order,
        )
