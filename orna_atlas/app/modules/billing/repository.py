from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.billing.models import (
    BillingOffer,
    BillingProviderEvent,
    BillingPurchase,
    BillingRefundRequest,
)


async def get_active_offer(
    db: AsyncSession, product_code: str = "lifetime_member", *, for_update: bool = False
) -> BillingOffer | None:
    statement = select(BillingOffer).where(
        BillingOffer.product_code == product_code,
        BillingOffer.is_active.is_(True),
    )
    if for_update:
        statement = statement.with_for_update()
    return await db.scalar(statement)


async def next_offer_version(
    db: AsyncSession, product_code: str = "lifetime_member"
) -> int:
    current = await db.scalar(
        select(func.max(BillingOffer.version)).where(BillingOffer.product_code == product_code)
    )
    return (current or 0) + 1


async def create_purchase(
    db: AsyncSession,
    *,
    user_id: UUID,
    merchant_reference: str,
    idempotency_key: str,
    amount_minor: int,
    currency: str,
    offer_id: UUID | None = None,
    offer_version: int | None = None,
) -> BillingPurchase:
    purchase = BillingPurchase(
        user_id=user_id,
        merchant_reference=merchant_reference,
        idempotency_key=idempotency_key,
        product_code="lifetime_member",
        amount_minor=amount_minor,
        currency=currency,
        offer_id=offer_id,
        offer_version=offer_version,
        status="creating",
    )
    db.add(purchase)
    await db.flush()
    return purchase


async def get_by_idempotency(
    db: AsyncSession, user_id: UUID, idempotency_key: str
) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase).where(
            BillingPurchase.user_id == user_id,
            BillingPurchase.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def get_for_user(
    db: AsyncSession, purchase_id: UUID, user_id: UUID
) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase).where(
            BillingPurchase.id == purchase_id, BillingPurchase.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def get_for_user_for_update(
    db: AsyncSession, purchase_id: UUID, user_id: UUID
) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase)
        .where(BillingPurchase.id == purchase_id, BillingPurchase.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_open_for_user(db: AsyncSession, user_id: UUID) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase)
        .where(
            BillingPurchase.user_id == user_id,
            BillingPurchase.status.in_(("creating", "provider_outcome_unknown", "pending")),
        )
        .order_by(BillingPurchase.created_at.desc(), BillingPurchase.id)
        .limit(1)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_for_user(db: AsyncSession, user_id: UUID) -> list[BillingPurchase]:
    result = await db.execute(
        select(BillingPurchase)
        .where(BillingPurchase.user_id == user_id)
        .order_by(BillingPurchase.created_at.desc(), BillingPurchase.id)
    )
    return list(result.scalars().all())


async def get_by_merchant_reference_for_update(
    db: AsyncSession, merchant_reference: str
) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase)
        .where(BillingPurchase.merchant_reference == merchant_reference)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_by_provider_order_id_for_update(
    db: AsyncSession, provider_order_id: str
) -> BillingPurchase | None:
    result = await db.execute(
        select(BillingPurchase)
        .where(BillingPurchase.provider_order_id == provider_order_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def event_exists(db: AsyncSession, provider_event_id: str) -> bool:
    result = await db.execute(
        select(BillingProviderEvent.id).where(
            BillingProviderEvent.provider_event_id == provider_event_id
        )
    )
    return result.scalar_one_or_none() is not None


async def add_event(
    db: AsyncSession,
    *,
    provider_event_id: str,
    purchase_id: UUID,
    event_status: str,
    occurred_at: datetime,
) -> BillingProviderEvent:
    event = BillingProviderEvent(
        provider_event_id=provider_event_id,
        purchase_id=purchase_id,
        event_status=event_status,
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()
    return event


async def has_other_payment_backed_purchase(
    db: AsyncSession, user_id: UUID, excluding_purchase_id: UUID
) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(BillingPurchase)
        .where(
            BillingPurchase.user_id == user_id,
            BillingPurchase.id != excluding_purchase_id,
            BillingPurchase.status.in_(("paid", "refund_requested")),
        )
    )
    return bool(result.scalar_one())


async def get_refund_request(
    db: AsyncSession, purchase_id: UUID
) -> BillingRefundRequest | None:
    result = await db.execute(
        select(BillingRefundRequest).where(BillingRefundRequest.purchase_id == purchase_id)
    )
    return result.scalar_one_or_none()


async def create_refund_request(
    db: AsyncSession, purchase_id: UUID, user_id: UUID
) -> BillingRefundRequest:
    request = BillingRefundRequest(purchase_id=purchase_id, user_id=user_id)
    db.add(request)
    await db.flush()
    return request
