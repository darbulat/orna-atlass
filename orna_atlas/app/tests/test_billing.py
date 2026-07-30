from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from orna_atlas.app.core.config import Settings
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
from orna_atlas.app.modules.billing.router import bereke_callback


@pytest.fixture(autouse=True)
def _lock_active_checkout_user(monkeypatch) -> None:
    monkeypatch.setattr(
        service.users_repository,
        "get_by_id_for_update",
        AsyncMock(return_value=SimpleNamespace(is_active=True)),
    )


def test_offer_is_fixed_one_time_usd_price() -> None:
    offer = service.public_offer(Settings(_env_file=None))

    assert offer.product_code == "lifetime_member"
    assert offer.amount_minor == 1000
    assert offer.currency == "USD"
    assert offer.is_recurring is False


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
    db.commit.assert_awaited_once()


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
async def test_paid_callback_activates_lifetime_membership_once(monkeypatch) -> None:
    purchase = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status="pending",
        provider_order_id="order-1",
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
    membership_update = service.memberships_repository.upsert.await_args.args[2]
    assert membership_update.status == "active"
    assert membership_update.expires_at is None
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
