from redis.asyncio import Redis

from orna_atlas.app.core.config import get_settings


def get_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def invalidate_cache(
    *,
    keys: tuple[str, ...] = (),
    patterns: tuple[str, ...] = (),
) -> None:
    """Delete cache entries after persistence without coupling a service to Redis scans."""
    client = get_redis_client()
    try:
        discovered = list(keys)
        for pattern in patterns:
            discovered.extend(
                [key async for key in client.scan_iter(match=pattern, count=100)]
            )
        unique_keys = tuple(dict.fromkeys(discovered))
        if unique_keys:
            await client.delete(*unique_keys)
    except Exception:
        # Redis is an optimization; a cache outage must not roll back committed data.
        pass
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def invalidate_atlas_cache(*, session_keys: tuple[str, ...] = ()) -> None:
    """Invalidate every atlas namespace and optional related session projections."""
    await invalidate_cache(keys=session_keys, patterns=("atlas:*",))
