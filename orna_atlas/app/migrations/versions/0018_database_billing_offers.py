"""store versioned lifetime membership offers

Revision ID: 0018_database_billing_offers
Revises: 0017_billing_test_currency
Create Date: 2026-08-03 09:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_database_billing_offers"
down_revision = "0017_billing_test_currency"
branch_labels = None
depends_on = None


_INITIAL_OFFER_ID = "00000000-0000-0000-0000-000000000018"


def upgrade() -> None:
    op.drop_constraint(
        "ck_billing_purchases_status", "billing_purchases", type_="check"
    )
    op.create_check_constraint(
        "ck_billing_purchases_status",
        "billing_purchases",
        "status IN ('creating', 'provider_outcome_unknown', 'pending', 'paid', 'failed', 'expired', 'refund_requested', 'refunded')",
    )
    # The old implementation committed `creating` before crossing the provider boundary. Any
    # surviving row may therefore represent an accepted order whose response was lost; quarantine
    # all of them rather than guessing that provider registration never happened.
    op.execute(
        sa.text(
            """
            UPDATE billing_purchases
            SET status = 'provider_outcome_unknown', checkout_url = NULL, updated_at = now()
            WHERE status = 'creating'
            """
        )
    )
    op.create_table(
        "billing_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_billing_offers_positive_amount"),
        sa.CheckConstraint("currency IN ('USD', 'KZT')", name="ck_billing_offers_currency"),
        sa.CheckConstraint("version > 0", name="ck_billing_offers_positive_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_code", "version", name="uq_billing_offers_product_version"),
    )
    op.create_index(
        "uq_billing_offers_one_active_product",
        "billing_offers",
        ["product_code"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO billing_offers
                (id, product_code, version, amount_minor, currency, is_active, created_at, updated_at)
            VALUES
                (CAST(:id AS uuid), 'lifetime_member', 1, 1000, 'USD', true, now(), now())
            """
        ).bindparams(id=_INITIAL_OFFER_ID)
    )
    op.add_column(
        "billing_purchases",
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "billing_purchases",
        sa.Column("offer_version", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_purchases_offer_id",
        "billing_purchases",
        "billing_offers",
        ["offer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            """
            UPDATE billing_purchases
            SET offer_id = CAST(:id AS uuid), offer_version = 1
            WHERE product_code = 'lifetime_member'
              AND amount_minor = 1000
              AND currency = 'USD'
            """
        ).bindparams(id=_INITIAL_OFFER_ID)
    )


def downgrade() -> None:
    connection = op.get_bind()
    unknown_count = connection.scalar(
        sa.text("SELECT count(*) FROM billing_purchases WHERE status = 'provider_outcome_unknown'")
    )
    if unknown_count:
        raise RuntimeError("Cannot downgrade while provider outcome is unknown")
    linked_purchase_count = connection.scalar(
        sa.text("SELECT count(*) FROM billing_purchases WHERE offer_id IS NOT NULL")
    )
    non_seed_offer_count = connection.scalar(
        sa.text(
            "SELECT count(*) FROM billing_offers "
            "WHERE id != CAST(:initial_offer_id AS uuid)"
        ).bindparams(initial_offer_id=_INITIAL_OFFER_ID)
    )
    if linked_purchase_count or non_seed_offer_count:
        raise RuntimeError(
            "Cannot downgrade while versioned offer or purchase-offer history exists"
        )
    op.drop_constraint("fk_billing_purchases_offer_id", "billing_purchases", type_="foreignkey")
    op.drop_column("billing_purchases", "offer_version")
    op.drop_column("billing_purchases", "offer_id")
    op.drop_index("uq_billing_offers_one_active_product", table_name="billing_offers")
    op.drop_table("billing_offers")
    op.drop_constraint(
        "ck_billing_purchases_status", "billing_purchases", type_="check"
    )
    op.create_check_constraint(
        "ck_billing_purchases_status",
        "billing_purchases",
        "status IN ('creating', 'pending', 'paid', 'failed', 'expired', 'refund_requested', 'refunded')",
    )
