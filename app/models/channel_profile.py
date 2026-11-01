"""ChannelProfile SQLAlchemy model."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class ChannelProfile(Base):
    """Singleton row with the creator's channel-wide branding defaults.

    There is exactly one profile (``id == 1``). It is created on first read so
    a fresh install can render and publish without any configuration.
    """

    __tablename__ = "channel_profiles"

    id = Column(Integer, primary_key=True, default=1)

    # Identity
    channel_name = Column(String(255), nullable=True)

    # Presentation Preset (Milestone 1): viral_kill | cinematic_kill | multi_kill_montage
    presentation_preset = Column(String(32), default="viral_kill", nullable=True)

    # Watermark / logo overlay applied by the render engine
    watermark_path = Column(String(1024), nullable=True)
    watermark_enabled = Column(Boolean, default=False)
    watermark_position = Column(String(32), default="bottom_right")
    watermark_opacity = Column(Float, default=0.85)
    watermark_scale = Column(Float, default=0.14)
    watermark_margin = Column(Float, default=0.03)
    watermark_start_seconds = Column(Float, nullable=True)
    watermark_end_seconds = Column(Float, nullable=True)

    # Hook Overlay (Milestone 2)
    hook_enabled = Column(Boolean, nullable=True)
    hook_text = Column(String(255), nullable=True)
    hook_start_seconds = Column(Float, nullable=True)
    hook_duration_seconds = Column(Float, nullable=True)
    hook_position = Column(String(32), nullable=True)

    # Kill & Event Effects (Milestone 3)
    kill_effects_enabled = Column(Boolean, nullable=True)

    # Dynamic Reframing (Milestone 4)
    tracking_enabled = Column(Boolean, nullable=True)

    # Audio & Looping (Milestone 5)
    bg_music_path = Column(String(1024), nullable=True)
    bg_music_volume = Column(Float, nullable=True)
    loop_optimization = Column(Boolean, nullable=True)

    # Output Quality / Frame Rate (Milestone 6)
    target_fps = Column(Integer, nullable=True)

    # Render defaults
    default_framing_preset = Column(String(64), default="third_person")
    default_quality_preset = Column(String(32), default="high")

    # Branded intro/outro cards (Phase 10.5). Nullable so rows created before
    # these columns existed fall back to the BRANDING_* env/seed defaults.
    branding_enabled = Column(Boolean, nullable=True)
    branding_intro = Column(Boolean, nullable=True)
    branding_outro = Column(Boolean, nullable=True)
    branding_intro_seconds = Column(Float, nullable=True)
    branding_outro_seconds = Column(Float, nullable=True)
    branding_intro_title = Column(String(255), nullable=True)
    branding_intro_subtitle = Column(String(255), nullable=True)
    branding_outro_title = Column(String(255), nullable=True)
    branding_outro_subtitle = Column(String(255), nullable=True)
    branding_background_color = Column(String(16), nullable=True)
    branding_accent_color = Column(String(16), nullable=True)
    branding_text_color = Column(String(16), nullable=True)
    branding_font_path = Column(String(1024), nullable=True)

    # Upload ceiling for clip + branded bookends
    max_clip_seconds = Column(Float, nullable=True)

    # CTA voiceover (TTS + bell chime) played over the outro.
    cta_enabled = Column(Boolean, nullable=True)
    cta_style = Column(String(16), nullable=True)
    cta_seconds = Column(Float, nullable=True)
    cta_headline = Column(String(255), nullable=True)
    cta_subtitle = Column(String(255), nullable=True)
    cta_speech_text = Column(Text, nullable=True)
    cta_voice = Column(String(64), nullable=True)
    cta_position = Column(String(32), default="bottom", nullable=True)

    # Publishing defaults
    title_template = Column(String(255), nullable=True)
    pinned_hashtags = Column(Text, nullable=True)  # JSON-encoded list[str]
    default_privacy = Column(String(32), default="public")
    upload_slots = Column(Text, nullable=True)  # JSON-encoded list["HH:MM"]
    upload_timezone = Column(String(64), default="UTC")

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
