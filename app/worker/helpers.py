import time

import redis

from app.config import settings

_broker_status_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL_SECONDS = 5.0


def clear_broker_online_cache() -> None:
    """Clear cached broker availability status."""
    _broker_status_cache.clear()


def is_celery_broker_online(force_refresh: bool = False) -> bool:
    """Check if the Celery Redis broker is reachable, caching status for 5 seconds."""
    cache_key = settings.CELERY_BROKER_URL
    now = time.monotonic()

    if not force_refresh and cache_key in _broker_status_cache:
        status, timestamp = _broker_status_cache[cache_key]
        if now - timestamp < _CACHE_TTL_SECONDS:
            return status

    client = None
    online = False
    try:
        client = redis.from_url(
            settings.CELERY_BROKER_URL, socket_timeout=0.2, socket_connect_timeout=0.2
        )
        client.ping()
        online = True
    except redis.RedisError, OSError:
        online = False
    finally:
        if client is not None:
            try:
                client.close()
            except redis.RedisError, OSError:
                pass

    _broker_status_cache[cache_key] = (online, now)
    return online
