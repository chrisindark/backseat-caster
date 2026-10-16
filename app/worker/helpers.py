import time

import redis
from celery import Celery

from app.config import settings

_broker_status_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL_SECONDS = 5.0


def clear_broker_online_cache() -> None:
    """Clear cached broker availability status."""
    _broker_status_cache.clear()


def is_celery_broker_online(force_refresh: bool = False) -> bool:
    """Check if Celery can actually process tasks.

    Redis being reachable is not sufficient: jobs dispatched to a broker with
    no live worker never run and leave the UI stuck indefinitely. We therefore
    also require at least one responsive worker before claiming Celery is online.
    """
    cache_key = settings.CELERY_BROKER_URL
    now = time.monotonic()

    if not force_refresh and cache_key in _broker_status_cache:
        status, timestamp = _broker_status_cache[cache_key]
        if now - timestamp < _CACHE_TTL_SECONDS:
            return status

    online = False
    client = None
    try:
        client = redis.from_url(
            settings.CELERY_BROKER_URL, socket_timeout=0.2, socket_connect_timeout=0.2
        )
        client.ping()

        app = Celery(broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
        inspector = app.control.inspect(timeout=0.2)
        try:
            workers = inspector.ping()
        except Exception:
            workers = None
        online = isinstance(workers, dict) and bool(workers)
    except Exception:
        online = False
    finally:
        if client is not None:
            try:
                client.close()
            except (redis.RedisError, OSError):
                pass

    _broker_status_cache[cache_key] = (online, now)
    return online
