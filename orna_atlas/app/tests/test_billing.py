import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from orna_atlas.app.core.config import Settings
from orna_atlas.app.modules.admin.context import build_admin_etag
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    ServiceUnavailableError,
    ValidationError,
)
from orna_atlas.app.integrations.bereke import (
    BerekeCallback,
    BerekeHostedCheckoutClient,
    HostedCheckout,
    parse_callback,
    sign_callback,
)
from orna_atlas.app.main import app
from orna_atlas.app.modules.billing import repository as billing_repository
from orna_atlas.app.modules.billing import service
from orna_atlas.app.modules.billing.schemas import AdminBillingOfferCreate
from orna_atlas.app.modules.billing.router import _read_callback_pairs, bereke_callback


@pytest.fixture(autouse=True)
def _lock_active_checkout_user(monkeypatch) -> None:
    monkeypatch.setattr(
        service.users_repository,
        "get_by_id_for_update",
        AsyncMock(return_value=SimpleNamespace(is_active=True)),
    )
    monkeypatch.setattr(
        service.repository,
        "get_active_offer",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                product_code="lifetime_member",
                version=1,
                amount_minor=1000,
                currency="USD",
                is_active=True,
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        service.memberships_repository,
        "upsert_grant",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        raising=False,
    )
    monkeypatch.setattr(
        service.memberships_repository,
        "revoke_grant",
        AsyncMock(return_value=True),
        raising=False,
    )
    monkeypatch.setattr(
        service.memberships_repository,
        "has_active_grant",
        AsyncMock(return_value=False),
        raising=False,
    )


@pytest.mark.asyncio
async def test_offer_uses_active_database_price(monkeypatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        service.repository,
        "get_active_offer",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(), version=3, amount_minor=2750, currency="KZT"
            )
        ),
    )

    offer = await service.public_offer(db, Settings(_env_file=None))

    assert offer.product_code == "lifetime_member"
    assert offer.amount_minor == 2750
    assert offer.currency == "KZT"
    assert offer.is_recurring is False


@pytest.mark.asyncio
async def test_offer_uses_explicit_two_tenge_template_price_in_test_mode() -> None:
    offer = await service.public_offer(
        AsyncMock(), Settings(_env_file=None, BILLING_TEST_MODE=True)
    )

    assert offer.amount_minor == 200
    assert offer.currency == "KZT"
    assert offer.is_recurring is False


