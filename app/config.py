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

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = "3600"
    DATABASE_URL: str = "sqlite:///./data/backseatcaster.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800
    DOWNLOADS_DIR: str = "./data/downloads"
    DEFAULT_YOUTUBE_CHANNEL: str = ""

    # Celery configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    RENDERS_DIR: str = "./data/renders"
    HIGHLIGHTS_DIR: str = "./data/highlights"
    HERO_TEMPLATES_DIR: str = "./data/hero_templates"

    # Preflight configuration
    PREFLIGHT_MIN_DISK_SPACE_GB: float = 2.0

    # YouTube API & OAuth configuration
    YOUTUBE_CLIENT_SECRETS_FILE: str = "./data/client_secrets.json"
    YOUTUBE_TOKEN_FILE: str = "./data/youtube_token.json"
    YOUTUBE_CLIENT_ID: str | None = None
    YOUTUBE_CLIENT_SECRET: str | None = None
    YOUTUBE_REFRESH_TOKEN: str | None = None
    YOUTUBE_REDIRECT_URI: str = "http://localhost:3001/api/v1/youtube/auth/callback"

    # YouTube Data API quota accounting (default: 10,000 units/day, 1,600 per upload)
    YOUTUBE_DAILY_QUOTA_UNITS: int = 10_000
    YOUTUBE_UPLOAD_QUOTA_COST: int = 1_600
    YOUTUBE_QUOTA_TIMEZONE: str = "America/Los_Angeles"

    # Phase 8: autonomous auto-stage & scheduling pipeline
    AUTO_STAGE_ENABLED: bool = False
    AUTO_STAGE_TOP_N: int = 3
    AUTO_STAGE_MIN_SCORE: float = 0.6
    AUTO_STAGE_CLIPPING_MODE: str = "third_person"
    AUTO_STAGE_FIRST_SLOT_HOURS: int = 1
    AUTO_STAGE_INTERVAL_HOURS: int = 24
    AUTO_STAGE_TIMEZONE: str = "Asia/Kolkata"
    AUTO_STAGE_DAILY_SLOTS: list[str] | str = [
        "08:00",
        "12:30",
        "16:00",
        "18:30",
        "20:30",
        "23:00",
    ]

    # Maintenance pipeline: purge uploaded render files and sweep-stage top highlights
    AUTO_CLEANUP_UPLOADED_RENDERS: bool = True
    AUTO_CLEANUP_VOD: bool = False
    AUTO_PIPELINE_INTERVAL_MINUTES: int = 0

    # Phase 8: LLM metadata generation (Gemini)
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    LLM_METADATA_ENABLED: bool = True

    @property
    def gemini_api_key(self) -> str | None:
        """Resolve the Gemini key from dedicated settings or the shared Google env var."""
        import os

        return self.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY") or None

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

    @field_validator("AUTO_PIPELINE_INTERVAL_MINUTES")
    @classmethod
    def validate_pipeline_interval(cls, v: int) -> int:
        return max(0, int(v))

    @field_validator("AUTO_STAGE_DAILY_SLOTS", mode="before")
    @classmethod
    def assemble_daily_slots(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(s).strip() for s in parsed if str(s).strip()]
            except Exception:
                return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        return v

    @property
    def downloads_path(self) -> Path:
        return Path(self.DOWNLOADS_DIR).resolve()

    @property
    def renders_path(self) -> Path:
        return Path(self.RENDERS_DIR).resolve()

    @property
    def highlights_path(self) -> Path:
        return Path(self.HIGHLIGHTS_DIR).resolve()

    @property
    def hero_templates_path(self) -> Path:
        return Path(self.HERO_TEMPLATES_DIR).resolve()

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
        self.highlights_path.mkdir(parents=True, exist_ok=True)
        self.hero_templates_path.mkdir(parents=True, exist_ok=True)
        self.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_client_secrets_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
