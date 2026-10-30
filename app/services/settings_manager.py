"""Runtime in-app settings persistence and dynamic configuration manager."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

SETTINGS_PERSIST_FILE = Path("./data/settings.json")


class SettingsManager:
    """Manages runtime settings stored in data/settings.json, overriding defaults."""

    @staticmethod
    def get_persisted_settings_path() -> Path:
        return SETTINGS_PERSIST_FILE.resolve()

    @classmethod
    def load_persisted_settings(cls) -> dict[str, Any]:
        """Load settings from data/settings.json if it exists."""
        path = cls.get_persisted_settings_path()
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception as e:
                logger.warning("Failed reading persisted settings from %s: %s", path, e)
        return {}

    @classmethod
    def save_persisted_settings(cls, updates: dict[str, Any]) -> dict[str, Any]:
        """Save settings to data/settings.json and update runtime in-memory settings."""
        path = cls.get_persisted_settings_path()
        current = cls.load_persisted_settings()

        # Update dictionary
        for k, v in updates.items():
            if v is not None:
                current[k] = v

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed writing persisted settings to %s: %s", path, e)

        # Apply in-memory
        cls.apply_settings_to_runtime(current)
        return current

    @classmethod
    def apply_settings_to_runtime(
        cls, settings_dict: dict[str, Any] | None = None
    ) -> None:
        """Apply persisted settings to the global settings instance."""
        data = (
            settings_dict
            if settings_dict is not None
            else cls.load_persisted_settings()
        )

        mapping = {
            "llm_enabled": "LLM_METADATA_ENABLED",
            "llm_base_url": "LLM_BASE_URL",
            "llm_api_key": "LLM_API_KEY",
            "llm_model": "LLM_MODEL",
            "default_clipping_mode": "AUTO_STAGE_CLIPPING_MODE",
            "auto_stage_top_n": "AUTO_STAGE_TOP_N",
            "auto_stage_min_score": "AUTO_STAGE_MIN_SCORE",
            "auto_cleanup_uploaded_renders": "AUTO_CLEANUP_UPLOADED_RENDERS",
            "auto_cleanup_vod": "AUTO_CLEANUP_VOD",
            "youtube_redirect_uri": "YOUTUBE_REDIRECT_URI",
            "auto_mine_on_ingest": "AUTO_MINE_ON_INGEST",
            "watch_dir": "WATCH_DIR",
            "watch_poll_interval_minutes": "WATCH_POLL_INTERVAL_MINUTES",
            "watch_delete_after_ingest": "WATCH_DELETE_AFTER_INGEST",
            # Phase 10.5: branded intro/outro cards
            "branding_enabled": "BRANDING_ENABLED",
            "branding_channel_name": "BRANDING_CHANNEL_NAME",
            "branding_intro_enabled": "BRANDING_INTRO_ENABLED",
            "branding_outro_enabled": "BRANDING_OUTRO_ENABLED",
            "branding_intro_seconds": "BRANDING_INTRO_SECONDS",
            "branding_outro_seconds": "BRANDING_OUTRO_SECONDS",
            "branding_intro_title": "BRANDING_INTRO_TITLE",
            "branding_intro_subtitle": "BRANDING_INTRO_SUBTITLE",
            "branding_outro_title": "BRANDING_OUTRO_TITLE",
            "branding_outro_subtitle": "BRANDING_OUTRO_SUBTITLE",
            "branding_background_color": "BRANDING_BACKGROUND_COLOR",
            "branding_accent_color": "BRANDING_ACCENT_COLOR",
            "branding_text_color": "BRANDING_TEXT_COLOR",
        }

        for api_key, attr_name in mapping.items():
            if api_key in data and hasattr(settings, attr_name):
                setattr(settings, attr_name, data[api_key])
