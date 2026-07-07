from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from redis import Redis

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.modules.media.service import process_media_asset

AUDIO_QUEUE_NAME = "audio-processing"


def enqueue_audio_processing(asset_id: UUID | str) -> str | None:
    try:
        from rq import Queue

        redis = Redis.from_url(get_settings().redis_url)
        queue = Queue(AUDIO_QUEUE_NAME, connection=redis)
        job = queue.enqueue(
            "orna_atlas.app.workers.audio_pipeline.process_audio_asset",
            str(asset_id),
            job_timeout=600,
            result_ttl=3600,
        )
        return job.id
    except Exception:
        return None


def process_audio_asset(asset_id: str) -> str:
    asyncio.run(_process_audio_asset(asset_id))
    return asset_id


async def _process_audio_asset(asset_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await process_media_asset(session, UUID(asset_id))
    await engine.dispose()


def run_worker() -> None:
    from rq import Queue, Worker

    redis = Redis.from_url(get_settings().redis_url)
    queue = Queue(AUDIO_QUEUE_NAME, connection=redis)
    worker = Worker([queue], connection=redis)
    worker.work()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        run_worker()
        return
    if len(sys.argv) > 1:
        process_audio_asset(sys.argv[1])
        return
    raise SystemExit("Usage: python -m orna_atlas.app.workers.audio_pipeline worker|<asset-id>")


if __name__ == "__main__":
    main()
