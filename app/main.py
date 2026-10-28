"""FastAPI Application entry point."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.dependencies import DependencyContainer
from app.core.logger import setup_logger
from app.core.middlewares import CorrelationIdMiddleware
from app.core.responses import BaseResponse, register_exception_handlers
from app.routers import (
    health_router,
    highlights_router,
    renders_router,
    videos_router,
    youtube_router,
)
from app.services.preflight import log_preflight_report, run_preflight_checks

# Initialize the custom colored logger with correlation ID
setup_logger()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await DependencyContainer.initialize()
    # Ensure local storage directories exist
    settings.ensure_directories()

    # Run startup preflight verification for media tools & storage
    preflight_report = run_preflight_checks()
    log_preflight_report(preflight_report)

    logger.info(
        "BackseatCaster API initialized. Downloads: %s, Renders: %s, Highlights: %s",
        settings.downloads_path,
        settings.renders_path,
        settings.highlights_path,
    )
    yield
    await DependencyContainer.shutdown()
    logger.info("BackseatCaster API shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="BackseatCaster backend for YouTube ingestion, video management, and highlight clip rendering",
    lifespan=lifespan,
)

# Register unified BaseResponse exception handlers
register_exception_handlers(app)

app.add_middleware(CorrelationIdMiddleware)
# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS
    if isinstance(settings.CORS_ORIGINS, list)
    else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Request-ID"],
)


@app.get("/", response_model=BaseResponse[dict])
def root():
    return BaseResponse.success_response(
        response={
            "app": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "api_prefix": settings.API_PREFIX,
            "default_channel": settings.DEFAULT_YOUTUBE_CHANNEL,
        }
    )


# Register routers
app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(videos_router, prefix=settings.API_PREFIX)
app.include_router(renders_router, prefix=settings.API_PREFIX)
app.include_router(youtube_router, prefix=settings.API_PREFIX)
app.include_router(highlights_router, prefix=settings.API_PREFIX)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
