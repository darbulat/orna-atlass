from collections.abc import Callable
import time

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.integrations.redis import get_redis_client


def rate_limit(scope: str, limit_getter: Callable[[], int]):
    """Create a fail-closed, fixed-window Redis rate-limit dependency."""

    async def enforce(request: Request) -> None:
        settings = get_settings()
        identity = request.client.host if request.client else "unknown"
        bucket = int(time.time() // settings.rate_limit_window_seconds)
        key = f"rate-limit:{scope}:{identity}:{bucket}"
        client = get_redis_client()
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, settings.rate_limit_window_seconds + 1)
        except RedisError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limit service unavailable",
            ) from exc
        finally:
            try:
                await client.aclose()
            except RedisError:
                pass
        limit = limit_getter()
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            )

    return enforce


auth_rate_limit = rate_limit("auth", lambda: get_settings().auth_rate_limit)
playback_rate_limit = rate_limit("playback", lambda: get_settings().playback_rate_limit)
search_rate_limit = rate_limit("search", lambda: get_settings().search_rate_limit)