@pytest.mark.asyncio
async def test_admin_offer_replacement_versions_and_deactivates_current(monkeypatch) -> None:
    current = SimpleNamespace(
        id=uuid4(),
        product_code="lifetime_member",
        version=3,
        amount_minor=2750,
        currency="KZT",
        is_active=True,
        updated_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.add = MagicMock()
    monkeypatch.setattr(service.repository, "get_active_offer", AsyncMock(return_value=current))
    monkeypatch.setattr(service.repository, "next_offer_version", AsyncMock(return_value=4))
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    offer = await service.replace_active_offer(
        db,
        AdminBillingOfferCreate(amount_minor=3250, currency="KZT"),
        if_match=build_admin_etag(resource_id=current.id, updated_at=current.updated_at),
        actor_user_id=uuid4(),
        actor_mode=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert current.is_active is False
    assert offer.version == 4
    assert offer.amount_minor == 3250
    assert offer.currency == "KZT"
    assert offer.is_active is True
    service.repository.get_active_offer.assert_awaited_once_with(db, for_update=True)
    service.add_audit_event.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_offer_replacement_returns_stale_precondition(monkeypatch) -> None:
    replacement = SimpleNamespace(
        id=uuid4(),
        product_code="lifetime_member",
        version=4,
        amount_minor=3250,
        currency="KZT",
        is_active=True,
        updated_at=datetime.now(UTC),
    )
    db = AsyncMock()
    get_active_offer = AsyncMock(side_effect=[None, replacement])
    audit_event = AsyncMock()
    monkeypatch.setattr(service.repository, "get_active_offer", get_active_offer)
    monkeypatch.setattr(service, "add_audit_event", audit_event)

    with pytest.raises(HTTPException) as exc_info:
        await service.replace_active_offer(
            db,
            AdminBillingOfferCreate(amount_minor=4000, currency="KZT"),
            if_match=build_admin_etag(
                resource_id=uuid4(), updated_at=replacement.updated_at
            ),
            actor_user_id=uuid4(),
            actor_mode=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert exc_info.value.status_code == 412
    assert get_active_offer.await_args_list == [
        call(db, for_update=True),
        call(db, for_update=True),
    ]
    audit_event.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_bereke_callback_signature_uses_sorted_gateway_fields() -> None:
    parameters = {
        "status": "1",
        "mdOrder": "order-1",
        "operation": "deposited",
        "orderNumber": "orna-1",
    }

    assert sign_callback(parameters, "callback-secret") == (
        "3B49A9EE4800F57FD0C2D2F7FAE249C66ABAF7F72196285BDF62BD4481C5DED1"
    )
    assert sign_callback({**parameters, "status": "0"}, "callback-secret") != sign_callback(
        parameters, "callback-secret"
    )


@pytest.mark.asyncio
async def test_callback_rejects_oversized_body_before_parsing() -> None:
    body = b"payload=" + (b"x" * 16_384)
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/callbacks/bereke",
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        },
        receive,
    )

    with pytest.raises(ValidationError, match="too large"):
        await _read_callback_pairs(request)


@pytest.mark.asyncio
async def test_callback_rejects_excessive_parameter_count() -> None:
    query = "&".join(f"p{index}=x" for index in range(33)).encode()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/callbacks/bereke",
            "query_string": query,
            "headers": [],
        }
    )

    with pytest.raises(ValidationError, match="too many"):
        await _read_callback_pairs(request)


def test_bereke_callback_rejects_invalid_signature() -> None:
    with pytest.raises(AuthenticationError, match="signature"):
        parse_callback(
            {
                "mdOrder": "order-1",
                "orderNumber": "orna-1",
                "operation": "deposited",
                "status": "1",
                "checksum": "invalid",
            },
            "callback-secret",
            {"orderNumber": "orna-1", "amount": 1000, "currency": "840"},
        )


@pytest.mark.parametrize("field", ["mdOrder", "orderNumber"])
def test_bereke_callback_rejects_null_identifiers(field: str) -> None:
    parameters = {
        "mdOrder": "order-1",
        "orderNumber": "orna-1",
        "operation": "deposited",
        "status": "1",
    }
    parameters[field] = ""
    parameters["checksum"] = sign_callback(parameters, "callback-secret")

    with pytest.raises(ValidationError, match="identifiers"):
        parse_callback(
            parameters,
            "callback-secret",
            {"orderNumber": "orna-1", "amount": 1000, "currency": "840"},
        )


def test_bereke_paid_callback_uses_verified_order_status() -> None:
    parameters = {
        "mdOrder": "order-1",
        "orderNumber": "orna-1",
        "operation": "deposited",
        "status": "1",
    }
    parameters["checksum"] = sign_callback(parameters, "callback-secret")

    callback = parse_callback(
        parameters,
        "callback-secret",
        {
            "orderNumber": "orna-1",
            "orderStatus": 2,
            "amount": 1000,
            "currency": "840",
            "depositedDate": 1785402000000,
        },
    )

    assert callback is not None
    assert callback.merchant_reference == "orna-1"
    assert callback.provider_order_id == "order-1"
    assert callback.status == "paid"
    assert callback.amount_minor == 1000
    assert callback.currency == "USD"
    assert callback.occurred_at == datetime.fromtimestamp(1785402000, tz=UTC)


