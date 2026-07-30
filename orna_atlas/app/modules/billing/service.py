from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from orna_atlas.app.integrations.bereke import BerekeCallback, BerekeHostedCheckoutClient
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.billing import repository
from orna_atlas.app.modules.billing.models import BillingPurchase
from orna_atlas.app.modules.billing.schemas import (
    BillingOfferRead,
    CheckoutRead,
    PurchaseRead,
    RefundRequestRead,
)
from orna_atlas.app.modules.memberships import repository as memberships_repository
from orna_atlas.app.modules.memberships.schemas import MembershipUpdate
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.service import require_user


def public_offer(settings: Settings) -> BillingOfferRead:
    amount_minor, currency = _offer_price(settings)
    return BillingOfferRead(
        amount_minor=amount_minor,
        currency=currency,
        checkout_available=settings.billing_enabled,
    )


def _offer_price(settings: Settings) -> tuple[int, str]:
    return (200, "KZT") if getattr(settings, "billing_test_mode", False) else (1000, "USD")


def _purchase_read(purchase: BillingPurchase) -> PurchaseRead:
    return PurchaseRead.model_validate(purchase)


def _checkout_read(purchase: BillingPurchase) -> CheckoutRead:
    return CheckoutRead(
        purchase_id=purchase.id,
        merchant_reference=purchase.merchant_reference,
        status=purchase.status,
        checkout_url=purchase.checkout_url if purchase.status == "pending" else None,
        expires_at=purchase.checkout_expires_at,
    )


def _expire_stale_checkout(purchase: BillingPurchase) -> bool:
    if (
        purchase.status == "pending"
        and purchase.checkout_expires_at is not None
        and purchase.checkout_expires_at <= datetime.now(UTC)
    ):
        purchase.status = "expired"
        purchase.checkout_url = None
        return True
    return False


async def create_checkout(
    db: AsyncSession,
    user_id: UUID,
    idempotency_key: str,
    provider: BerekeHostedCheckoutClient,
    settings: Settings,
) -> CheckoutRead:
    user = await require_user(db, user_id)
    if not user.email_verified:
        raise ForbiddenError("A verified email is required before payment")
    if not settings.billing_enabled:
        raise ServiceUnavailableError("Secure checkout is temporarily unavailable")
    locked_user = await users_repository.get_by_id_for_update(db, user_id)
    if locked_user is None or not locked_user.is_active:
        raise AuthenticationError("User is unavailable")
    membership = await memberships_repository.get_for_user(db, user_id)
    if membership is not None and membership.is_entitled:
        raise ConflictError("Lifetime Member Access is already active")
    amount_minor, currency = _offer_price(settings)
    existing = await repository.get_by_idempotency(db, user_id, idempotency_key)
    if existing is not None:
        if _expire_stale_checkout(existing):
            await db.commit()
            return _checkout_read(existing)
        if existing.status != "creating":
            return _checkout_read(existing)
        purchase = existing
        merchant_reference = existing.merchant_reference
    else:
        open_purchase = await repository.get_open_for_user(db, user_id)
        if open_purchase is not None and not _expire_stale_checkout(open_purchase):
            return _checkout_read(open_purchase)
        # Bereke's hosted gateway limits orderNumber to 36 characters.
        merchant_reference = f"orna-{uuid4().hex[:31]}"
        purchase = await repository.create_purchase(
            db,
            user_id=user_id,
            merchant_reference=merchant_reference,
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            currency=currency,
        )
        await db.commit()
    hosted = await provider.create_checkout(
        merchant_reference=merchant_reference,
        amount_minor=amount_minor,
        currency=currency,
        description="ORNA Atlas Lifetime Member Access",
        customer_email=getattr(user, "email", None),
    )
    purchase.provider_order_id = hosted.provider_order_id
    purchase.checkout_url = hosted.checkout_url
    purchase.checkout_expires_at = hosted.expires_at
    purchase.status = "pending"
    await db.commit()
    return CheckoutRead(
        purchase_id=purchase.id,
        merchant_reference=purchase.merchant_reference,
        status="pending",
        checkout_url=hosted.checkout_url,
        expires_at=hosted.expires_at,
    )


async def list_purchases(db: AsyncSession, user_id: UUID) -> list[PurchaseRead]:
    await require_user(db, user_id)
    purchases = await repository.list_for_user(db, user_id)
    expired_any = False
    for item in purchases:
        expired_any = _expire_stale_checkout(item) or expired_any
    if expired_any:
        await db.commit()
    return [_purchase_read(item) for item in purchases]


