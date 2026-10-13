"""FastAPI Application entry point."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logger import setup_logger
from app.core.middlewares import CorrelationIdMiddleware
from app.core.responses import BaseResponse, register_exception_handlers
from app.routers import renders_router, videos_router, youtube_router

# Initialize the custom colored logger with correlation ID
setup_logger()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure local storage directories exist
    settings.ensure_directories()
    logger.info(
        "BackseatCaster API initialized. Downloads: %s, Renders: %s",
        settings.downloads_path,
        settings.renders_path,
    )
    yield
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


@app.get(f"{settings.API_PREFIX}/health", response_model=BaseResponse[dict])
def health_check():
    return BaseResponse.success_response(
        response={
            "status": "healthy",
            "version": settings.VERSION,
            "downloads_dir": str(settings.downloads_path),
        }
    )


# Register routers
app.include_router(videos_router, prefix=settings.API_PREFIX)
app.include_router(renders_router, prefix=settings.API_PREFIX)
app.include_router(youtube_router, prefix=settings.API_PREFIX)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
