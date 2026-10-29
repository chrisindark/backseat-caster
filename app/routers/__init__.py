from app.routers.health import router as health_router
from app.routers.highlights import router as highlights_router
from app.routers.renders import router as renders_router
from app.routers.setup import router as setup_router
from app.routers.videos import router as videos_router
from app.routers.youtube import router as youtube_router

__all__ = [
    "health_router",
    "highlights_router",
    "renders_router",
    "setup_router",
    "videos_router",
    "youtube_router",
]
