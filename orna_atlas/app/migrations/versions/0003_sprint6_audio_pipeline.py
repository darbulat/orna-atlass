"""sprint6 audio pipeline

Revision ID: 0003_sprint6_audio_pipeline
Revises: 0002_sprint2_core_tables
Create Date: 2026-07-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_sprint6_audio_pipeline"
down_revision = "0002_sprint2_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recording_sessions",
        sa.Column("processing_status", sa.String(length=40), nullable=False, server_default="pending"),
    )
    op.create_index(
        "ix_recording_sessions_processing_status",
        "recording_sessions",
        ["processing_status"],
    )
    op.add_column(
        "media_assets",
        sa.Column("processing_status", sa.String(length=40), nullable=False, server_default="uploaded"),
    )
    op.create_index("ix_media_assets_processing_status", "media_assets", ["processing_status"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_processing_jobs_asset_id", "processing_jobs", ["asset_id"])
    op.create_index("ix_processing_jobs_job_type", "processing_jobs", ["job_type"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_job_type", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_asset_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_media_assets_processing_status", table_name="media_assets")
    op.drop_column("media_assets", "processing_status")
    op.drop_index("ix_recording_sessions_processing_status", table_name="recording_sessions")
    op.drop_column("recording_sessions", "processing_status")
