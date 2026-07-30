from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.billing.models import (
    BillingProviderEvent,
    BillingPurchase,
    BillingRefundRequest,
)


async def create_purchase(
    db: AsyncSession,
    *,
    user_id: UUID,
    merchant_reference: str,
    idempotency_key: str,
) -> BillingPurchase:
    purchase = BillingPurchase(
        user_id=user_id,
        merchant_reference=merchant_reference,
        idempotency_key=idempotency_key,
        product_code="lifetime_member",
        amount_minor=1000,
        currency="USD",
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


async def has_other_paid_purchase(
    db: AsyncSession, user_id: UUID, excluding_purchase_id: UUID
) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(BillingPurchase)
        .where(
            BillingPurchase.user_id == user_id,
            BillingPurchase.id != excluding_purchase_id,
            BillingPurchase.status == "paid",
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
