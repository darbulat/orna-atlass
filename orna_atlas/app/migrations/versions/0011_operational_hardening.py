"""enforce geospatial invariants and recover stale pipeline jobs

Revision ID: 0011_operational_hardening
Revises: 0010_pipeline_stages
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_operational_hardening"
down_revision: str | None = "0010_pipeline_stages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail closed for legacy rows that cannot produce an approximate public point.
    op.execute(
        """
        UPDATE locations
        SET coordinate_visibility = 'hidden_public'
        WHERE coordinate_visibility = 'approximate_public'
          AND (public_latitude IS NULL OR public_longitude IS NULL)
        """
    )
    op.create_check_constraint(
        "ck_locations_approximate_public_coordinates",
        "locations",
        "coordinate_visibility != 'approximate_public' "
        "OR (public_latitude IS NOT NULL AND public_longitude IS NOT NULL)",
    )
    op.add_column(
        "processing_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE processing_jobs
        SET heartbeat_at = COALESCE(started_at, updated_at, created_at)
        WHERE status = 'running'
        """
    )
    op.create_index(
        "ix_processing_jobs_heartbeat_at",
        "processing_jobs",
        ["heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_heartbeat_at", table_name="processing_jobs")
    op.drop_column("processing_jobs", "heartbeat_at")
    op.drop_constraint(
        "ck_locations_approximate_public_coordinates",
        "locations",
        type_="check",
    )
