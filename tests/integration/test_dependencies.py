"""Opt-in smoke tests for the real infrastructure boundary.

These tests intentionally refuse to run unless RUN_INTEGRATION_TESTS=1. Point all
URLs at disposable local services; the S3 test creates and removes its own object.
"""

from __future__ import annotations

import os
import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from orna_atlas.app.integrations.s3 import ObjectStorageClient, ObjectStorageConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 and use disposable local services",
    ),
]


@pytest.mark.asyncio
async def test_postgres_is_at_alembic_head() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    finally:
        await engine.dispose()

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert [current] == heads


@pytest.mark.asyncio
async def test_redis_round_trip() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    key = f"orna-atlas:integration:{uuid.uuid4()}"
    try:
        await client.set(key, "ok", ex=30)
        assert await client.get(key) == "ok"
    finally:
        await client.delete(key)
        await client.aclose()


def test_s3_round_trip() -> None:
    config = ObjectStorageConfig(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        public_endpoint_url=os.getenv("S3_PUBLIC_ENDPOINT_URL"),
        region=os.getenv("S3_REGION", "us-east-1"),
        private_bucket=os.environ["S3_PRIVATE_BUCKET"],
        public_bucket=os.getenv("S3_PUBLIC_BUCKET", "orna-media-public"),
        access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
    )
    storage = ObjectStorageClient(config)
    key = f"integration/{uuid.uuid4()}.txt"
    storage.put_bytes(key, b"orna-atlas", content_type="text/plain")
    try:
        assert storage.object_exists(key)
        assert storage.get_object_stream(key).read() == b"orna-atlas"
    finally:
        storage._get_client().delete_object(Bucket=config.private_bucket, Key=key)
