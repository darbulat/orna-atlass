from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.db.base import Base
from orna_atlas.app.modules.admin.models import AuditEvent  # noqa: F401
from orna_atlas.app.modules.auth.models import RefreshToken  # noqa: F401
from orna_atlas.app.modules.memberships.models import Membership  # noqa: F401
from orna_atlas.app.modules.users.models import User  # noqa: F401
from orna_atlas.app.modules.locations.models import Location  # noqa: F401
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob  # noqa: F401
from orna_atlas.app.modules.sessions.models import BirdVocalPart, RecordingSession  # noqa: F401
from orna_atlas.app.modules.collections.models import Collection, CollectionLocation, CollectionSession  # noqa: F401

config = context.config
config.set_main_option(
    "sqlalchemy.url", get_settings().database_url.replace("+asyncpg", "+psycopg")
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ANN001, ANN201
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
