import redis

from app.config import settings


def is_celery_broker_online() -> bool:
    try:
        client = redis.from_url(
            settings.CELERY_BROKER_URL, socket_timeout=0.2, socket_connect_timeout=0.2
        )
        client.ping()
        return True
    except Exception:
        return False
