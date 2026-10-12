"""Application configuration using Pydantic Settings."""

import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """BackseatCaster application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "app/.env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "BackseatCaster API"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "sqlite:///./data/backseatcaster.db"
    DOWNLOADS_DIR: str = "./data/downloads"
    DEFAULT_YOUTUBE_CHANNEL: str = "@chrisindark"

    # Celery configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    RENDERS_DIR: str = "./data/renders"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def downloads_path(self) -> Path:
        path = Path(self.DOWNLOADS_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def renders_path(self) -> Path:
        path = Path(self.RENDERS_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
