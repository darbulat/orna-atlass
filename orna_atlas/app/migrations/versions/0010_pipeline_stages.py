"""persist per-stage audio pipeline state

Revision ID: 0010_pipeline_stages
Revises: 0009_content_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_pipeline_stages"
down_revision: str | None = "0009_content_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column(
            "stage_states",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("request_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("queue_job_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_processing_jobs_request_id",
        "processing_jobs",
        ["request_id"],
    )
    op.create_index(
        "ix_processing_jobs_queue_job_id",
        "processing_jobs",
        ["queue_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_queue_job_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_request_id", table_name="processing_jobs")
    op.drop_column("processing_jobs", "queue_job_id")
    op.drop_column("processing_jobs", "request_id")
    op.drop_column("processing_jobs", "stage_states")
