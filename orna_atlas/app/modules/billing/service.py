from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import ConflictError, ForbiddenError, NotFoundError
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
from orna_atlas.app.modules.users.service import require_user


def public_offer(settings: Settings) -> BillingOfferRead:
    return BillingOfferRead(checkout_available=settings.billing_enabled)


def _purchase_read(purchase: BillingPurchase) -> PurchaseRead:
    return PurchaseRead.model_validate(purchase)


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
    membership = await memberships_repository.get_for_user(db, user_id)
    if membership is not None and membership.is_entitled:
        raise ConflictError("Lifetime Member Access is already active")
    existing = await repository.get_by_idempotency(db, user_id, idempotency_key)
    if existing is not None:
        if existing.status != "creating":
            return CheckoutRead(
                purchase_id=existing.id,
                merchant_reference=existing.merchant_reference,
                status=existing.status,
                checkout_url=existing.checkout_url if existing.status == "pending" else None,
                expires_at=existing.checkout_expires_at,
            )
        purchase = existing
        merchant_reference = existing.merchant_reference
    else:
        merchant_reference = f"orna-{uuid4().hex}"
        purchase = await repository.create_purchase(
            db,
            user_id=user_id,
            merchant_reference=merchant_reference,
            idempotency_key=idempotency_key,
        )
        await db.commit()
    hosted = await provider.create_checkout(
        merchant_reference=merchant_reference,
        amount_minor=1000,
        currency="USD",
        description="ORNA Atlas Lifetime Member Access",
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
    return [_purchase_read(item) for item in await repository.list_for_user(db, user_id)]


async def get_purchase(db: AsyncSession, user_id: UUID, purchase_id: UUID) -> PurchaseRead:
    await require_user(db, user_id)
    purchase = await repository.get_for_user(db, purchase_id, user_id)
    if purchase is None:
        raise NotFoundError("Purchase not found")
    return _purchase_read(purchase)


async def request_refund(
    db: AsyncSession, user_id: UUID, purchase_id: UUID
) -> RefundRequestRead:
    await require_user(db, user_id)
    purchase = await repository.get_for_user(db, purchase_id, user_id)
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
    if callback.status == "paid" and purchase.status in {"creating", "pending", "failed"}:
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
        if not await repository.has_other_paid_purchase(db, purchase.user_id, purchase.id):
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
