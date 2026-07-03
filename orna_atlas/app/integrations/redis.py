from redis.asyncio import Redis

from orna_atlas.app.core.config import get_settings


def get_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
