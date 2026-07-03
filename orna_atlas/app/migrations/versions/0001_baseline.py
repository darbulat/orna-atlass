"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("habitat", sa.String(length=120), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_locations_slug", "locations", ["slug"], unique=True)
    op.create_index("ix_locations_name", "locations", ["name"])
    op.create_index("ix_locations_country_code", "locations", ["country_code"])
    op.create_index("ix_locations_habitat", "locations", ["habitat"])

    op.create_table(
        "recording_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("recorder", sa.String(length=160), nullable=True),
        sa.Column("weather", sa.String(length=240), nullable=True),
        sa.Column("access_level", sa.String(length=40), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recording_sessions_slug", "recording_sessions", ["slug"], unique=True)
    op.create_index("ix_recording_sessions_location_id", "recording_sessions", ["location_id"])
    op.create_index("ix_recording_sessions_recorded_at", "recording_sessions", ["recorded_at"])
    op.create_index("ix_recording_sessions_access_level", "recording_sessions", ["access_level"])

    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_media_assets_session_id", "media_assets", ["session_id"])
    op.create_index("ix_media_assets_storage_key", "media_assets", ["storage_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_media_assets_storage_key", table_name="media_assets")
    op.drop_index("ix_media_assets_session_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_recording_sessions_access_level", table_name="recording_sessions")
    op.drop_index("ix_recording_sessions_recorded_at", table_name="recording_sessions")
    op.drop_index("ix_recording_sessions_location_id", table_name="recording_sessions")
    op.drop_index("ix_recording_sessions_slug", table_name="recording_sessions")
    op.drop_table("recording_sessions")
    op.drop_index("ix_locations_habitat", table_name="locations")
    op.drop_index("ix_locations_country_code", table_name="locations")
    op.drop_index("ix_locations_name", table_name="locations")
    op.drop_index("ix_locations_slug", table_name="locations")
    op.drop_table("locations")
