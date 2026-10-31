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

ALL_CLIPPING_MODES: list[str] = [
    "landscape",
    "vertical_blur",
    "third_person",
    "direct_crop",
    "cinematic",
    "custom",
]

DEFAULT_CLIPPING_MODES: list[str] = [
    "third_person",
]

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


class WatermarkConfig(BaseModel):
    """Channel watermark/logo overlaid on every rendered clip."""

    enabled: bool = Field(False, description="Master switch for the logo overlay")
    path: str | None = Field(None, description="Absolute path to the logo image")
    position: Literal[
        "top_left", "top_right", "bottom_left", "bottom_right", "center"
    ] = "bottom_right"
    opacity: float = Field(0.85, ge=0.05, le=1.0)
    scale: float = Field(
        0.14,
        ge=0.02,
        le=0.6,
        description="Logo width as a fraction of the output width",
    )
    margin: float = Field(
        0.03,
        ge=0.0,
        le=0.2,
        description="Edge margin as a fraction of the output short edge",
    )

    @property
    def active(self) -> bool:
        return bool(self.enabled and self.path and Path(self.path).exists())

    def describe(self) -> dict[str, Any]:
        """Serialisable summary recorded in the render manifest."""
        return {
            "enabled": self.active,
            "position": self.position,
            "opacity": self.opacity,
            "scale": self.scale,
            "margin": self.margin,
        }


class BrandingConfig(BaseModel):
    """Branded intro/outro card settings applied to every rendered clip.

    Cards are rasterised locally with Pillow and concatenated in the same FFmpeg
    pass as the clip, so branding costs no extra encode generation.
    """

    enabled: bool = Field(
        False, description="Master switch; when off renders are untouched"
    )
    intro: bool = Field(True, description="Render the intro card when enabled")
    outro: bool = Field(True, description="Render the outro card when enabled")

    intro_seconds: float = Field(
        1.2, ge=0.2, le=5.0, description="Intro card duration in seconds"
    )
    outro_seconds: float = Field(
        2.0, ge=0.2, le=10.0, description="Outro card duration in seconds"
    )

    intro_title: str = Field("", description="Intro headline (defaults to channel)")
    intro_subtitle: str = Field("", description="Intro secondary line")
    outro_title: str = Field("SUBSCRIBE", description="Outro headline")
    outro_subtitle: str = Field(
        "", description="Outro secondary line (defaults to channel handle)"
    )
    channel_name: str = Field("", description="Channel handle shown on cards")

    background_color: str = Field("#0B0D13", description="Card background (hex)")
    accent_color: str = Field("#F43F5E", description="Accent rule/text (hex)")
    text_color: str = Field("#FFFFFF", description="Headline text colour (hex)")
    font_path: str | None = Field(
        None, description="Optional TTF/OTF override for card typography"
    )

    @property
    def has_intro(self) -> bool:
        return self.enabled and self.intro

    @property
    def has_outro(self) -> bool:
        return self.enabled and self.outro

    @property
    def has_bookends(self) -> bool:
        """True when at least one card should be rendered."""
        return self.has_intro or self.has_outro

    def resolved_intro_title(self) -> str:
        """Headline for the intro card."""
        return (self.intro_title or self.channel_name or "BACKSEATCASTER").strip()

    def resolved_outro_subtitle(self) -> str:
        """Secondary line for the outro card."""
        return (self.outro_subtitle or self.channel_name or "").strip()

    def describe(self) -> dict[str, Any]:
        """Serialisable summary recorded in the render manifest."""
        return {
            "enabled": self.has_bookends,
            "intro": self.has_intro,
            "outro": self.has_outro,
            "intro_seconds": self.intro_seconds if self.has_intro else 0.0,
            "outro_seconds": self.outro_seconds if self.has_outro else 0.0,
            "intro_title": self.resolved_intro_title() if self.has_intro else None,
            "outro_title": self.outro_title if self.has_outro else None,
            "channel_name": self.channel_name or None,
        }


#: Hard ceiling for a *composed* clip (source window + intro/outro cards).
DEFAULT_MAX_CLIP_SECONDS = 90.0

#: Soft checkpoints below the ceiling. Everything up to the ceiling publishes as
#: short-form video; these only label how long a clip ended up, so a 61s or 80s
#: result is never rejected and never silently trimmed.
SHORTS_DURATION_TIERS: tuple[float, ...] = (60.0, 72.0, 88.0)

#: Upload labels, from the shortest tier upwards.
DURATION_TIER_LABELS: tuple[str, ...] = ("shorts", "extended", "long", "ceiling")
OVER_CEILING_LABEL = "over_ceiling"


class CtaConfig(BaseModel):
    """In-video CTA overlay / outro voiceover settings."""

    enabled: bool = False
    style: Literal["outro_card", "overlay"] = "outro_card"
    seconds: float = Field(3.5, ge=2.0, le=10.0)
    headline: str = "SUBSCRIBE & TAP THE BELL"
    subtitle: str = "Click the bell for more clips"
    speech_text: str = "Subscribe to the channel and tap the bell for more clips."
    voice: str = "en-US-ChristopherNeural"


def default_branding_config() -> BrandingConfig:
    """Build branding defaults from application settings (env or /setup UI)."""
    return BrandingConfig(
        enabled=settings.BRANDING_ENABLED,
        intro=settings.BRANDING_INTRO_ENABLED,
        outro=settings.BRANDING_OUTRO_ENABLED,
        intro_seconds=settings.BRANDING_INTRO_SECONDS,
        outro_seconds=settings.BRANDING_OUTRO_SECONDS,
        intro_title=settings.BRANDING_INTRO_TITLE,
        intro_subtitle=settings.BRANDING_INTRO_SUBTITLE,
        outro_title=settings.BRANDING_OUTRO_TITLE,
        outro_subtitle=settings.BRANDING_OUTRO_SUBTITLE,
        channel_name=settings.branding_channel_name,
        background_color=settings.BRANDING_BACKGROUND_COLOR,
        accent_color=settings.BRANDING_ACCENT_COLOR,
        text_color=settings.BRANDING_TEXT_COLOR,
        font_path=settings.BRANDING_FONT_PATH,
    )


