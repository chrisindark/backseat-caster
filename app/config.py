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
    CHANNEL_ASSETS_DIR: str = "./data/channel"

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

    # Phase 10.5: branded intro/outro cards prepended/appended to every render.
    # Off by default so a plain install renders exactly the clip it asked for;
    # enable it once and every manual and auto-staged render gets branded.
    BRANDING_ENABLED: bool = False
    BRANDING_CHANNEL_NAME: str = ""
    BRANDING_INTRO_ENABLED: bool = True
    BRANDING_OUTRO_ENABLED: bool = True
    BRANDING_INTRO_TITLE: str = ""
    BRANDING_INTRO_SUBTITLE: str = ""
    BRANDING_OUTRO_TITLE: str = "SUBSCRIBE"
    BRANDING_OUTRO_SUBTITLE: str = ""
    BRANDING_INTRO_SECONDS: float = 1.2
    BRANDING_OUTRO_SECONDS: float = 2.0
    BRANDING_BACKGROUND_COLOR: str = "#0B0D13"
    BRANDING_ACCENT_COLOR: str = "#F43F5E"
    BRANDING_TEXT_COLOR: str = "#FFFFFF"
    BRANDING_FONT_PATH: str | None = None

    # Phase 10: zero-input ingest pipeline (auto-mine on download/upload)
    AUTO_MINE_ON_INGEST: bool = False
    AUTO_MINE_GAME: str | None = None
    AUTO_MINE_MIN_SCORE: float = 0.5
    AUTO_MINE_AUTO_RENDER_TOP_N: int | None = None

    # Phase 10: OBS watch folder (zero-click ingest)
    WATCH_DIR: str | None = None
    WATCH_POLL_INTERVAL_MINUTES: int = 0
    WATCH_STABILITY_SECONDS: int = 10
    WATCH_MIN_FILE_MB: float = 1.0
    WATCH_DELETE_AFTER_INGEST: bool = False
    WATCH_VIDEO_EXTENSIONS: list[str] | str = [
        ".mp4",
        ".mkv",
        ".mov",
        ".webm",
        ".flv",
        ".ts",
        ".m4v",
    ]

    # Phase 8: LLM metadata generation (Universal OpenAI-compatible: Ollama, OpenAI, Groq, Gemini, etc.)
    LLM_METADATA_ENABLED: bool = False
    LLM_BASE_URL: str | None = None
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "llama3.2"
    # Legacy Gemini settings preserved for backwards compatibility
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    @property
    def llm_api_key(self) -> str | None:
        """Resolve the LLM key from dedicated settings, OpenAI, or Gemini/Google env vars."""
        import os

        return (
            self.LLM_API_KEY
            or os.environ.get("OPENAI_API_KEY")
            or self.GEMINI_API_KEY
            or os.environ.get("GOOGLE_API_KEY")
            or None
        )

    @property
    def gemini_api_key(self) -> str | None:
        """Backwards compatibility alias for gemini_api_key."""
        return self.llm_api_key

    @property
    def resolved_llm_base_url(self) -> str:
        """Resolve base URL for OpenAI-compatible chat completions."""
        import os

        if self.LLM_BASE_URL:
            return self.LLM_BASE_URL.rstrip("/")
        # If Google/Gemini key is configured without a custom base URL
        if (
            (self.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY"))
            and not self.LLM_API_KEY
            and not os.environ.get("OPENAI_API_KEY")
        ):
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        # If OpenAI key is configured without a custom base URL
        if os.environ.get("OPENAI_API_KEY") and not self.LLM_API_KEY:
            return "https://api.openai.com/v1"
        # Local-first Ollama default
        return "http://localhost:11434/v1"

    @property
    def resolved_llm_model(self) -> str:
        """Resolve active LLM model name."""
        import os

        if self.LLM_MODEL and self.LLM_MODEL != "llama3.2":
            return self.LLM_MODEL
        if (
            (self.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY"))
            and not self.LLM_API_KEY
            and not os.environ.get("OPENAI_API_KEY")
        ):
            return self.GEMINI_MODEL or "gemini-2.5-flash"
        return self.LLM_MODEL or "llama3.2"

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

    @field_validator("WATCH_VIDEO_EXTENSIONS", mode="before")
    @classmethod
    def assemble_watch_extensions(cls, v: str | list[str]) -> list[str]:
        """Normalise the watch-folder extension allowlist to lowercase dot prefixes."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    items = [str(s) for s in parsed]
                else:
                    items = v.split(",")
            except Exception:
                items = v.split(",")
        else:
            items = [str(s) for s in v]

        normalised: list[str] = []
        for item in items:
            token = item.strip().lower()
            if not token:
                continue
            if not token.startswith("."):
                token = f".{token}"
            if token not in normalised:
                normalised.append(token)
        return normalised

    @property
    def auto_mine_top_n(self) -> int:
        """Resolve how many candidates to auto-render once an ingest mine completes.

        ``AUTO_MINE_AUTO_RENDER_TOP_N`` wins when set; otherwise the Phase 8
        ``AUTO_STAGE_*`` settings decide, keeping one switch for "should this
        pipeline publish clips at all".
        """
        if self.AUTO_MINE_AUTO_RENDER_TOP_N is not None:
            return max(0, int(self.AUTO_MINE_AUTO_RENDER_TOP_N))
        if self.AUTO_STAGE_ENABLED:
            return max(0, int(self.AUTO_STAGE_TOP_N))
        return 0

    @property
    def branding_channel_name(self) -> str:
        """Channel handle shown on branding cards, falling back to the default channel."""
        explicit = (self.BRANDING_CHANNEL_NAME or "").strip()
        if explicit:
            return explicit
        return (self.DEFAULT_YOUTUBE_CHANNEL or "").strip()

    @property
    def watch_path(self) -> Path | None:
        """Resolved watch folder, or None when the zero-click ingest is disabled."""
        if not self.WATCH_DIR or not str(self.WATCH_DIR).strip():
            return None
        return Path(str(self.WATCH_DIR).strip()).expanduser().resolve()

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
    def channel_assets_path(self) -> Path:
        return Path(self.CHANNEL_ASSETS_DIR).resolve()

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
        self.channel_assets_path.mkdir(parents=True, exist_ok=True)
        self.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_client_secrets_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
