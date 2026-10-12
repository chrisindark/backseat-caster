"""Rendering configuration and defaults."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.config import settings

CROP_PADDING_PRESETS: dict[str, float] = {
    "third_person": 0.3333,  # 33.33% total blur padding (~16.66% top / ~16.66% bottom)
    "cinematic": 0.25,  # 25% total blur padding (~12.5% top / ~12.5% bottom)
    "direct_crop": 0.0,  # 0% blur (traditional 100% full-height center crop)
}

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "high": {  # Balanced broadcast/studio fidelity (~35-40 MB/min, matches 1080p source)
        "videotoolbox_bitrate": "5M",
        "videotoolbox_maxrate": "7M",
        "videotoolbox_bufsize": "10M",
        "libx264_crf": 21,
    },
    "compact": {  # Optimized for quick mobile sharing / web preview (~25 MB/min)
        "videotoolbox_bitrate": "3.5M",
        "videotoolbox_maxrate": "5M",
        "videotoolbox_bufsize": "7M",
        "libx264_crf": 24,
    },
    "archive": {  # High-bitrate studio mastering (~120 MB/min)
        "videotoolbox_bitrate": "20M",
        "videotoolbox_maxrate": "25M",
        "videotoolbox_bufsize": "40M",
        "libx264_crf": 17,
    },
}


class RenderConfig(BaseModel):
    """Configuration for clip rendering engine."""

    # Output dimensions
    landscape_width: int = 1920
    landscape_height: int = 1080
    vertical_width: int = 1080
    vertical_height: int = 1920

    # Vertical Crop Composition
    crop_preset: Literal["third_person", "cinematic", "direct_crop", "custom"] = (
        "third_person"
    )
    crop_blur_padding: float = Field(
        0.3333,
        ge=0.0,
        le=0.6,
        description="Fraction of total height for blurred top/bottom padding (0.0 for full direct crop, 0.3333 for 1/3 blur)",
    )

    # Video Encoding (High Quality & Bandwidth-Optimized)
    preferred_encoder: Literal["auto", "h264_videotoolbox", "libx264"] = "auto"
    quality_preset: Literal["high", "compact", "archive", "custom"] = "high"
    videotoolbox_bitrate: str = "5M"
    videotoolbox_maxrate: str = "7M"
    videotoolbox_bufsize: str = "10M"
    libx264_crf: int = 21  # Visually lossless relative to source
    libx264_preset: str = "medium"

    # Audio Mixing
    unducked_game_gain: float = Field(
        1.0, description="Volume of game audio when no voiceover is used"
    )
    ducked_game_gain: float = Field(
        0.30, description="Volume of game audio when voiceover is present"
    )
    narration_gain: float = Field(1.0, description="Volume of voiceover narration")
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48000
    limiter_enabled: bool = True

    # Output defaults
    default_output_root: Path = settings.renders_path
    api_prefix: str = settings.API_PREFIX

    @model_validator(mode="before")
    @classmethod
    def apply_quality_preset(cls, data: Any) -> Any:
        if isinstance(data, dict):
            preset = data.get("quality_preset")
            if preset and preset in QUALITY_PRESETS:
                for k, v in QUALITY_PRESETS[preset].items():
                    data.setdefault(k, v)
        return data


default_render_config = RenderConfig()
