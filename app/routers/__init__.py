"""Routers package."""
from app.routers.videos import router as videos_router
from app.routers.renders import router as renders_router

__all__ = ["videos_router", "renders_router"]
