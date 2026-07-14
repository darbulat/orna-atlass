from __future__ import annotations

import asyncio
import logging
import math
import sys
from uuid import UUID

from redis import Redis

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.logging import request_id_context
from orna_atlas.app.core.metrics import start_metrics_http_server
from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.modules.media.service import process_media_asset

AUDIO_QUEUE_NAME = "audio-processing"
logger = logging.getLogger(__name__)


def audio_job_timeout_seconds(duration_seconds: int | None) -> int:
    settings = get_settings()
    if duration_seconds is None or duration_seconds <= 0:
        # Duration is normally supplied by the upload contract.  If it is not,
        # fail safe for long-form field recordings instead of killing an unknown
        # multi-hour WAV after the short default timeout.
        return settings.audio_job_max_timeout_seconds
    estimated_hours = max(1, math.ceil(duration_seconds / 3600))
    estimated_timeout = estimated_hours * settings.audio_job_timeout_per_hour_seconds
    return min(
        settings.audio_job_max_timeout_seconds,
        max(settings.audio_job_timeout_seconds, estimated_timeout),
    )


def enqueue_audio_processing(
    asset_id: UUID | str,
    revision: int = 1,
    *,
    request_id: str | None = None,
    processing_job_id: UUID | str | None = None,
    duration_seconds: int | None = None,
) -> str:
    from rq import Queue, Retry

    redis = Redis.from_url(get_settings().redis_url)
    settings = get_settings()
    queue = Queue(AUDIO_QUEUE_NAME, connection=redis)
    job = queue.enqueue(
        "orna_atlas.app.workers.audio_pipeline.process_audio_asset",
        str(asset_id),
        job_id=(
            f"audio-{asset_id}-r{revision}"
            + (
                f"-p{processing_job_id}"
                if processing_job_id is not None
                else ""
            )
        ),
        job_timeout=audio_job_timeout_seconds(duration_seconds),
        result_ttl=settings.audio_job_result_ttl_seconds,
        retry=(
            Retry(
                max=settings.audio_job_max_retries,
                interval=settings.audio_job_retry_interval_seconds,
            )
            if settings.audio_job_max_retries
            else None
        ),
        meta={
            key: value
            for key, value in {
                "request_id": request_id,
                "processing_job_id": (
                    str(processing_job_id) if processing_job_id is not None else None
                ),
                "asset_id": str(asset_id),
            }.items()
            if value is not None
        },
    )
    return job.id


def process_audio_asset(asset_id: str) -> str:
    from rq import get_current_job

    rq_job = get_current_job()
    meta = rq_job.meta if rq_job is not None and isinstance(rq_job.meta, dict) else {}
    request_id = meta.get("request_id")
    token = request_id_context.set(request_id if isinstance(request_id, str) else None)
    log_context = {
        "event": "pipeline.job",
        "request_id": request_id,
        "rq_job_id": getattr(rq_job, "id", None),
        "processing_job_id": meta.get("processing_job_id"),
        "asset_id": asset_id,
    }
    logger.info("pipeline_job_started", extra={**log_context, "status": "started"})
    try:
        asyncio.run(_process_audio_asset(asset_id))
    except Exception:
        logger.exception("pipeline_job_failed", extra={**log_context, "status": "failed"})
        raise
    else:
        logger.info("pipeline_job_succeeded", extra={**log_context, "status": "succeeded"})
        return asset_id
    finally:
        request_id_context.reset(token)


async def _process_audio_asset(asset_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await process_media_asset(session, UUID(asset_id))
    await engine.dispose()


def run_worker() -> None:
    from rq import Queue, Worker

    settings = get_settings()
    start_metrics_http_server(settings.worker_metrics_port)
    redis = Redis.from_url(settings.redis_url)
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
