"""segmented recordings and session HLS jobs

Revision ID: 0013_segmented_hls
Revises: 0012_seed_link_ownership
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013_segmented_hls"
down_revision: str | None = "0012_seed_link_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "storage_cleanup_jobs",
        sa.Column("object_keys", postgresql.JSONB(), nullable=True),
    )
    op.drop_index("uq_media_assets_active_source", table_name="media_assets")
    op.create_index(
        "uq_media_assets_active_source",
        "media_assets",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "kind IN ('audio', 'source_audio', 'master_audio') "
            "AND is_active AND archived_at IS NULL "
            "AND NOT (metadata ? 'recording_segment')"
        ),
    )
    op.create_table(
        "recording_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "processing_status", sa.String(length=40), nullable=False, server_default="pending"
        ),
        sa.Column("processing_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_error_code", sa.String(length=80), nullable=True),
        sa.Column("processing_error_message", sa.Text(), nullable=True),
        sa.Column("start_offset_ms", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence_number > 0", name="ck_recording_segments_sequence"),
        sa.CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed')",
            name="ck_recording_segments_processing_status",
        ),
        sa.CheckConstraint(
            "processing_attempt_count >= 0",
            name="ck_recording_segments_processing_attempt_count",
        ),
        sa.CheckConstraint(
            "start_offset_ms IS NULL OR start_offset_ms >= 0",
            name="ck_recording_segments_offset",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms > 0", name="ck_recording_segments_duration"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["recording_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["media_assets.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "session_id", "sequence_number", name="uq_recording_segments_sequence"
        ),
        sa.UniqueConstraint("source_asset_id", name="uq_recording_segments_source_asset"),
    )
    op.create_index("ix_recording_segments_session_id", "recording_segments", ["session_id"])
    op.create_index(
        "ix_recording_segments_processing_status", "recording_segments", ["processing_status"]
    )
    op.create_index(
        "ix_recording_segments_source_asset_id", "recording_segments", ["source_asset_id"]
    )
    op.add_column(
        "bird_vocal_parts",
        sa.Column("recording_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_bird_vocal_parts_recording_segment_id",
        "bird_vocal_parts",
        "recording_segments",
        ["recording_segment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_bird_vocal_parts_recording_segment_id",
        "bird_vocal_parts",
        ["recording_segment_id"],
    )

    op.create_table(
        "hls_processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_states", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("queue_job_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="ck_hls_jobs_status"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_hls_jobs_attempt_count"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["recording_sessions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_hls_processing_jobs_session_id", "hls_processing_jobs", ["session_id"])
    op.create_index("ix_hls_processing_jobs_status", "hls_processing_jobs", ["status"])
    op.create_index(
        "ix_hls_processing_jobs_queue_job_id", "hls_processing_jobs", ["queue_job_id"]
    )
    op.create_index(
        "ix_hls_processing_jobs_heartbeat_at", "hls_processing_jobs", ["heartbeat_at"]
    )
    op.create_index(
        "uq_hls_jobs_active_source_set",
        "hls_processing_jobs",
        ["session_id", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM recording_segments LIMIT 1")).first():
        raise RuntimeError("Refusing to drop non-empty recording_segments")
    if connection.execute(sa.text("SELECT 1 FROM hls_processing_jobs LIMIT 1")).first():
        raise RuntimeError("Refusing to drop non-empty hls_processing_jobs")
    op.drop_constraint(
        "fk_bird_vocal_parts_recording_segment_id", "bird_vocal_parts", type_="foreignkey"
    )
    op.drop_index("ix_bird_vocal_parts_recording_segment_id", table_name="bird_vocal_parts")
    op.drop_column("bird_vocal_parts", "recording_segment_id")
    op.drop_column("storage_cleanup_jobs", "object_keys")
    op.drop_table("hls_processing_jobs")
    op.drop_table("recording_segments")
    op.drop_index("uq_media_assets_active_source", table_name="media_assets")
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
