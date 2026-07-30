"""add lifetime membership billing

Revision ID: 0016_lifetime_billing
Revises: 0015_account_library
Create Date: 2026-07-30 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_lifetime_billing"
down_revision = "0015_account_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_reference", sa.String(length=80), nullable=False),
        sa.Column("provider_order_id", sa.String(length=160), nullable=True),
        sa.Column("checkout_url", sa.String(length=2048), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checkout_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_billing_purchases_positive_amount"),
        sa.CheckConstraint("currency = 'USD'", name="ck_billing_purchases_currency"),
        sa.CheckConstraint(
            "status IN ('creating', 'pending', 'paid', 'failed', 'expired', 'refund_requested', 'refunded')",
            name="ck_billing_purchases_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_reference"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_billing_purchase_user_idempotency"),
    )
    op.create_index("ix_billing_purchases_user_id", "billing_purchases", ["user_id"])
    op.create_index("ix_billing_purchases_merchant_reference", "billing_purchases", ["merchant_reference"])
    op.create_index("ix_billing_purchases_provider_order_id", "billing_purchases", ["provider_order_id"])
    op.create_index("ix_billing_purchases_status", "billing_purchases", ["status"])
    op.create_index("ix_billing_purchases_created_at", "billing_purchases", ["created_at"])

    op.create_table(
        "billing_provider_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["billing_purchases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index("ix_billing_provider_events_provider_event_id", "billing_provider_events", ["provider_event_id"])
    op.create_index("ix_billing_provider_events_purchase_id", "billing_provider_events", ["purchase_id"])

    op.create_table(
        "billing_refund_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'rejected')",
            name="ck_billing_refund_requests_status",
        ),
        sa.ForeignKeyConstraint(["purchase_id"], ["billing_purchases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_id"),
    )
    op.create_index("ix_billing_refund_requests_purchase_id", "billing_refund_requests", ["purchase_id"])
    op.create_index("ix_billing_refund_requests_user_id", "billing_refund_requests", ["user_id"])
    op.create_index("ix_billing_refund_requests_status", "billing_refund_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_billing_refund_requests_status", table_name="billing_refund_requests")
    op.drop_index("ix_billing_refund_requests_user_id", table_name="billing_refund_requests")
    op.drop_index("ix_billing_refund_requests_purchase_id", table_name="billing_refund_requests")
    op.drop_table("billing_refund_requests")
    op.drop_index("ix_billing_provider_events_purchase_id", table_name="billing_provider_events")
    op.drop_index("ix_billing_provider_events_provider_event_id", table_name="billing_provider_events")
    op.drop_table("billing_provider_events")
    op.drop_index("ix_billing_purchases_created_at", table_name="billing_purchases")
    op.drop_index("ix_billing_purchases_status", table_name="billing_purchases")
    op.drop_index("ix_billing_purchases_provider_order_id", table_name="billing_purchases")
    op.drop_index("ix_billing_purchases_merchant_reference", table_name="billing_purchases")
    op.drop_index("ix_billing_purchases_user_id", table_name="billing_purchases")
    op.drop_table("billing_purchases")
