from datetime import UTC, datetime
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ConflictError, ForbiddenError
from orna_atlas.app.integrations.bereke import (
    BerekeCallback,
    HostedCheckout,
    parse_callback,
    sign_callback,
)
from orna_atlas.app.main import app
from orna_atlas.app.modules.billing import service


def test_offer_is_fixed_one_time_usd_price() -> None:
    offer = service.public_offer(Settings(_env_file=None))

    assert offer.product_code == "lifetime_member"
    assert offer.amount_minor == 1000
    assert offer.currency == "USD"
    assert offer.is_recurring is False


def test_bereke_callback_signature_covers_exact_body() -> None:
    body = json.dumps({"event_id": "evt-1", "status": "paid"}, separators=(",", ":")).encode()
    signature = sign_callback(body, "callback-secret")

    expected = hmac.new(b"callback-secret", body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, expected)
    assert not hmac.compare_digest(signature, sign_callback(body + b" ", "callback-secret"))


def test_bereke_callback_rejects_invalid_signature() -> None:
    with pytest.raises(AuthenticationError, match="signature"):
        parse_callback(b"{}", "invalid", "callback-secret")


def test_billing_openapi_exposes_only_customer_contracts() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/billing/offer" in paths
    assert "/api/v1/billing/checkouts" in paths
    assert "/api/v1/billing/purchases/me" in paths
    assert "/api/v1/billing/callbacks/bereke" not in paths


def test_enabled_billing_requires_complete_provider_configuration() -> None:
    with pytest.raises(ValueError, match="BEREKE_CHECKOUT_CREATE_URL"):
        Settings(_env_file=None, BILLING_ENABLED=True)


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
        db, user_id, "request-1", AsyncMock(), Settings(_env_file=None)
    )

    assert result.purchase_id == purchase_id
    assert result.checkout_url == "https://checkout.example/order"
    db.commit.assert_not_awaited()


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
        db, user_id, "request-1", provider, Settings(_env_file=None)
    )

    assert result.status == "pending"
    assert purchase.provider_order_id == "order-1"
    provider.create_checkout.assert_awaited_once()
    db.commit.assert_awaited_once()


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
    monkeypatch.setattr(service.repository, "has_other_paid_purchase", AsyncMock(return_value=False))
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
