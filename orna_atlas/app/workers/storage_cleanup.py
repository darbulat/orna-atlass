from __future__ import annotations

import argparse
import asyncio
import logging

from orna_atlas.app.db import models as _models  # noqa: F401
from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.modules.media.service import process_due_storage_cleanup_jobs

logger = logging.getLogger(__name__)


async def run_once(*, limit: int = 50) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        return await process_due_storage_cleanup_jobs(session, limit=limit)


async def run_worker(*, limit: int = 50, interval_seconds: int = 60) -> None:
    while True:
        try:
            await run_once(limit=limit)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "storage_cleanup_iteration_failed",
                extra={"event": "storage.cleanup.iteration"},
            )
        await asyncio.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable object-storage cleanup jobs")
    parser.add_argument("mode", choices=("once", "worker"), nargs="?", default="once")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.limit < 1 or args.interval_seconds < 1:
        parser.error("--limit and --interval-seconds must be positive")
    try:
        if args.mode == "worker":
            asyncio.run(
                run_worker(limit=args.limit, interval_seconds=args.interval_seconds)
            )
        else:
            succeeded, failed = asyncio.run(run_once(limit=args.limit))
            print(f"Storage cleanup complete: {succeeded} succeeded, {failed} failed")
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
