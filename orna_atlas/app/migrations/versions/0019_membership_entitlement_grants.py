"""preserve membership entitlement grant provenance

Revision ID: 0019_entitlement_grants
Revises: 0018_database_billing_offers
Create Date: 2026-08-03 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019_entitlement_grants"
down_revision = "0018_database_billing_offers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Block old callback writers until the compatibility trigger is committed. Statements that
    # were waiting on this lock resume only after the trigger is visible, closing the otherwise
    # possible backfill/cutover gap during a rolling Compose deployment.
    op.execute("LOCK TABLE billing_purchases IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "membership_entitlement_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('billing_purchase', 'admin', 'legacy')",
            name="ck_membership_grants_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_membership_grants_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_membership_grants_source"),
    )
    op.create_index(
        "ix_membership_entitlement_grants_user_id",
        "membership_entitlement_grants",
        ["user_id"],
    )
    op.create_index(
        "ix_membership_entitlement_grants_status",
        "membership_entitlement_grants",
        ["status"],
    )
    op.create_index(
        "ix_membership_entitlement_grants_expires_at",
        "membership_entitlement_grants",
        ["expires_at"],
    )
    op.execute(
        """
        CREATE FUNCTION sync_billing_purchase_entitlement_grant()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status IN ('paid', 'refund_requested') THEN
                INSERT INTO membership_entitlement_grants
                    (id, user_id, source_type, source_id, plan, status, starts_at,
                     expires_at, revoked_at, created_at, updated_at)
                VALUES
                    (NEW.id, NEW.user_id, 'billing_purchase', NEW.id,
                     'lifetime_member', 'active', COALESCE(NEW.paid_at, NEW.created_at),
                     NULL, NULL, NEW.created_at, NEW.updated_at)
                ON CONFLICT ON CONSTRAINT uq_membership_grants_source
                DO UPDATE SET
                    status = 'active',
                    starts_at = EXCLUDED.starts_at,
                    expires_at = NULL,
                    revoked_at = NULL,
                    updated_at = EXCLUDED.updated_at;
            ELSIF NEW.status = 'refunded' THEN
                UPDATE membership_entitlement_grants
                SET status = 'revoked',
                    revoked_at = COALESCE(NEW.refunded_at, now()),
                    updated_at = NEW.updated_at
                WHERE source_type = 'billing_purchase'
                  AND source_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_billing_purchase_entitlement_grant
        AFTER INSERT OR UPDATE OF status ON billing_purchases
        FOR EACH ROW
        EXECUTE FUNCTION sync_billing_purchase_entitlement_grant()
        """
    )
    op.execute(
        sa.text(
            """
            INSERT INTO membership_entitlement_grants
                (id, user_id, source_type, source_id, plan, status, starts_at,
                 expires_at, revoked_at, created_at, updated_at)
            SELECT
                p.id, p.user_id, 'billing_purchase', p.id, 'lifetime_member', 'active',
                COALESCE(p.paid_at, p.created_at), NULL, NULL, p.created_at, p.updated_at
            FROM billing_purchases AS p
            WHERE p.status IN ('paid', 'refund_requested')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO membership_entitlement_grants
                (id, user_id, source_type, source_id, plan, status, starts_at,
                 expires_at, revoked_at, created_at, updated_at)
            SELECT
                m.id, m.user_id, 'legacy', m.id, m.plan, 'active', m.starts_at,
                m.expires_at, NULL, m.created_at, m.updated_at
            FROM memberships AS m
            WHERE m.status = 'active'
              AND (m.expires_at IS NULL OR m.expires_at > now())
            """
        )
    )


def downgrade() -> None:
    op.execute("LOCK TABLE billing_purchases IN SHARE ROW EXCLUSIVE MODE")
    grant_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM membership_entitlement_grants")
    ).scalar_one()
    if grant_count:
        raise RuntimeError(
            "Cannot downgrade 0019_entitlement_grants while entitlement grant history exists"
        )
    op.execute(
        "DROP TRIGGER trg_sync_billing_purchase_entitlement_grant ON billing_purchases"
    )
    op.execute("DROP FUNCTION sync_billing_purchase_entitlement_grant()")
    op.drop_index(
        "ix_membership_entitlement_grants_expires_at",
        table_name="membership_entitlement_grants",
    )
    op.drop_index(
        "ix_membership_entitlement_grants_status",
        table_name="membership_entitlement_grants",
    )
    op.drop_index(
        "ix_membership_entitlement_grants_user_id",
        table_name="membership_entitlement_grants",
    )
    op.drop_table("membership_entitlement_grants")
