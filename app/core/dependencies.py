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


# FastAPI Depends compatible functions
async def get_redis_service() -> RedisService:
    return await DependencyContainer.get_redis_service()
