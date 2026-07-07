"""sprint9 editorial collections bird parts featured

Revision ID: 0004_sprint9_editorial
Revises: 0003_sprint6_audio_pipeline
Create Date: 2026-07-07 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_sprint9_editorial"
down_revision = "0003_sprint6_audio_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_collections_slug", "collections", ["slug"], unique=True)
    op.create_index("ix_collections_is_public", "collections", ["is_public"])
    op.create_index("ix_collections_sort_order", "collections", ["sort_order"])

    op.create_table(
        "collection_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("collection_id", "location_id", name="uq_collection_locations_pair"),
    )
    op.create_index("ix_collection_locations_collection_id", "collection_locations", ["collection_id"])
    op.create_index("ix_collection_locations_location_id", "collection_locations", ["location_id"])

    op.create_table(
        "collection_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("collection_id", "session_id", name="uq_collection_sessions_pair"),
    )
    op.create_index("ix_collection_sessions_collection_id", "collection_sessions", ["collection_id"])
    op.create_index("ix_collection_sessions_session_id", "collection_sessions", ["session_id"])

    op.create_table(
        "bird_vocal_parts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("species_code", sa.String(length=120), nullable=False),
        sa.Column("species_common_name", sa.String(length=180), nullable=False),
        sa.Column("species_scientific_name", sa.String(length=180), nullable=True),
        sa.Column("starts_at_seconds", sa.Float(), nullable=False),
        sa.Column("ends_at_seconds", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("channel", sa.String(length=40), nullable=True),
        sa.Column("call_type", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("analysis_provider", sa.String(length=120), nullable=True),
        sa.Column("analysis_model_version", sa.String(length=80), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bird_vocal_parts_session_id", "bird_vocal_parts", ["session_id"])
    op.create_index("ix_bird_vocal_parts_species_code", "bird_vocal_parts", ["species_code"])

    op.add_column(
        "recording_sessions",
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("recording_sessions", sa.Column("featured_sort_order", sa.Integer(), nullable=True))
    op.create_index("ix_recording_sessions_is_featured", "recording_sessions", ["is_featured"])


def downgrade() -> None:
    op.drop_index("ix_recording_sessions_is_featured", table_name="recording_sessions")
    op.drop_column("recording_sessions", "featured_sort_order")
    op.drop_column("recording_sessions", "is_featured")
    op.drop_index("ix_bird_vocal_parts_species_code", table_name="bird_vocal_parts")
    op.drop_index("ix_bird_vocal_parts_session_id", table_name="bird_vocal_parts")
    op.drop_table("bird_vocal_parts")
    op.drop_index("ix_collection_sessions_session_id", table_name="collection_sessions")
    op.drop_index("ix_collection_sessions_collection_id", table_name="collection_sessions")
    op.drop_table("collection_sessions")
    op.drop_index("ix_collection_locations_location_id", table_name="collection_locations")
    op.drop_index("ix_collection_locations_collection_id", table_name="collection_locations")
    op.drop_table("collection_locations")
    op.drop_index("ix_collections_sort_order", table_name="collections")
    op.drop_index("ix_collections_is_public", table_name="collections")
    op.drop_index("ix_collections_slug", table_name="collections")
    op.drop_table("collections")