async def get_purchase(db: AsyncSession, user_id: UUID, purchase_id: UUID) -> PurchaseRead:
    await require_user(db, user_id)
    purchase = await repository.get_for_user(db, purchase_id, user_id)
    if purchase is None:
        raise NotFoundError("Purchase not found")
    if _expire_stale_checkout(purchase):
        await db.commit()
    return _purchase_read(purchase)


async def request_refund(
    db: AsyncSession, user_id: UUID, purchase_id: UUID
) -> RefundRequestRead:
    await require_user(db, user_id)
    purchase = await repository.get_for_user_for_update(db, purchase_id, user_id)
    if purchase is None:
        raise NotFoundError("Purchase not found")
    if purchase.status not in {"paid", "refund_requested"}:
        raise ConflictError("Only a completed payment can be refunded")
    existing = await repository.get_refund_request(db, purchase_id)
    if existing is not None:
        return RefundRequestRead.model_validate(existing)
    refund = await repository.create_refund_request(db, purchase_id, user_id)
    purchase.status = "refund_requested"
    await add_audit_event(
        db,
        event_type="billing.refund_requested",
        subject_type="billing_purchase",
        subject_id=str(purchase.id),
        actor_user_id=user_id,
        metadata={"merchant_reference": purchase.merchant_reference},
    )
    await db.commit()
    return RefundRequestRead.model_validate(refund)


async def apply_callback(db: AsyncSession, callback: BerekeCallback) -> BillingPurchase:
    if callback.match_by_provider_order:
        purchase = await repository.get_by_provider_order_id_for_update(
            db, callback.provider_order_id
        )
    else:
        purchase = await repository.get_by_merchant_reference_for_update(
            db, callback.merchant_reference
        )
    if purchase is None:
        raise NotFoundError("Purchase not found")
    # The purchase lock serializes callbacks for one order. Rechecking event identity only after
    # acquiring it makes concurrent provider retries idempotent instead of racing the unique key.
    if await repository.event_exists(db, callback.event_id):
        return purchase
    if purchase.provider_order_id != callback.provider_order_id:
        raise ConflictError("Payment order does not match")
    if purchase.amount_minor != callback.amount_minor or purchase.currency != callback.currency:
        raise ConflictError("Payment amount or currency does not match")
    paid_before_expiry = (
        purchase.status == "expired"
        and purchase.checkout_expires_at is not None
        and callback.occurred_at <= purchase.checkout_expires_at
    )
    if callback.status == "paid" and (
        purchase.status in {"creating", "pending", "failed"} or paid_before_expiry
    ):
        purchase.status = "paid"
        purchase.paid_at = callback.occurred_at
        update = MembershipUpdate(status="active", plan="lifetime_member", expires_at=None)
        membership = await memberships_repository.upsert(db, purchase.user_id, update)
        await add_audit_event(
            db,
            event_type="billing.payment_confirmed",
            subject_type="billing_purchase",
            subject_id=str(purchase.id),
            actor_user_id=None,
            metadata={"membership_id": str(membership.id), "provider": "bereke"},
        )
    elif callback.status == "failed" and purchase.status in {"creating", "pending"}:
        purchase.status = "failed"
    elif callback.status == "refunded" and purchase.status != "refunded":
        purchase.status = "refunded"
        purchase.refunded_at = callback.occurred_at
        refund = await repository.get_refund_request(db, purchase.id)
        if refund is not None:
            refund.status = "completed"
        if not await repository.has_other_payment_backed_purchase(
            db, purchase.user_id, purchase.id
        ):
            membership = await memberships_repository.get_for_user(db, purchase.user_id)
            if membership is not None and membership.plan == "lifetime_member":
                update = MembershipUpdate(status="cancelled", plan="lifetime_member", expires_at=None)
                await memberships_repository.upsert(db, purchase.user_id, update)
        await add_audit_event(
            db,
            event_type="billing.refund_confirmed",
            subject_type="billing_purchase",
            subject_id=str(purchase.id),
            actor_user_id=None,
            metadata={"provider": "bereke"},
        )
    await repository.add_event(
        db,
        provider_event_id=callback.event_id,
        purchase_id=purchase.id,
        event_status=callback.status,
        occurred_at=callback.occurred_at,
    )
    await db.commit()
    return purchase