def test_bereke_callback_rejects_mismatched_verified_order() -> None:
    parameters = {
        "mdOrder": "order-1",
        "orderNumber": "orna-1",
        "operation": "deposited",
        "status": "1",
    }
    parameters["checksum"] = sign_callback(parameters, "callback-secret")

    with pytest.raises(ValidationError, match="order"):
        parse_callback(
            parameters,
            "callback-secret",
            {"orderNumber": "other-order", "amount": 1000, "currency": "840"},
        )


def test_bereke_callback_ignores_non_final_hold() -> None:
    parameters = {
        "mdOrder": "order-1",
        "orderNumber": "orna-1",
        "operation": "approved",
        "status": "1",
    }
    parameters["checksum"] = sign_callback(parameters, "callback-secret")

    assert parse_callback(parameters, "callback-secret", None) is None


@pytest.mark.asyncio
async def test_bereke_callback_stays_available_when_new_checkout_is_disabled() -> None:
    parameters = {
        "mdOrder": "order-1",
        "orderNumber": "orna-1",
        "operation": "approved",
        "status": "1",
    }
    parameters["checksum"] = sign_callback(parameters, "callback-secret-value-that-is-long")
    settings = Settings(
        _env_file=None,
        BILLING_ENABLED=False,
        BILLING_FRONTEND_URL="https://orna.land/membership",
        BEREKE_CHECKOUT_CREATE_URL=(
            "https://securepayments.berekebank.kz/payment/rest/register.do"
        ),
        BEREKE_MERCHANT_ID="merchant-1",
        BEREKE_API_KEY="api-token",
        BEREKE_CALLBACK_SECRET="callback-secret-value-that-is-long",
        BEREKE_CALLBACK_URL="https://orna.land/api/v1/billing/callbacks/bereke",
        BEREKE_CHECKOUT_HOSTS=["securepayments.berekebank.kz"],
    )

    assert await BerekeHostedCheckoutClient(settings).resolve_callback(parameters) is None


@pytest.mark.asyncio
async def test_bereke_checkout_uses_form_contract_and_maps_hosted_url(monkeypatch) -> None:
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "orderId": "order-1",
            "formUrl": (
                "https://securepayments.berekebank.kz/payment/merchants/orna/payment_en.html"
                "?mdOrder=order-1"
            ),
        },
    )
    post = AsyncMock(return_value=response)
    client_context = AsyncMock()
    client_context.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr(
        "orna_atlas.app.integrations.bereke.httpx.AsyncClient",
        lambda **_kwargs: client_context,
    )
    settings = Settings(
        _env_file=None,
        BILLING_ENABLED=True,
        BILLING_FRONTEND_URL="https://orna.land/membership",
        BEREKE_CHECKOUT_CREATE_URL=(
            "https://securepayments.berekebank.kz/payment/rest/register.do"
        ),
        BEREKE_MERCHANT_ID="merchant-1",
        BEREKE_API_KEY="api-token",
        BEREKE_CALLBACK_SECRET="a" * 32,
        BEREKE_CALLBACK_URL="https://orna.land/api/v1/billing/callbacks/bereke",
        BEREKE_CHECKOUT_HOSTS=["securepayments.berekebank.kz"],
    )

    result = await BerekeHostedCheckoutClient(settings).create_checkout(
        merchant_reference="orna-1",
        amount_minor=1000,
        currency="USD",
        description="Lifetime Member Access",
    )

    assert result.provider_order_id == "order-1"
    request_data = post.await_args.kwargs["data"]
    assert request_data == {
        "token": "api-token",
        "orderNumber": "orna-1",
        "amount": "1000",
        "currency": "840",
        "description": "Lifetime Member Access",
        "returnUrl": "https://orna.land/membership?payment_return=orna-1",
        "failUrl": "https://orna.land/membership?payment_return=orna-1",
    }


