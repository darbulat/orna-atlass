from datetime import UTC, datetime, timedelta
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
from orna_atlas.app.modules.admin.context import (
    apply_actor_mode_metadata,
    build_admin_etag,
    validate_if_match_or_fail,
)
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.billing import repository
from orna_atlas.app.modules.billing.models import BillingOffer, BillingPurchase
from orna_atlas.app.modules.billing.schemas import (
    AdminBillingOfferCreate,
    BillingOfferRead,
    CheckoutRead,
    PurchaseRead,
    RefundRequestRead,
)
from orna_atlas.app.modules.memberships import repository as memberships_repository
from orna_atlas.app.modules.memberships.schemas import MembershipUpdate
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.service import require_user


async def public_offer(db: AsyncSession, settings: Settings) -> BillingOfferRead:
    _, _, amount_minor, currency = await _offer_snapshot(db, settings)
    return BillingOfferRead(
        amount_minor=amount_minor,
        currency=currency,
        checkout_available=settings.billing_enabled,
    )


async def active_offer_for_admin(db: AsyncSession) -> BillingOffer:
    offer = await repository.get_active_offer(db)
    if offer is None:
        raise ServiceUnavailableError("Lifetime membership offer is unavailable")
    return offer


async def replace_active_offer(
    db: AsyncSession,
    data: AdminBillingOfferCreate,
    *,
    if_match: str,
    actor_user_id: UUID | None,
    actor_mode: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> BillingOffer:
    current = await repository.get_active_offer(db, for_update=True)
    if current is None:
        # PostgreSQL rechecks the partial `is_active` predicate after waiting on
        # a row lock. A concurrent replacement can therefore make the locked
        # row disappear from this statement even though a new active offer now
        # exists. Lock that replacement so the caller receives the required
        # stale If-Match response rather than a misleading availability error.
        current = await repository.get_active_offer(db, for_update=True)
    if current is None:
        raise ServiceUnavailableError("Lifetime membership offer is unavailable")
    validate_if_match_or_fail(
        if_match=if_match,
        expected=build_admin_etag(resource_id=current.id, updated_at=current.updated_at),
    )
    if current.amount_minor == data.amount_minor and current.currency == data.currency:
        return current
    current.is_active = False
    await db.flush()
    offer = BillingOffer(
        product_code="lifetime_member",
        version=await repository.next_offer_version(db),
        amount_minor=data.amount_minor,
        currency=data.currency,
        is_active=True,
    )
    db.add(offer)
    await db.flush()
    await add_audit_event(
        db,
        event_type="billing.offer_activated",
        subject_type="billing_offer",
        subject_id=str(offer.id),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=apply_actor_mode_metadata(
            {
                "previous_offer_id": str(current.id),
                "version": offer.version,
                "amount_minor": offer.amount_minor,
                "currency": offer.currency,
            },
            actor_mode,
        ),
    )
    await db.commit()
    await db.refresh(offer)
    return offer


async def _offer_snapshot(
    db: AsyncSession, settings: Settings, *, for_update: bool = False
) -> tuple[UUID | None, int | None, int, str]:
    if getattr(settings, "billing_test_mode", False):
        return None, None, 200, "KZT"
    offer = await repository.get_active_offer(db, for_update=for_update)
    if offer is None:
        raise ServiceUnavailableError("Lifetime membership offer is unavailable")
    return offer.id, offer.version, offer.amount_minor, offer.currency


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
    if await memberships_repository.has_active_grant(db, user_id):
        raise ConflictError("Lifetime Member Access is already active")
    existing = await repository.get_by_idempotency(db, user_id, idempotency_key)
    if existing is not None:
        if _expire_stale_checkout(existing):
            await db.commit()
            return _checkout_read(existing)
        if existing.status == "creating":
            # A surviving row may come from the pre-quarantine release, which crossed the
            # provider boundary while status was still `creating`. Do not replay it.
            existing.status = "provider_outcome_unknown"
            existing.checkout_url = None
            await db.commit()
        return _checkout_read(existing)
    else:
        open_purchase = await repository.get_open_for_user(db, user_id)
        if open_purchase is not None and not _expire_stale_checkout(open_purchase):
            if open_purchase.status == "creating":
                open_purchase.status = "provider_outcome_unknown"
                open_purchase.checkout_url = None
                await db.commit()
            return _checkout_read(open_purchase)
        # Bereke's hosted gateway limits orderNumber to 36 characters.
        merchant_reference = f"orna-{uuid4().hex[:31]}"
        offer_id, offer_version, amount_minor, currency = await _offer_snapshot(
            db, settings, for_update=True
        )
        purchase = await repository.create_purchase(
            db,
            user_id=user_id,
            merchant_reference=merchant_reference,
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            currency=currency,
            offer_id=offer_id,
            offer_version=offer_version,
        )
        await db.commit()
    # Persist the fail-closed state before crossing the provider boundary. A task cancellation,
    # process exit or lost response after this commit must never leave a retryable local state.
    purchase.status = "provider_outcome_unknown"
    purchase.checkout_url = None
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
    existing = await repository.get_refund_request(db, purchase_id)
    if existing is not None:
        return RefundRequestRead.model_validate(existing)
    if purchase.status not in {"paid", "refund_requested"}:
        raise ConflictError("Only a completed payment can be refunded")
    if purchase.paid_at is None or datetime.now(UTC) > purchase.paid_at + timedelta(days=14):
        raise ConflictError("Self-service refunds are available for 14 calendar days")
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
    if purchase.amount_minor != callback.amount_minor or purchase.currency != callback.currency:
        raise ConflictError("Payment amount or currency does not match")
    if (
        purchase.provider_order_id is None
        and purchase.status == "provider_outcome_unknown"
        and not callback.match_by_provider_order
    ):
        # Normal-mode callbacks are independently verified and locate the
        # locked purchase by its immutable merchant reference. This is the
        # authoritative reconciliation path when the provider created an order
        # but its registration response was lost before we persisted the ID.
        purchase.provider_order_id = callback.provider_order_id
    elif purchase.provider_order_id != callback.provider_order_id:
        raise ConflictError("Payment order does not match")
    if callback.status == "refunded" and purchase.status not in {"paid", "refund_requested", "refunded"}:
        raise ConflictError("Only a paid purchase can be refunded")
    paid_before_expiry = (
        purchase.status == "expired"
        and purchase.checkout_expires_at is not None
        and callback.occurred_at <= purchase.checkout_expires_at
    )
    if callback.status == "paid" and (
        purchase.status in {"creating", "provider_outcome_unknown", "pending", "failed"}
        or paid_before_expiry
    ):
        purchase.status = "paid"
        purchase.paid_at = callback.occurred_at
        await memberships_repository.upsert_grant(
            db,
            purchase.user_id,
            source_type="billing_purchase",
            source_id=purchase.id,
            plan="lifetime_member",
            expires_at=None,
        )
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
    elif callback.status == "failed" and purchase.status in {
        "creating",
        "provider_outcome_unknown",
        "pending",
    }:
        purchase.status = "failed"
    elif callback.status == "refunded" and purchase.status != "refunded":
        purchase.status = "refunded"
        purchase.refunded_at = callback.occurred_at
        refund = await repository.get_refund_request(db, purchase.id)
        if refund is not None:
            refund.status = "completed"
        await memberships_repository.revoke_grant(
            db, source_type="billing_purchase", source_id=purchase.id
        )
        if not await memberships_repository.has_active_grant(db, purchase.user_id):
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
