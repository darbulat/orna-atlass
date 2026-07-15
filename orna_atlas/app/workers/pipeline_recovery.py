from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.modules.media import repository
from orna_atlas.app.modules.media.service import recover_stale_asset_processing

logger = logging.getLogger(__name__)


async def run_once(*, limit: int = 25) -> tuple[int, int]:
    stale_before = datetime.now(UTC) - timedelta(
        seconds=get_settings().pipeline_stale_after_seconds
    )
    async with AsyncSessionLocal() as session:
        asset_ids = await repository.stale_processing_asset_ids(
            session,
            stale_before=stale_before,
            limit=limit,
        )
    recovered = 0
    failed = 0
    for asset_id in asset_ids:
        try:
            async with AsyncSessionLocal() as session:
                if await recover_stale_asset_processing(session, asset_id):
                    recovered += 1
        except Exception:
            failed += 1
            logger.exception(
                "stale_pipeline_recovery_failed",
                extra={"event": "pipeline.recovery", "asset_id": str(asset_id)},
            )
    return recovered, failed


async def run_worker(*, limit: int = 25, interval_seconds: int = 300) -> None:
    while True:
        try:
            await run_once(limit=limit)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "pipeline_recovery_iteration_failed",
                extra={"event": "pipeline.recovery.iteration"},
            )
        await asyncio.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover stale audio pipeline jobs")
    parser.add_argument("mode", choices=("once", "worker"), nargs="?", default="once")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.limit < 1 or args.interval_seconds < 1:
        parser.error("--limit and --interval-seconds must be positive")
    try:
        if args.mode == "worker":
            asyncio.run(
                run_worker(limit=args.limit, interval_seconds=args.interval_seconds)
            )
        else:
            recovered, failed = asyncio.run(run_once(limit=args.limit))
            print(f"Pipeline recovery complete: {recovered} recovered, {failed} failed")
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