@pytest.mark.asyncio
async def test_bereke_test_checkout_registers_unique_order_from_template(monkeypatch) -> None:
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "orderId": "template-order-1",
            "formUrl": (
                "https://securepayments.berekebank.kz/payment/merchants/livecom/payment_en.html"
                "?mdOrder=template-order-1"
            ),
        },
    )
    post = AsyncMock(return_value=response)
    client_context = AsyncMock()
    client_context.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr(
        "orna_atlas.app.integrations.bereke.httpx.AsyncClient",
        lambda **_kwargs: client_context,
    )
    settings = Settings(
        _env_file=None,
        BILLING_ENABLED=True,
        BILLING_TEST_MODE=True,
        BILLING_FRONTEND_URL="https://orna.land/membership",
        BEREKE_CHECKOUT_CREATE_URL=(
            "https://securepayments.berekebank.kz/payment/rest/registerByTemplate.do"
        ),
        BEREKE_TEMPLATE_ID="xcyUoLEOVERqvOjP",
        BEREKE_CALLBACK_SECRET="a" * 32,
        BEREKE_CALLBACK_URL="https://orna.land/api/v1/billing/callbacks/bereke",
        BEREKE_CHECKOUT_HOSTS=["securepayments.berekebank.kz"],
    )

    result = await BerekeHostedCheckoutClient(settings).create_checkout(
        merchant_reference="orna-1",
        amount_minor=200,
        currency="KZT",
        description="ORNA Atlas test checkout",
        customer_email="member@example.com",
    )

    assert result.provider_order_id == "template-order-1"
    assert post.await_args.kwargs["json"] == {
        "templateId": "xcyUoLEOVERqvOjP",
        "language": "en",
        "amount": 200,
        "currency": "KZT",
        "addParams": {"email": "member@example.com"},
    }


@pytest.mark.asyncio
async def test_bereke_template_callback_uses_signed_operation_without_api_status(monkeypatch) -> None:
    secret = "callback-secret-value-that-is-long"
    parameters = {
        "mdOrder": "template-order-1",
        "orderNumber": "generated-provider-number",
        "operation": "deposited",
        "status": "1",
    }
    parameters["checksum"] = sign_callback(parameters, secret)
    settings = Settings(
        _env_file=None,
        BILLING_ENABLED=True,
        BILLING_TEST_MODE=True,
        BEREKE_CHECKOUT_CREATE_URL=(
            "https://securepayments.berekebank.kz/payment/rest/registerByTemplate.do"
        ),
        BEREKE_TEMPLATE_ID="xcyUoLEOVERqvOjP",
        BEREKE_CALLBACK_SECRET=secret,
        BEREKE_CALLBACK_URL="https://orna.land/api/v1/billing/callbacks/bereke",
        BEREKE_CHECKOUT_HOSTS=["securepayments.berekebank.kz"],
    )
    monkeypatch.setattr(
        "orna_atlas.app.integrations.bereke.httpx.AsyncClient",
        lambda **_kwargs: pytest.fail("template callback must not call authenticated status API"),
    )

    callback = await BerekeHostedCheckoutClient(settings).resolve_callback(parameters)

    assert callback is not None
    assert callback.match_by_provider_order is True
    assert callback.provider_order_id == "template-order-1"
    assert callback.amount_minor == 200
    assert callback.currency == "KZT"


@pytest.mark.asyncio
async def test_bereke_callback_route_accepts_posted_form(monkeypatch) -> None:
    callback_client = SimpleNamespace(resolve_callback=AsyncMock(return_value=None))
    monkeypatch.setattr(
        "orna_atlas.app.modules.billing.router.BerekeHostedCheckoutClient",
        lambda _settings: callback_client,
    )
    body = b"mdOrder=order-1&orderNumber=orna-1&operation=approved&status=1&checksum=signed"
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
            "path": "/api/v1/billing/callbacks/bereke",
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        },
        receive,
    )

    response = await bereke_callback(request, AsyncMock(), SimpleNamespace())

    assert response.status_code == 204
    callback_client.resolve_callback.assert_awaited_once_with(
        {
            "mdOrder": "order-1",
            "orderNumber": "orna-1",
            "operation": "approved",
            "status": "1",
            "checksum": "signed",
        }
    )


