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

    # YouTube API & OAuth configuration
    YOUTUBE_CLIENT_SECRETS_FILE: str = "./data/client_secrets.json"
    YOUTUBE_TOKEN_FILE: str = "./data/youtube_token.json"
    YOUTUBE_CLIENT_ID: str | None = None
    YOUTUBE_CLIENT_SECRET: str | None = None
    YOUTUBE_REFRESH_TOKEN: str | None = None
    YOUTUBE_REDIRECT_URI: str = "http://localhost:8000/api/v1/youtube/auth/callback"

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
        return Path(self.DOWNLOADS_DIR).resolve()

    @property
    def renders_path(self) -> Path:
        return Path(self.RENDERS_DIR).resolve()

    @property
    def youtube_token_path(self) -> Path:
        return Path(self.YOUTUBE_TOKEN_FILE).resolve()

    @property
    def youtube_client_secrets_path(self) -> Path:
        return Path(self.YOUTUBE_CLIENT_SECRETS_FILE).resolve()

    def ensure_directories(self) -> None:
        """Ensure all runtime directories and parent folders exist."""
        self.downloads_path.mkdir(parents=True, exist_ok=True)
        self.renders_path.mkdir(parents=True, exist_ok=True)
        self.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_client_secrets_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
