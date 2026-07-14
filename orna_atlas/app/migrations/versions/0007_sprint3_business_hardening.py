"""sprint 3 business hardening

Revision ID: 0007_sprint3_business_hardening
Revises: 0006_sprint2_domain_constraints
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_sprint3_business_hardening"
down_revision: str | None = "0006_sprint2_domain_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recording_sessions",
        sa.Column("publication_status", sa.String(length=40), nullable=True),
    )
    op.execute(
        "UPDATE recording_sessions SET publication_status = "
        "CASE WHEN access_level IN ('public','members_only') THEN 'published' ELSE 'draft' END"
    )
    op.drop_constraint("ck_sessions_access_level", "recording_sessions", type_="check")
    op.execute("UPDATE recording_sessions SET access_level = 'private' WHERE access_level = 'draft'")
    op.create_check_constraint(
        "ck_sessions_access_level",
        "recording_sessions",
        "access_level IN ('public','members_only','private')",
    )
    op.create_check_constraint(
        "ck_sessions_publication_status",
        "recording_sessions",
        "publication_status IN ('draft','published','archived')",
    )
    op.alter_column(
        "recording_sessions",
        "publication_status",
        nullable=False,
        server_default="draft",
    )
    op.create_index(
        "ix_recording_sessions_publication_status",
        "recording_sessions",
        ["publication_status"],
    )

    op.add_column(
        "media_assets", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "media_assets", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column("media_assets", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("media_assets", sa.Column("source_asset_id", sa.UUID()))
    op.create_foreign_key(
        "fk_media_assets_source_asset_id",
        "media_assets",
        "media_assets",
        ["source_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint("ck_media_assets_revision", "media_assets", "revision > 0")
    op.create_index("ix_media_assets_is_active", "media_assets", ["is_active"])
    op.create_index("ix_media_assets_archived_at", "media_assets", ["archived_at"])
    op.create_index("ix_media_assets_source_asset_id", "media_assets", ["source_asset_id"])

    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY session_id
                ORDER BY created_at DESC, id DESC
            ) AS position
            FROM media_assets
            WHERE kind IN ('audio','source_audio','master_audio')
        )
        UPDATE media_assets AS asset
        SET is_active = false, archived_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE asset.id = ranked.id AND ranked.position > 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY session_id
                ORDER BY
                    CASE WHEN processing_status = 'ready' THEN 0 ELSE 1 END,
                    created_at DESC,
                    id DESC
            ) AS position
            FROM media_assets
            WHERE kind = 'streaming_rendition'
              AND is_active = true
              AND archived_at IS NULL
        )
        UPDATE media_assets AS asset
        SET is_active = false, archived_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE asset.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_index(
        "uq_media_assets_active_source",
        "media_assets",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_active AND archived_at IS NULL "
            "AND kind IN ('audio','source_audio','master_audio')"
        ),
    )
    op.create_index(
        "uq_media_assets_active_rendition",
        "media_assets",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_active AND archived_at IS NULL AND kind = 'streaming_rendition'"
        ),
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY asset_id, job_type
                ORDER BY created_at DESC, id DESC
            ) AS position
            FROM processing_jobs
            WHERE status IN ('queued','running')
        )
        UPDATE processing_jobs AS job
        SET status = 'failed', error_code = 'superseded',
            error_message = 'Superseded while enforcing active-job uniqueness',
            finished_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE job.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_index(
        "uq_processing_jobs_active_asset_type",
        "processing_jobs",
        ["asset_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_processing_jobs_active_asset_type", table_name="processing_jobs")
    op.drop_index("uq_media_assets_active_rendition", table_name="media_assets")
    op.drop_index("uq_media_assets_active_source", table_name="media_assets")
    op.drop_index("ix_media_assets_source_asset_id", table_name="media_assets")
    op.drop_index("ix_media_assets_archived_at", table_name="media_assets")
    op.drop_index("ix_media_assets_is_active", table_name="media_assets")
    op.drop_constraint("ck_media_assets_revision", "media_assets", type_="check")
    op.drop_constraint("fk_media_assets_source_asset_id", "media_assets", type_="foreignkey")
    op.drop_column("media_assets", "source_asset_id")
    op.drop_column("media_assets", "archived_at")
    op.drop_column("media_assets", "is_active")
    op.drop_column("media_assets", "revision")

    op.drop_index("ix_recording_sessions_publication_status", table_name="recording_sessions")
    op.drop_constraint("ck_sessions_publication_status", "recording_sessions", type_="check")
    op.drop_constraint("ck_sessions_access_level", "recording_sessions", type_="check")
    op.create_check_constraint(
        "ck_sessions_access_level",
        "recording_sessions",
        "access_level IN ('public','members_only','draft','private')",
    )
    op.execute(
        "UPDATE recording_sessions SET access_level = 'draft' "
        "WHERE publication_status = 'draft'"
    )
    op.drop_column("recording_sessions", "publication_status")
