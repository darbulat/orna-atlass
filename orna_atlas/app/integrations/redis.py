from redis.asyncio import Redis

from orna_atlas.app.core.config import get_settings


def get_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def invalidate_atlas_cache() -> None:
    """Best-effort invalidation after a committed public-content mutation."""
    client = get_redis_client()
    try:
        keys = [key async for key in client.scan_iter(match="atlas:*", count=100)]
        if keys:
            await client.delete(*keys)
    except Exception:
        # Redis is an optimization; a cache outage must not roll back committed data.
        pass
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
