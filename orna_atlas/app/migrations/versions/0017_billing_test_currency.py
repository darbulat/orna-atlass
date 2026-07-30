"""allow the explicit KZT billing test offer

Revision ID: 0017_billing_test_currency
Revises: 0016_lifetime_billing
Create Date: 2026-07-30 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_billing_test_currency"
down_revision = "0016_lifetime_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_billing_purchases_currency", "billing_purchases", type_="check"
    )
    op.create_check_constraint(
        "ck_billing_purchases_currency",
        "billing_purchases",
        "currency IN ('USD', 'KZT')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    kzt_count = connection.scalar(
        sa.text("SELECT count(*) FROM billing_purchases WHERE currency = 'KZT'")
    )
    if kzt_count:
        raise RuntimeError("Cannot downgrade while KZT billing purchases exist")
    op.drop_constraint(
        "ck_billing_purchases_currency", "billing_purchases", type_="check"
    )
    op.create_check_constraint(
        "ck_billing_purchases_currency", "billing_purchases", "currency = 'USD'"
    )
