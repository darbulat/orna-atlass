"""add account library

Revision ID: 0015_account_library
Revises: 0014_oauth_identities
Create Date: 2026-07-22 07:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_account_library"
down_revision = "0014_oauth_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "session_id"),
    )
    op.create_index("ix_user_favorites_user_created_at", "user_favorites", ["user_id", "created_at", "session_id"])
    op.create_index("ix_user_favorites_session_id", "user_favorites", ["session_id"])
    op.create_table(
        "listening_history",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_listened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_listened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_position_seconds", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("last_position_seconds >= 0", name="ck_listening_history_position"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "session_id"),
    )
    op.create_index("ix_listening_history_user_last_listened_at", "listening_history", ["user_id", "last_listened_at", "session_id"])
    op.create_index("ix_listening_history_session_id", "listening_history", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_listening_history_session_id", table_name="listening_history")
    op.drop_index("ix_listening_history_user_last_listened_at", table_name="listening_history")
    op.drop_table("listening_history")
    op.drop_index("ix_user_favorites_session_id", table_name="user_favorites")
    op.drop_index("ix_user_favorites_user_created_at", table_name="user_favorites")
    op.drop_table("user_favorites")
