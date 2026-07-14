"""content tombstones and durable object cleanup

Revision ID: 0009_content_lifecycle
Revises: 0008_postgis_locations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_content_lifecycle"
down_revision: str | None = "0008_postgis_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "locations",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_locations_archived_at", "locations", ["archived_at"])
    op.add_column(
        "recording_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_recording_sessions_archived_at",
        "recording_sessions",
        ["archived_at"],
    )
    op.add_column(
        "media_assets",
        sa.Column("storage_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "storage_cleanup_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed')",
            name="ck_storage_cleanup_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_storage_cleanup_jobs_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["media_assets.id"],
            name="fk_storage_cleanup_jobs_asset_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_storage_cleanup_jobs"),
        sa.UniqueConstraint("asset_id", name="uq_storage_cleanup_jobs_asset_id"),
        sa.UniqueConstraint("storage_key", name="uq_storage_cleanup_jobs_storage_key"),
    )
    op.create_index(
        "ix_storage_cleanup_jobs_asset_id",
        "storage_cleanup_jobs",
        ["asset_id"],
    )
    op.create_index(
        "ix_storage_cleanup_jobs_status",
        "storage_cleanup_jobs",
        ["status"],
    )
    op.create_index(
        "ix_storage_cleanup_jobs_retain_until",
        "storage_cleanup_jobs",
        ["retain_until"],
    )
    op.create_index(
        "ix_storage_cleanup_jobs_next_attempt_at",
        "storage_cleanup_jobs",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_storage_cleanup_jobs_due",
        "storage_cleanup_jobs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_storage_cleanup_jobs_due", table_name="storage_cleanup_jobs")
    op.drop_index(
        "ix_storage_cleanup_jobs_next_attempt_at",
        table_name="storage_cleanup_jobs",
    )
    op.drop_index(
        "ix_storage_cleanup_jobs_retain_until",
        table_name="storage_cleanup_jobs",
    )
    op.drop_index("ix_storage_cleanup_jobs_status", table_name="storage_cleanup_jobs")
    op.drop_index("ix_storage_cleanup_jobs_asset_id", table_name="storage_cleanup_jobs")
    op.drop_table("storage_cleanup_jobs")
    op.drop_column("media_assets", "storage_deleted_at")
    op.drop_index(
        "ix_recording_sessions_archived_at",
        table_name="recording_sessions",
    )
    op.drop_column("recording_sessions", "archived_at")
    op.drop_index("ix_locations_archived_at", table_name="locations")
    op.drop_column("locations", "archived_at")
