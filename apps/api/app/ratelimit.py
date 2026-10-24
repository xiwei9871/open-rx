"""Fixed-window rate limiting on Redis.

Fail-open in dev/test, fail-closed in prod: if Redis is unreachable a prod
deployment denies rather than silently permitting brute force.
"""
import logging

from app.config import get_settings

_s = get_settings()
_r = None


def _client():
    global _r
    if _r is None:
        import redis.asyncio as aioredis
        _r = aioredis.from_url(_s.redis_url, decode_responses=True,
                               socket_connect_timeout=2, socket_timeout=2)
    return _r


async def allow(bucket: str, ident: str, limit: int, window_s: int) -> bool:
    """True if the (bucket, ident) pair is under `limit` hits per window."""
    key = f"rl:{bucket}:{ident}"
    try:
        n = await _client().incr(key)
        if n == 1:
            await _client().expire(key, window_s)
        return n <= limit
    except Exception as e:
        logging.getLogger("easyrs").warning("rate limiter unavailable: %s", e)
        return _s.env != "prod"


async def reset(bucket: str, ident: str) -> None:
    """Delete a bucket key (test hygiene — Redis persists between runs)."""
    try:
        await _client().delete(f"rl:{bucket}:{ident}")
    except Exception:
        pass
