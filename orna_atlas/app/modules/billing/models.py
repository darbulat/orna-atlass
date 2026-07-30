from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from orna_atlas.app.db.base import Base


class BillingPurchase(Base):
    __tablename__ = "billing_purchases"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_billing_purchases_positive_amount"),
        CheckConstraint("currency = 'USD'", name="ck_billing_purchases_currency"),
        CheckConstraint(
            "status IN ('creating', 'pending', 'paid', 'failed', 'expired', 'refund_requested', 'refunded')",
            name="ck_billing_purchases_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_billing_purchase_user_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    merchant_reference: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    checkout_url: Mapped[str | None] = mapped_column(String(2048))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    product_code: Mapped[str] = mapped_column(String(64), default="lifetime_member")
    amount_minor: Mapped[int] = mapped_column(Integer, default=1000)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="creating", index=True)
    checkout_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class BillingProviderEvent(Base):
    __tablename__ = "billing_provider_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    purchase_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("billing_purchases.id", ondelete="CASCADE"), index=True
    )
    event_status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class BillingRefundRequest(Base):
    __tablename__ = "billing_refund_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'rejected')",
            name="ck_billing_refund_requests_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    purchase_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("billing_purchases.id", ondelete="CASCADE"),
        unique=True, index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