@pytest.mark.asyncio
async def test_bereke_callback_route_rejects_duplicate_parameters() -> None:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/billing/callbacks/bereke",
            "query_string": b"status=1&status=0",
            "headers": [],
        },
        receive,
    )

    with pytest.raises(ValidationError, match="Duplicate"):
        await bereke_callback(request, AsyncMock(), SimpleNamespace())


def test_billing_openapi_exposes_only_customer_contracts() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/billing/offer" in paths
    assert "/api/v1/billing/checkouts" in paths
    assert "/api/v1/billing/purchases/me" in paths
    assert "/api/v1/billing/callbacks/bereke" not in paths


def test_enabled_billing_requires_complete_provider_configuration() -> None:
    with pytest.raises(ValueError, match="BEREKE_CHECKOUT_CREATE_URL"):
        Settings(_env_file=None, BILLING_ENABLED=True)


def test_configured_callback_secret_is_strong_while_checkout_is_disabled() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(_env_file=None, BEREKE_CALLBACK_SECRET="short")


@pytest.mark.asyncio
async def test_disabled_checkout_does_not_persist_purchase(monkeypatch) -> None:
    user_id = uuid4()
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "create_purchase", AsyncMock())

    with pytest.raises(ServiceUnavailableError, match="checkout"):
        await service.create_checkout(
            db, user_id, "request-disabled", AsyncMock(), Settings(_env_file=None)
        )

    service.repository.create_purchase.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_requires_verified_email(monkeypatch) -> None:
    user_id = uuid4()
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=False)),
    )

    with pytest.raises(ForbiddenError, match="verified email"):
        await service.create_checkout(
            db, user_id, "request-1", AsyncMock(), Settings(_env_file=None)
        )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_retry_returns_same_private_hosted_url(monkeypatch) -> None:
    user_id = uuid4()
    purchase_id = uuid4()
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.repository,
        "get_by_idempotency",
        AsyncMock(return_value=SimpleNamespace(
            id=purchase_id,
            merchant_reference="orna-existing",
            status="pending",
            checkout_url="https://checkout.example/order",
            checkout_expires_at=None,
        )),
    )

    result = await service.create_checkout(
        db, user_id, "request-1", AsyncMock(), SimpleNamespace(billing_enabled=True)
    )

    assert result.purchase_id == purchase_id
    assert result.checkout_url == "https://checkout.example/order"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_retry_expires_stale_hosted_url(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-expired",
        status="pending",
        checkout_url="https://checkout.example/expired",
        checkout_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=purchase))

    result = await service.create_checkout(
        db, user_id, "request-expired", AsyncMock(), SimpleNamespace(billing_enabled=True)
    )

    assert result.status == "expired"
    assert result.checkout_url is None
    assert purchase.status == "expired"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_purchase_history_expires_stale_hosted_checkout(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-expired-history",
        product_code="lifetime_member",
        amount_minor=1000,
        currency="USD",
        status="pending",
        checkout_url="https://checkout.example/expired",
        checkout_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        paid_at=None,
        refunded_at=None,
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db = AsyncMock()
    monkeypatch.setattr(service, "require_user", AsyncMock())
    monkeypatch.setattr(service.repository, "list_for_user", AsyncMock(return_value=[purchase]))

    result = await service.list_purchases(db, user_id)

    assert result[0].status == "expired"
    assert purchase.checkout_url is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_different_key_reuses_in_flight_checkout(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-open",
        status="creating",
        checkout_url=None,
        checkout_expires_at=None,
    )
    db = AsyncMock()
    provider = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.repository, "get_open_for_user", AsyncMock(return_value=purchase), raising=False
    )
    monkeypatch.setattr(service.repository, "create_purchase", AsyncMock())

    result = await service.create_checkout(
        db, user_id, "request-other", provider, SimpleNamespace(billing_enabled=True)
    )

    assert result.purchase_id == purchase.id
    assert result.status == "creating"
    provider.create_checkout.assert_not_awaited()
    service.repository.create_purchase.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_retry_recovers_provider_call_left_in_creating(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-existing",
        status="creating",
        provider_order_id=None,
        checkout_url=None,
        checkout_expires_at=None,
        amount_minor=1750,
        currency="KZT",
    )
    db = AsyncMock()
    provider = AsyncMock()
    provider.create_checkout.return_value = HostedCheckout(
        provider_order_id="order-1",
        checkout_url="https://checkout.example/order",
    )
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=purchase))

    result = await service.create_checkout(
        db, user_id, "request-1", provider, SimpleNamespace(billing_enabled=True)
    )

    assert result.status == "pending"
    assert purchase.provider_order_id == "order-1"
    provider.create_checkout.assert_awaited_once()
    assert provider.create_checkout.await_args.kwargs["amount_minor"] == 1750
    assert provider.create_checkout.await_args.kwargs["currency"] == "KZT"
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_checkout_provider_error_marks_outcome_unknown_without_blind_retry(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-unknown",
        status="creating",
        provider_order_id=None,
        checkout_url=None,
        checkout_expires_at=None,
        amount_minor=1000,
        currency="USD",
    )
    db = AsyncMock()
    provider = AsyncMock()
    provider.create_checkout.side_effect = RuntimeError("response lost")
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_open_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "create_purchase", AsyncMock(return_value=purchase))

    with pytest.raises(RuntimeError, match="response lost"):
        await service.create_checkout(
            db, user_id, "request-unknown", provider, SimpleNamespace(billing_enabled=True)
        )

    assert purchase.status == "provider_outcome_unknown"
    assert db.commit.await_count == 2

    service.repository.get_by_idempotency.return_value = purchase
    provider.reset_mock()
    result = await service.create_checkout(
        db, user_id, "request-unknown", provider, SimpleNamespace(billing_enabled=True)
    )

    assert result.status == "provider_outcome_unknown"
    provider.create_checkout.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_cancellation_cannot_leave_provider_call_retryable(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="orna-cancelled",
        status="creating",
        provider_order_id=None,
        checkout_url=None,
        checkout_expires_at=None,
        amount_minor=1000,
        currency="USD",
    )
    db = AsyncMock()
    provider = AsyncMock()

    async def cancelled(**_kwargs):
        assert purchase.status == "provider_outcome_unknown"
        db.commit.assert_awaited_once()
        raise asyncio.CancelledError

    provider.create_checkout.side_effect = cancelled
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=purchase))

    with pytest.raises(asyncio.CancelledError):
        await service.create_checkout(
            db, user_id, "request-cancelled", provider, SimpleNamespace(billing_enabled=True)
        )

    assert purchase.status == "provider_outcome_unknown"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkout_rejects_any_active_provenance_grant(monkeypatch) -> None:
    user_id = uuid4()
    provider = AsyncMock()
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(
        service.memberships_repository,
        "has_active_grant",
        AsyncMock(return_value=True),
    )

    with pytest.raises(ConflictError, match="already active"):
        await service.create_checkout(
            AsyncMock(), user_id, "request-entitled", provider, SimpleNamespace(billing_enabled=True)
        )

    provider.create_checkout.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_checkout_merchant_reference_fits_bereke_limit(monkeypatch) -> None:
    user_id = uuid4()
    db = AsyncMock()
    provider = AsyncMock()
    provider.create_checkout.return_value = HostedCheckout(
        provider_order_id="order-1",
        checkout_url="https://checkout.example/order",
    )
    purchase = SimpleNamespace(
        id=uuid4(),
        merchant_reference="",
        status="creating",
        provider_order_id=None,
        checkout_url=None,
        checkout_expires_at=None,
    )
    monkeypatch.setattr(
        service,
        "require_user",
        AsyncMock(return_value=SimpleNamespace(id=user_id, email_verified=True)),
    )
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_by_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "get_open_for_user", AsyncMock(return_value=None))

    async def create_purchase(_db, **kwargs):
        purchase.merchant_reference = kwargs["merchant_reference"]
        return purchase

    monkeypatch.setattr(service.repository, "create_purchase", create_purchase)

    await service.create_checkout(
        db, user_id, "request-new", provider, SimpleNamespace(billing_enabled=True)
    )

    reference = provider.create_checkout.await_args.kwargs["merchant_reference"]
    assert reference.startswith("orna-")
    assert len(reference) == 36


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["pending", "provider_outcome_unknown"])
async def test_paid_callback_activates_lifetime_membership_once(
    monkeypatch, initial_status
) -> None:
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=initial_status,
        provider_order_id=None if initial_status == "provider_outcome_unknown" else "order-1",
        amount_minor=1000,
        currency="USD",
        paid_at=None,
        refunded_at=None,
    )
    db = AsyncMock()
    monkeypatch.setattr(service.repository, "event_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(
        service.repository,
        "get_by_merchant_reference_for_update",
        AsyncMock(return_value=purchase),
    )
    monkeypatch.setattr(service.repository, "add_event", AsyncMock())
    monkeypatch.setattr(
        service.memberships_repository, "get_for_user", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        service.memberships_repository,
        "upsert",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())
    callback = BerekeCallback(
        event_id="evt-1",
        merchant_reference="orna-1",
        provider_order_id="order-1",
        status="paid",
        amount_minor=1000,
        currency="USD",
        occurred_at=datetime.now(UTC),
    )

    result = await service.apply_callback(db, callback)

    assert result is purchase
    assert purchase.status == "paid"
    assert purchase.provider_order_id == "order-1"
    membership_update = service.memberships_repository.upsert.await_args.args[2]
    assert membership_update.status == "active"
    assert membership_update.expires_at is None
    service.memberships_repository.upsert_grant.assert_awaited_once_with(
        db,
        purchase.user_id,
        source_type="billing_purchase",
        source_id=purchase.id,
        plan="lifetime_member",
        expires_at=None,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_template_callback_matches_purchase_by_signed_provider_order(monkeypatch) -> None:
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status="pending",
        provider_order_id="template-order-1",
        amount_minor=200,
        currency="KZT",
        paid_at=None,
        refunded_at=None,
    )
    db = AsyncMock()
    monkeypatch.setattr(
        service.repository,
        "get_by_provider_order_id_for_update",
        AsyncMock(return_value=purchase),
        raising=False,
    )
    monkeypatch.setattr(service.repository, "event_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(service.repository, "add_event", AsyncMock())
    monkeypatch.setattr(service.memberships_repository, "get_for_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.memberships_repository,
        "upsert",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())
    callback = BerekeCallback(
        event_id="evt-template-1",
        merchant_reference="provider-generated-reference",
        provider_order_id="template-order-1",
        status="paid",
        amount_minor=200,
        currency="KZT",
        occurred_at=datetime.now(UTC),
        match_by_provider_order=True,
    )

    await service.apply_callback(db, callback)

    service.repository.get_by_provider_order_id_for_update.assert_awaited_once_with(
        db, "template-order-1"
    )
    assert purchase.status == "paid"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_amount_mismatch_fails_closed(monkeypatch) -> None:
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status="pending",
        provider_order_id="order-1",
        amount_minor=1000,
        currency="USD",
    )
    db = AsyncMock()
    monkeypatch.setattr(service.repository, "event_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(
        service.repository,
        "get_by_merchant_reference_for_update",
        AsyncMock(return_value=purchase),
    )
    callback = BerekeCallback(
        event_id="evt-2",
        merchant_reference="orna-1",
        provider_order_id="order-1",
        status="paid",
        amount_minor=999,
        currency="USD",
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(ConflictError, match="amount or currency"):
        await service.apply_callback(db, callback)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_request_locks_purchase_before_status_change(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        merchant_reference="orna-paid",
        status="paid",
        paid_at=datetime.now(UTC) - timedelta(days=1),
    )
    refund = SimpleNamespace(id=uuid4(), purchase_id=purchase.id, status="requested", created_at=datetime.now(UTC))
    db = AsyncMock()
    monkeypatch.setattr(service, "require_user", AsyncMock())
    locked_read = AsyncMock(return_value=purchase)
    monkeypatch.setattr(
        service.repository, "get_for_user_for_update", locked_read, raising=False
    )
    monkeypatch.setattr(service.repository, "get_for_user", AsyncMock(return_value=purchase))
    monkeypatch.setattr(service.repository, "get_refund_request", AsyncMock(return_value=None))
    monkeypatch.setattr(service.repository, "create_refund_request", AsyncMock(return_value=refund))
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    await service.request_refund(db, user_id, purchase.id)

    locked_read.assert_awaited_once_with(db, purchase.id, user_id)
    service.repository.get_for_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_request_rejects_purchase_after_fourteen_days(monkeypatch) -> None:
    user_id = uuid4()
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        merchant_reference="orna-old-paid",
        status="paid",
        paid_at=datetime.now(UTC) - timedelta(days=15),
    )
    db = AsyncMock()
    monkeypatch.setattr(service, "require_user", AsyncMock())
    monkeypatch.setattr(
        service.repository, "get_for_user_for_update", AsyncMock(return_value=purchase)
    )
    monkeypatch.setattr(service.repository, "get_refund_request", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service.repository,
        "create_refund_request",
        AsyncMock(return_value=SimpleNamespace(
            id=uuid4(), purchase_id=purchase.id, status="requested", created_at=datetime.now(UTC)
        )),
    )
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    with pytest.raises(ConflictError, match="14 calendar days"):
        await service.request_refund(db, user_id, purchase.id)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_callback_revokes_payment_backed_membership(monkeypatch) -> None:
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status="refund_requested",
        provider_order_id="order-1",
        amount_minor=1000,
        currency="USD",
        refunded_at=None,
    )
    membership = SimpleNamespace(plan="lifetime_member")
    refund = SimpleNamespace(status="requested")
    db = AsyncMock()
    monkeypatch.setattr(
        service.repository,
        "get_by_merchant_reference_for_update",
        AsyncMock(return_value=purchase),
    )
    monkeypatch.setattr(service.repository, "event_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(service.repository, "get_refund_request", AsyncMock(return_value=refund))
    monkeypatch.setattr(
        service.repository,
        "has_other_payment_backed_purchase",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(service.repository, "add_event", AsyncMock())
    monkeypatch.setattr(
        service.memberships_repository, "get_for_user", AsyncMock(return_value=membership)
    )
    monkeypatch.setattr(service.memberships_repository, "upsert", AsyncMock())
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())
    callback = BerekeCallback(
        event_id="evt-refund-1",
        merchant_reference="orna-1",
        provider_order_id="order-1",
        status="refunded",
        amount_minor=1000,
        currency="USD",
        occurred_at=datetime.now(UTC),
    )

    await service.apply_callback(db, callback)

    assert purchase.status == "refunded"
    assert refund.status == "completed"
    service.memberships_repository.revoke_grant.assert_awaited_once_with(
        db, source_type="billing_purchase", source_id=purchase.id
    )
    membership_update = service.memberships_repository.upsert.await_args.args[2]
    assert membership_update.status == "cancelled"
    service.add_audit_event.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_requested_purchase_remains_payment_backed() -> None:
    result = SimpleNamespace(scalar_one=lambda: 1)
    db = AsyncMock()
    db.execute.return_value = result

    assert await billing_repository.has_other_payment_backed_purchase(
        db, uuid4(), uuid4()
    )

    statement = db.execute.await_args.args[0]
    status_values = next(
        value for value in statement.compile().params.values() if isinstance(value, (list, tuple))
    )
    assert set(status_values) == {"paid", "refund_requested"}
