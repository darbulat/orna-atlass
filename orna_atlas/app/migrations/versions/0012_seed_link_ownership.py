"""track ownership of collection links created by the local seed

Revision ID: 0012_seed_link_ownership
Revises: 0011_operational_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_seed_link_ownership"
down_revision: str | None = "0011_operational_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column(
        "collection_locations",
        sa.Column("seed_owner", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "collection_sessions",
        sa.Column("seed_owner", sa.String(length=80), nullable=True),
    )
    # Ownership cannot be inferred from the endpoints: a user may have linked
    # two otherwise seed-owned records. Existing links remain NULL and are
    # preserved; only future explicit seed writes set this column.


def downgrade() -> None:
    op.drop_column("collection_sessions", "seed_owner")
    op.drop_column("collection_locations", "seed_owner")
