"""Routers package."""

from app.routers.renders import router as renders_router
from app.routers.videos import router as videos_router
from app.routers.youtube import router as youtube_router

__all__ = ["renders_router", "videos_router", "youtube_router"]
