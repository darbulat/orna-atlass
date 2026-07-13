"""sprint 2 domain constraints

Revision ID: 0006_sprint2_domain_constraints
Revises: 0005_sprint8_auth_membership
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_sprint2_domain_constraints"
down_revision: str | None = "0005_sprint8_auth_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONSTRAINTS = {
    "locations": [
        ("ck_locations_exact_latitude", "exact_latitude BETWEEN -90 AND 90"),
        ("ck_locations_exact_longitude", "exact_longitude BETWEEN -180 AND 180"),
        ("ck_locations_public_coordinate_pair", "(public_latitude IS NULL) = (public_longitude IS NULL)"),
        ("ck_locations_public_latitude", "public_latitude IS NULL OR public_latitude BETWEEN -90 AND 90"),
        ("ck_locations_public_longitude", "public_longitude IS NULL OR public_longitude BETWEEN -180 AND 180"),
        ("ck_locations_coordinate_visibility", "coordinate_visibility IN ('exact_public','approximate_public','hidden_public')"),
        ("ck_locations_sensitivity_level", "sensitivity_level IN ('none','low','medium','high','protected')"),
    ],
    "recording_sessions": [
        ("ck_sessions_duration", "duration_seconds IS NULL OR duration_seconds >= 0"),
        ("ck_sessions_access_level", "access_level IN ('public','members_only','draft','private')"),
        ("ck_sessions_processing_status", "processing_status IN ('pending','uploaded','queued','processing','ready','failed')"),
    ],
    "media_assets": [
        ("ck_media_assets_kind", "kind IN ('audio','source_audio','master_audio','streaming_rendition','audio_stream')"),
        ("ck_media_assets_processing_status", "processing_status IN ('pending','uploaded','queued','processing','ready','failed')"),
        ("ck_media_assets_duration", "duration_seconds IS NULL OR duration_seconds >= 0"),
        ("ck_media_assets_size", "size_bytes IS NULL OR size_bytes >= 0"),
    ],
    "processing_jobs": [
        ("ck_processing_jobs_type", "job_type IN ('audio_pipeline')"),
        ("ck_processing_jobs_status", "status IN ('queued','running','succeeded','failed')"),
        ("ck_processing_jobs_attempt_count", "attempt_count >= 0"),
    ],
    "bird_vocal_parts": [
        ("ck_bird_parts_start", "starts_at_seconds >= 0"),
        ("ck_bird_parts_interval", "ends_at_seconds >= starts_at_seconds"),
        ("ck_bird_parts_confidence", "confidence IS NULL OR confidence BETWEEN 0 AND 1"),
    ],
}


def upgrade() -> None:
    op.execute("UPDATE locations SET coordinate_visibility = 'approximate_public' WHERE coordinate_visibility = 'public_only'")
    for table, constraints in CONSTRAINTS.items():
        for name, condition in constraints:
            op.create_check_constraint(name, table, condition)


def downgrade() -> None:
    for table, constraints in reversed(CONSTRAINTS.items()):
        for name, _condition in reversed(constraints):
            op.drop_constraint(name, table, type_="check")