class DurationBudget(BaseModel):
    """How much clip fits under the upload ceiling once cards are added.

    The ceiling applies to the *composed* duration (clip window + intro/outro),
    because that is what lands on YouTube. Soft tiers inside the ceiling let a
    creator upload a 61s or 80s clip without the pipeline complaining.
    """

    max_seconds: float = Field(
        DEFAULT_MAX_CLIP_SECONDS, gt=0, description="Ceiling for clip + bookends"
    )
    bookend_seconds: float = Field(
        0.0, ge=0.0, description="Intro + outro seconds added to every render"
    )
    tiers: tuple[float, ...] = Field(
        default=SHORTS_DURATION_TIERS,
        description="Soft upload checkpoints inside the ceiling",
    )

    @property
    def clip_budget(self) -> float:
        """Longest source window that still fits under the ceiling."""
        return max(1.0, round(self.max_seconds - self.bookend_seconds, 2))

    def composed_seconds(self, clip_seconds: float) -> float:
        """Duration that will actually be uploaded for a given clip window."""
        return round(max(0.0, clip_seconds) + self.bookend_seconds, 2)

    def fits(self, clip_seconds: float, *, tolerance: float = 0.05) -> bool:
        """True when the composed clip stays at or under the ceiling."""
        return self.composed_seconds(clip_seconds) <= self.max_seconds + tolerance

    def clamp(self, clip_seconds: float) -> float:
        """Trim a clip window so the composed clip fits the ceiling."""
        return round(min(max(0.0, clip_seconds), self.clip_budget), 2)

    def tier_for_composed(self, composed_seconds: float) -> str:
        """Label a composed duration: shorts, extended, long, ceiling or over."""
        for index, checkpoint in enumerate(self.tiers):
            if composed_seconds <= checkpoint + 0.05:
                return DURATION_TIER_LABELS[min(index, len(DURATION_TIER_LABELS) - 1)]
        if composed_seconds <= self.max_seconds + 0.05:
            return DURATION_TIER_LABELS[-1]
        return OVER_CEILING_LABEL

    def tier(self, clip_seconds: float) -> str:
        """Label the composed duration produced by ``clip_seconds``."""
        return self.tier_for_composed(self.composed_seconds(clip_seconds))

    def is_uploadable(self, clip_seconds: float) -> bool:
        """Every tier at or below the ceiling is uploadable as short-form."""
        return self.fits(clip_seconds)

    def describe(self, clip_seconds: float) -> dict[str, Any]:
        """Serialisable summary recorded in the render manifest."""
        return self.describe_composed(self.composed_seconds(clip_seconds))

    def describe_composed(self, composed_seconds: float) -> dict[str, Any]:
        """Same summary, starting from the duration that was actually encoded."""
        composed = round(max(0.0, composed_seconds), 2)
        return {
            "max_seconds": self.max_seconds,
            "bookend_seconds": self.bookend_seconds,
            "clip_budget_seconds": self.clip_budget,
            "tiers": list(self.tiers),
            "composed_seconds": composed,
            "tier": self.tier_for_composed(composed),
            "uploadable": composed <= self.max_seconds + 0.05,
        }

    def over_ceiling_message(self, clip_seconds: float) -> str:
        """Human-readable explanation for a request that is too long."""
        composed = self.composed_seconds(clip_seconds)
        return (
            f"Clip window {clip_seconds:.1f}s + {self.bookend_seconds:.1f}s of branded "
            f"bookends = {composed:.1f}s, over the {self.max_seconds:.0f}s ceiling. "
            f"Use a window of {self.clip_budget:.1f}s or less, disable a card, or "
            f"raise Max clip length in your channel profile."
        )


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

    # Audio Mixing & Loudness Normalization
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
    normalize_audio: bool = Field(
        True,
        description="Enable EBU R128 audio loudness normalization (YouTube Shorts standard)",
    )
    target_lufs: float = Field(
        -14.0,
        description="Integrated loudness target in LUFS (-14 LUFS standard for YouTube Shorts)",
    )
    loudnorm_true_peak: float = Field(
        -1.5,
        description="Maximum True Peak level in dBTP",
    )
    loudnorm_lra: float = Field(
        11.0,
        description="Target loudness range in LU",
    )

    # Branded intro/outro cards (Phase 10.5)
    branding: BrandingConfig = Field(default_factory=default_branding_config)

    # CTA voiceover / in-video overlay
    cta: CtaConfig = Field(default_factory=CtaConfig)

    # Upload ceiling for the composed clip (source window + bookends)
    max_total_seconds: float = Field(
        DEFAULT_MAX_CLIP_SECONDS,
        gt=0,
        description="Ceiling applied to clip window + branded bookends",
    )

    # Tier 3: channel watermark/logo overlay (applied to every render)
    watermark: WatermarkConfig = Field(default_factory=WatermarkConfig)

    # Output defaults
    default_output_root: Path = settings.renders_path
    api_prefix: str = settings.API_PREFIX

    # Duration Boundary Clamping
    clamp_to_duration: bool = Field(
        True,
        description="Automatically clamp clip duration to source video duration instead of raising ValidationError",
    )
    min_clip_duration: float = Field(
        0.5,
        ge=0.1,
        description="Minimum allowable clip duration in seconds",
    )

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
