"""Destructive migration-cycle proof for an explicitly disposable database."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

LEGACY_REVISION = "0007_sprint3_business_hardening"


def _require_disposable_target() -> str:
    if os.getenv("RUN_MIGRATION_CYCLE_CHECK") != "1":
        raise RuntimeError("Set RUN_MIGRATION_CYCLE_CHECK=1 for this destructive check")
    environment = os.getenv("APP_ENVIRONMENT", "").strip().lower()
    if environment not in {"local", "test", "ci"}:
        raise RuntimeError("Migration cycle is allowed only in local/test/ci")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return database_url


async def _execute(database_url: str, statement: str, parameters: dict | None = None):
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(statement), parameters or {})
            row = result.mappings().first() if result.returns_rows else None
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _require_disposable_target()
    config = Config("alembic.ini")
    fixture_id = uuid4()
    fixture_slug = f"migration-cycle-{fixture_id.hex}"

    command.upgrade(config, "head")
    command.downgrade(config, LEGACY_REVISION)
    asyncio.run(
        _execute(
            database_url,
            """
            INSERT INTO locations (
                id, slug, name, exact_latitude, exact_longitude,
                public_latitude, public_longitude, coordinate_visibility,
                sensitivity_level, timezone, metadata, created_at, updated_at
            ) VALUES (
                :id, :slug, 'Migration cycle fixture', 57.25, 30.75,
                57.5, 31.0, 'approximate_public', 'protected', 'UTC',
                '{}'::jsonb, now(), now()
            )
            """,
            {"id": fixture_id, "slug": fixture_slug},
        )
    )

    command.upgrade(config, "head")
    projected = asyncio.run(
        _execute(
            database_url,
            """
            SELECT exact_latitude, exact_longitude,
                   ST_Y(exact_point) AS exact_y, ST_X(exact_point) AS exact_x,
                   ST_Y(public_point) AS public_y, ST_X(public_point) AS public_x
            FROM locations WHERE id = :id
            """,
            {"id": fixture_id},
        )
    )
    assert projected == {
        "exact_latitude": 57.25,
        "exact_longitude": 30.75,
        "exact_y": 57.25,
        "exact_x": 30.75,
        "public_y": 57.5,
        "public_x": 31.0,
    }

    command.downgrade(config, LEGACY_REVISION)
    preserved = asyncio.run(
        _execute(
            database_url,
            """
            SELECT exact_latitude, exact_longitude, public_latitude, public_longitude,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'locations' AND column_name = 'exact_point'
                   ) AS geometry_column_exists
            FROM locations WHERE id = :id
            """,
            {"id": fixture_id},
        )
    )
    assert preserved == {
        "exact_latitude": 57.25,
        "exact_longitude": 30.75,
        "public_latitude": 57.5,
        "public_longitude": 31.0,
        "geometry_column_exists": False,
    }
    asyncio.run(
        _execute(
            database_url,
            "DELETE FROM locations WHERE id = :id",
            {"id": fixture_id},
        )
    )
    command.upgrade(config, "head")
    command.check(config)
    print("Migration cycle preserved legacy coordinates and returned to head.")


if __name__ == "__main__":
    main()
