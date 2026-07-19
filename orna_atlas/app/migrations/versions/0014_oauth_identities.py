"""add social OAuth identities

Revision ID: 0014_oauth_identities
Revises: 0013_segmented_hls
Create Date: 2026-07-19 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_oauth_identities"
down_revision = "0013_segmented_hls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "provider IN ('google', 'apple', 'facebook')",
            name="ck_oauth_identities_provider",
        ),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_oauth_identities_provider_subject"
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_oauth_identities_user_provider"
        ),
    )
    op.create_index(
        "ix_oauth_identities_user_id", "oauth_identities", ["user_id"]
    )



def downgrade() -> None:
    # Downgrade cannot invent credentials for OAuth-only users. Fail instead of
    # cascading destructive user deletion; operators must migrate those accounts explicitly.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM users WHERE password_hash IS NULL) THEN "
        "RAISE EXCEPTION 'cannot downgrade while passwordless users exist'; "
        "END IF; END $$"
    )
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
    op.drop_column("users", "email_verified_at")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
