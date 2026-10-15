import asyncio
import logging

from redis import asyncio as aioredis

from app.config import settings
from app.core.logger import log_latency

logger = logging.getLogger(__name__)

# Cap how long a single Redis probe may block startup/request handling so that a
# slow or black-holed host cannot stall the application.
REDIS_PING_TIMEOUT_SECONDS = 2.0


class RedisService:
    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self.redis = aioredis.from_url(self.redis_url, decode_responses=True)

        self.ttl = int(settings.REDIS_TTL)
        logger.info(f"Connecting to Redis at {self.redis_url}")

    async def ping(self) -> bool:
        """Probe Redis, returning True on success.

        Never raises: a missing, slow, or black-holed Redis must not break
        application startup or request handling. Broadly catching here also
        absorbs ``RuntimeError`` from reusing a client bound to a closed event
        loop instead of leaking it into callers.
        """
        try:
            if await asyncio.wait_for(
                self.redis.ping(), timeout=REDIS_PING_TIMEOUT_SECONDS
            ):
                logger.info("Redis connection is successful")
                return True
        except Exception as e:
            logger.error(f"Error in Redis connection: {e}")
        return False

    @log_latency()
    async def get(self, key: str) -> bytes | str | None:
        """Retrieve an exact match from Redis cache."""
        try:
            cached_data = await self.redis.get(key)
            if cached_data:
                logger.info("Redis exact cache hit!")
                return cached_data
        except Exception as e:
            logger.error(f"Failed to get data from Redis: {e}")

        return None

    @log_latency()
    async def set(
        self, key: str, value: str, ttl: int | None = None
    ) -> bool | bytes | str | None:
        """Cache the exact response for a prompt in Redis."""
        try:
            expire_time = ttl if ttl is not None else self.ttl
            logger.info("Successfully saved exact match to Redis")
            response = await self.redis.set(key, value, ex=expire_time)
            return response
        except Exception as e:
            logger.error(f"Failed to save data to Redis: {e}")

        return None

    @log_latency()
    async def delete(self, key: str) -> bytes | int | str | None:
        """Delete a key from Redis cache."""
        try:
            return await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete key from Redis: {e}")
            return None

    async def close(self) -> None:
        """Close the underlying connection pool. Safe to call more than once."""
        try:
            # redis>=5.0.1 prefers aclose(); fall back for older clients.
            close = getattr(self.redis, "aclose", None) or self.redis.close
            await close()
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")

    async def expire(self, key: str, seconds: int):
        try:
            return await self.redis.expire(key, seconds)
        except Exception as e:
            logger.error(f"Failed to expire key in Redis: {e}")

        return None

    async def incr(self, key: str):
        try:
            return await self.redis.incr(key)
        except Exception as e:
            logger.error(f"Failed to increment key in Redis: {e}")

        return None

    async def incrby(self, key: str, amount: int):
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment key in Redis: {e}")

        return None

    async def decr(self, key: str):
        try:
            return await self.redis.decr(key)
        except Exception as e:
            logger.error(f"Failed to decrement key in Redis: {e}")

        return None

    async def decrby(self, key: str, amount: int):
        try:
            return await self.redis.decrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to decrement key in Redis: {e}")

        return None
