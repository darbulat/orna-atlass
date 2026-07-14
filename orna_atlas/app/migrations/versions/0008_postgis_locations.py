"""postgis location points and spatial indexes

Revision ID: 0008_postgis_locations
Revises: 0007_sprint3_business_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0008_postgis_locations"
down_revision: str | None = "0007_sprint3_business_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXACT_POINT_SQL = "ST_SetSRID(ST_MakePoint(exact_longitude, exact_latitude), 4326)"
PUBLIC_POINT_SQL = (
    "CASE "
    "WHEN coordinate_visibility = 'hidden_public' THEN NULL "
    "WHEN coordinate_visibility = 'exact_public' "
    "AND sensitivity_level NOT IN ('protected','high','medium') "
    f"THEN {EXACT_POINT_SQL} "
    "WHEN public_longitude IS NOT NULL AND public_latitude IS NOT NULL "
    "THEN ST_SetSRID(ST_MakePoint(public_longitude, public_latitude), 4326) "
    "ELSE NULL END"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.add_column(
        "locations",
        sa.Column(
            "exact_point",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            sa.Computed(EXACT_POINT_SQL, persisted=True),
            nullable=False,
        ),
    )
    op.add_column(
        "locations",
        sa.Column(
            "public_point",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            sa.Computed(PUBLIC_POINT_SQL, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_locations_exact_point_gist",
        "locations",
        ["exact_point"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_locations_public_point_gist",
        "locations",
        ["public_point"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_locations_public_point_gist", table_name="locations")
    op.drop_index("ix_locations_exact_point_gist", table_name="locations")
    op.drop_column("locations", "public_point")
    op.drop_column("locations", "exact_point")
