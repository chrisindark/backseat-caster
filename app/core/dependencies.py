from app.services.redis import RedisService


class DependencyContainer:
    _redis_service: RedisService | None = None

    @classmethod
    async def initialize(cls) -> None:
        await cls.get_redis_service()

    @classmethod
    async def get_redis_service(cls) -> RedisService:
        if cls._redis_service is None:
            cls._redis_service = RedisService()
        await cls._redis_service.ping()
        return cls._redis_service

    @classmethod
    async def shutdown(cls) -> None:
        """Close and drop the cached Redis service.

        The asyncio Redis client is bound to the event loop that created it, so
        this singleton must not outlive the application lifespan (and, in tests,
        must not leak across successive ``TestClient`` event loops).
        """
        service = cls._redis_service
        cls._redis_service = None
        if service is not None:
            await service.close()


# FastAPI Depends compatible functions
async def get_redis_service() -> RedisService:
    return await DependencyContainer.get_redis_service()
