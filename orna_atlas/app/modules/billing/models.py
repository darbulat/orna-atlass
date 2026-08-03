from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from orna_atlas.app.db.base import Base


class BillingOffer(Base):
    __tablename__ = "billing_offers"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_billing_offers_positive_amount"),
        CheckConstraint("currency IN ('USD', 'KZT')", name="ck_billing_offers_currency"),
        CheckConstraint("version > 0", name="ck_billing_offers_positive_version"),
        UniqueConstraint("product_code", "version", name="uq_billing_offers_product_version"),
        Index(
            "uq_billing_offers_one_active_product",
            "product_code",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class BillingPurchase(Base):
    __tablename__ = "billing_purchases"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_billing_purchases_positive_amount"),
        CheckConstraint("currency IN ('USD', 'KZT')", name="ck_billing_purchases_currency"),
        CheckConstraint(
            "status IN ('creating', 'provider_outcome_unknown', 'pending', 'paid', 'failed', 'expired', 'refund_requested', 'refunded')",
            name="ck_billing_purchases_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_billing_purchase_user_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    offer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("billing_offers.id", ondelete="RESTRICT"), nullable=True
    )
    offer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
