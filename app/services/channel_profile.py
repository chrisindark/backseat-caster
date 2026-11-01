"""Channel profile persistence and brand-default resolution."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.channel_profile import ChannelProfile
from app.rendering.config import (
    CROP_PADDING_PRESETS,
    QUALITY_PRESETS,
    BrandingConfig,
    CtaConfig,
    DurationBudget,
    HookConfig,
    KillEffectsConfig,
    LoopConfig,
    MusicConfig,
    TrackingConfig,
    WatermarkConfig,
    default_branding_config,
)
from app.rendering.presentation import (
    DEFAULT_PRESENTATION_PRESET,
    PRESENTATION_PRESETS,
    get_presentation_preset,
)
from app.schemas.channel import (
    ChannelProfileResponse,
    ChannelProfileUpdate,
    PresentationPresetResponse,
    normalize_hashtags,
)

logger = logging.getLogger(__name__)

PROFILE_ID = 1
CTA_STYLES = ("outro_card", "overlay")
WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _cta_style(raw: str | None) -> str:
    """Coerce a stored CTA style, so a legacy/unknown value cannot break renders."""
    return raw if raw in CTA_STYLES else "outro_card"


def extract_candidate_events(
    details: dict[str, Any], clip_start: float, clip_end: float
) -> list[dict[str, Any]]:
    """Extract deterministic event moments (relative to clip start) from highlight metadata."""
    raw_events: list[tuple[float, str, float]] = []

    # 1. Trigger events
    for trigger in details.get("trigger_events", []):
        t_abs = trigger.get("time")
        if t_abs is not None and clip_start <= float(t_abs) <= clip_end:
            rel_t = round(float(t_abs) - clip_start, 3)
            label = str(trigger.get("label") or "Elimination")
            conf = float(trigger.get("confidence", 1.0))
            raw_events.append((rel_t, label, conf))

    # 2. Killfeed rows
    killfeed = details.get("killfeed_chain") or {}
    for row in killfeed.get("rows", []):
        t_abs = row.get("timestamp")
        action = str(row.get("action") or "").lower()
        if t_abs is not None and clip_start <= float(t_abs) <= clip_end:
            if action in ("elimination", "knock"):
                rel_t = round(float(t_abs) - clip_start, 3)
                label = "Elimination"
                conf = float(row.get("confidence", 0.8))
                raw_events.append((rel_t, label, conf))

    raw_events.sort(key=lambda x: x[0])

    merged: list[dict[str, Any]] = []
    for rel_t, label, conf in raw_events:
        if merged and abs(merged[-1]["time"] - rel_t) < 0.35:
            # Upgrade label if current is more specific
            if any(
                k in label.lower() for k in ("wipe", "ko", "double", "triple", "quad")
            ):
                merged[-1]["label"] = label
            merged[-1]["confidence"] = max(merged[-1]["confidence"], conf)
        else:
            merged.append({"time": rel_t, "label": label, "confidence": conf})

    combo = 1
    for ev in merged:
        ev["combo"] = combo
        if ev["label"].lower() in ("elimination", "knock"):
            if combo == 2:
                ev["label"] = "DOUBLE KO"
            elif combo == 3:
                ev["label"] = "TRIPLE KO"
            elif combo == 4:
                ev["label"] = "QUAD KO"
            elif combo >= 5:
                ev["label"] = "MULTI KO"
        combo += 1

    return merged


MAX_WATERMARK_BYTES = 15 * 1024 * 1024

#: Free-text columns that are stored as ``NULL`` when blank, so the render
#: engine falls back to the ``BRANDING_*`` defaults instead of showing "  ".
TEXT_FIELDS = frozenset(
    {
        "title_template",
        "channel_name",
        "presentation_preset",
        "branding_intro_title",
        "branding_intro_subtitle",
        "branding_outro_title",
        "branding_outro_subtitle",
        "branding_font_path",
        "branding_background_color",
        "branding_accent_color",
        "branding_text_color",
        "cta_headline",
        "cta_subtitle",
        "cta_speech_text",
        "cta_voice",
        "hook_text",
        "hook_position",
        "bg_music_path",
    }
)


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _default_slots() -> list[str]:
    raw = settings.AUTO_STAGE_DAILY_SLOTS
    values = raw if isinstance(raw, list) else str(raw).split(",")
    slots: list[str] = []
    for value in values:
        token = str(value).strip()
        parts = token.split(":")
        if len(parts) != 2:
            continue
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if 0 <= hour < 24 and 0 <= minute < 60:
            normalized = f"{hour:02d}:{minute:02d}"
            if normalized not in slots:
                slots.append(normalized)
    return sorted(slots)


class ChannelProfileService:
    """Owns the single channel profile row and derives effective defaults."""

    @classmethod
    def get_or_create(cls, db: Session) -> ChannelProfile:
        """Return the singleton profile, creating it from current settings once."""
        profile = (
            db.query(ChannelProfile).filter(ChannelProfile.id == PROFILE_ID).first()
        )
        if profile:
            return profile

        framing = (settings.AUTO_STAGE_CLIPPING_MODE or "third_person").strip()
        if framing not in CROP_PADDING_PRESETS and framing not in (
            "vertical_blur",
            "custom",
        ):
            framing = "third_person"

        profile = ChannelProfile(
            id=PROFILE_ID,
            channel_name=(settings.DEFAULT_YOUTUBE_CHANNEL or "").strip() or None,
            presentation_preset=DEFAULT_PRESENTATION_PRESET,
            watermark_path=None,
            watermark_enabled=False,
            watermark_position="bottom_right",
            watermark_opacity=0.85,
            watermark_scale=0.14,
            watermark_margin=0.03,
            default_framing_preset=framing,
            default_quality_preset="high",
            title_template=None,
            pinned_hashtags=json.dumps([]),
            default_privacy="public",
            upload_slots=json.dumps(_default_slots()),
            upload_timezone=(settings.AUTO_STAGE_TIMEZONE or "UTC").strip() or "UTC",
            max_clip_seconds=float(settings.MAX_CLIP_SECONDS),
            cta_enabled=False,
            cta_style="outro_card",
            cta_seconds=3.5,
            cta_headline="SUBSCRIBE & TAP THE BELL",
            cta_subtitle="Click the bell for more clips",
            cta_speech_text="Subscribe to the channel and tap the bell for more clips.",
            cta_voice="en-US-ChristopherNeural",
            **cls._branding_seed_values(),
        )
        db.add(profile)
        try:
            db.commit()
        except Exception:
            # A concurrent first read may have won the race; use that row.
            db.rollback()
            profile = (
                db.query(ChannelProfile).filter(ChannelProfile.id == PROFILE_ID).first()
            )
            if not profile:
                raise
            return profile
        db.refresh(profile)
        return profile

    @classmethod
    def to_response(
        cls, db: Session, profile: ChannelProfile | None = None
    ) -> ChannelProfileResponse:
        profile = profile or cls.get_or_create(db)
        prefix = settings.API_PREFIX
        watermark_url = None
        if profile.watermark_path:
            version = (
                profile.updated_at.isoformat()
                if isinstance(profile.updated_at, datetime)
                else str(profile.updated_at or "")
            )
            watermark_url = f"{prefix}/channel/watermark?v={version}"

        preset = get_presentation_preset(profile.presentation_preset)
        quality = (
            profile.default_quality_preset or preset.default_quality_preset
        ).strip()
        if quality not in QUALITY_PRESETS:
            quality = "high"

        branding = cls.branding_config(db)
        cta = cls.cta_config(db)

        return ChannelProfileResponse(
            channel_name=profile.channel_name,
            presentation_preset=preset.name,
            watermark_enabled=bool(profile.watermark_enabled)
            if profile.watermark_enabled is not None
            else preset.watermark_enabled,
            has_watermark=bool(profile.watermark_path),
            watermark_url=watermark_url,
            watermark_position=profile.watermark_position or preset.watermark_position,
            watermark_opacity=(
                float(profile.watermark_opacity)
                if profile.watermark_opacity is not None
                else preset.watermark_opacity
            ),
            watermark_scale=(
                float(profile.watermark_scale)
                if profile.watermark_scale is not None
                else preset.watermark_scale
            ),
            watermark_margin=(
                float(profile.watermark_margin)
                if profile.watermark_margin is not None
                else preset.watermark_margin
            ),
            watermark_start_seconds=profile.watermark_start_seconds,
            watermark_end_seconds=profile.watermark_end_seconds,
            hook_enabled=(
                bool(profile.hook_enabled)
                if profile.hook_enabled is not None
                else preset.hook_enabled
            ),
            hook_text=profile.hook_text,
            hook_start_seconds=(
                float(profile.hook_start_seconds)
                if profile.hook_start_seconds is not None
                else 0.0
            ),
            hook_duration_seconds=(
                float(profile.hook_duration_seconds)
                if profile.hook_duration_seconds is not None
                else preset.hook_duration_seconds
            ),
            hook_position=profile.hook_position or preset.hook_position,
            kill_effects_enabled=(
                bool(profile.kill_effects_enabled)
                if profile.kill_effects_enabled is not None
                else preset.kill_effects_enabled
            ),
            tracking_enabled=(
                bool(profile.tracking_enabled)
                if profile.tracking_enabled is not None
                else preset.tracking_enabled
            ),
            bg_music_path=profile.bg_music_path,
            bg_music_volume=(
                float(profile.bg_music_volume)
                if profile.bg_music_volume is not None
                else preset.bg_music_volume
            ),
            loop_optimization=(
                bool(profile.loop_optimization)
                if profile.loop_optimization is not None
                else preset.loop_optimization
            ),
            target_fps=profile.target_fps,
            default_framing_preset=profile.default_framing_preset
            or preset.default_framing_preset,
            default_quality_preset=quality,
            branding_enabled=branding.enabled,
            branding_intro=branding.intro,
            branding_outro=branding.outro,
            branding_intro_seconds=branding.intro_seconds,
            branding_outro_seconds=branding.outro_seconds,
            branding_intro_title=branding.intro_title or None,
            branding_intro_subtitle=branding.intro_subtitle or None,
            branding_outro_title=branding.outro_title,
            branding_outro_subtitle=branding.outro_subtitle or None,
            branding_background_color=branding.background_color,
            branding_accent_color=branding.accent_color,
            branding_text_color=branding.text_color,
            branding_font_path=branding.font_path,
            max_clip_seconds=cls.duration_budget(db).max_seconds,
            cta_enabled=cta.enabled,
            cta_style=cta.style,
            cta_seconds=cta.seconds,
            cta_position=cta.position,
            cta_headline=profile.cta_headline or "SUBSCRIBE & TAP THE BELL",
            cta_subtitle=profile.cta_subtitle or "Click the bell for more clips",
            cta_speech_text=profile.cta_speech_text
            or "Subscribe to the channel and tap the bell for more clips.",
            cta_voice=profile.cta_voice or "en-US-ChristopherNeural",
            title_template=profile.title_template,
            pinned_hashtags=normalize_hashtags(_json_list(profile.pinned_hashtags)),
            default_privacy=profile.default_privacy or "public",
            upload_slots=cls.upload_slots(profile),
            upload_timezone=profile.upload_timezone
            or settings.AUTO_STAGE_TIMEZONE
            or "UTC",
            updated_at=profile.updated_at.isoformat()
            if isinstance(profile.updated_at, datetime)
            else None,
        )

    @classmethod
    def update(
        cls, db: Session, payload: ChannelProfileUpdate
    ) -> ChannelProfileResponse:
        profile = cls.get_or_create(db)
        data = payload.model_dump(exclude_unset=True)

        for field, value in data.items():
            if field == "pinned_hashtags":
                profile.pinned_hashtags = json.dumps(normalize_hashtags(value or []))
            elif field == "upload_slots":
                profile.upload_slots = json.dumps(value or [])
            elif field in TEXT_FIELDS:
                cleaned = (value or "").strip() if value is not None else None
                setattr(profile, field, cleaned or None)
            else:
                setattr(profile, field, value)

        profile.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(profile)
        return cls.to_response(db, profile)

    @classmethod
    def upload_slots(cls, profile: ChannelProfile) -> list[str]:
        slots = _json_list(profile.upload_slots)
        return slots or _default_slots()

    @classmethod
    def pinned_hashtags(cls, profile: ChannelProfile) -> list[str]:
        return normalize_hashtags(_json_list(profile.pinned_hashtags))

    @classmethod
    def schedule_config(cls, db: Session) -> tuple[list[str], str]:
        """Return effective daily slots and timezone for publish scheduling."""
        profile = cls.get_or_create(db)
        slots = _json_list(profile.upload_slots) or _default_slots()
        timezone = (
            profile.upload_timezone or settings.AUTO_STAGE_TIMEZONE or "UTC"
        ).strip() or "UTC"
        return slots, timezone

    @staticmethod
    def _branding_seed_values() -> dict[str, object]:
        """Column values seeded from the ``BRANDING_*`` env/settings defaults."""
        env = default_branding_config()
        return {
            "branding_enabled": env.enabled,
            "branding_intro": env.intro,
            "branding_outro": env.outro,
            "branding_intro_seconds": env.intro_seconds,
            "branding_outro_seconds": env.outro_seconds,
            "branding_intro_title": env.intro_title or None,
            "branding_intro_subtitle": env.intro_subtitle or None,
            "branding_outro_title": env.outro_title or None,
            "branding_outro_subtitle": env.outro_subtitle or None,
            "branding_background_color": env.background_color,
            "branding_accent_color": env.accent_color,
            "branding_text_color": env.text_color,
            "branding_font_path": env.font_path or None,
        }

    @classmethod
    def branding_config(cls, db: Session) -> BrandingConfig:
        """Resolve the profile's branded intro/outro settings for a render.

        Columns are ``None`` on rows created before branding moved into the
        profile, so unset columns fall back to the active presentation preset
        and ``BRANDING_*`` settings instead of forcing the creator to re-enter them.
        """
        profile = cls.get_or_create(db)
        env = default_branding_config()

        def pick(attr: str, fallback: object) -> object:
            value = getattr(profile, f"branding_{attr}", None)
            return fallback if value is None else value

        enabled_val = (
            profile.branding_enabled
            if profile.branding_enabled is not None
            else env.enabled
        )

        return BrandingConfig(
            enabled=bool(enabled_val),
            intro=bool(pick("intro", env.intro)),
            outro=bool(pick("outro", env.outro)),
            intro_seconds=float(pick("intro_seconds", env.intro_seconds)),
            outro_seconds=float(pick("outro_seconds", env.outro_seconds)),
            intro_title=str(pick("intro_title", env.intro_title) or ""),
            intro_subtitle=str(pick("intro_subtitle", env.intro_subtitle) or ""),
            outro_title=str(pick("outro_title", env.outro_title) or ""),
            outro_subtitle=str(pick("outro_subtitle", env.outro_subtitle) or ""),
            channel_name=(profile.channel_name or "").strip() or env.channel_name,
            background_color=str(pick("background_color", env.background_color)),
            accent_color=str(pick("accent_color", env.accent_color)),
            text_color=str(pick("text_color", env.text_color)),
            font_path=pick("font_path", env.font_path) or None,
        )

    @classmethod
    def duration_budget(cls, db: Session) -> DurationBudget:
        """Resolve how long a clip may be once branded bookends are added.

        ``max_clip_seconds`` is nullable so profiles created before the ceiling
        existed fall back to ``MAX_CLIP_SECONDS`` (90s by default).
        """
        profile = cls.get_or_create(db)
        branding = cls.branding_config(db)
        bookends = (branding.intro_seconds if branding.has_intro else 0.0) + (
            branding.outro_seconds if branding.has_outro else 0.0
        )
        ceiling = profile.max_clip_seconds
        if ceiling is None:
            ceiling = settings.MAX_CLIP_SECONDS
        return DurationBudget(
            max_seconds=round(float(ceiling), 2),
            bookend_seconds=round(float(bookends), 2),
        )

    @classmethod
    def cta_config(cls, db: Session) -> CtaConfig:
        """Resolve the profile's CTA (voiceover / overlay) settings."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        enabled_val = (
            profile.cta_enabled
            if profile.cta_enabled is not None
            else preset.cta_enabled
        )
        style_val = profile.cta_style or preset.cta_style
        seconds_val = (
            profile.cta_seconds
            if profile.cta_seconds is not None
            else preset.cta_seconds
        )
        position_val = getattr(profile, "cta_position", None) or "bottom"
        return CtaConfig(
            enabled=bool(enabled_val),
            style=_cta_style(style_val),
            seconds=float(seconds_val),
            position="upper_third" if position_val == "upper_third" else "bottom",
            headline=profile.cta_headline or "SUBSCRIBE & TAP THE BELL",
            subtitle=profile.cta_subtitle or "Click the bell for more clips",
            speech_text=profile.cta_speech_text
            or "Subscribe to the channel and tap the bell for more clips.",
            voice=profile.cta_voice or "en-US-ChristopherNeural",
        )

    @classmethod
    def watermark_config(cls, db: Session) -> WatermarkConfig:
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        path = profile.watermark_path
        enabled_val = (
            profile.watermark_enabled
            if profile.watermark_enabled is not None
            else preset.watermark_enabled
        )
        channel_name = profile.channel_name or settings.branding_channel_name
        enabled = bool(enabled_val and (path or channel_name))
        if path and not Path(path).exists():
            logger.warning("Channel watermark is enabled but missing on disk: %s", path)
            path = None
        return WatermarkConfig(
            enabled=enabled,
            path=path if (path and Path(path).exists()) else None,
            position=profile.watermark_position or preset.watermark_position,
            opacity=(
                float(profile.watermark_opacity)
                if profile.watermark_opacity is not None
                else preset.watermark_opacity
            ),
            scale=(
                float(profile.watermark_scale)
                if profile.watermark_scale is not None
                else preset.watermark_scale
            ),
            margin=(
                float(profile.watermark_margin)
                if profile.watermark_margin is not None
                else preset.watermark_margin
            ),
            start_seconds=(
                float(profile.watermark_start_seconds)
                if profile.watermark_start_seconds is not None
                else 0.0
            ),
            end_seconds=(
                float(profile.watermark_end_seconds)
                if profile.watermark_end_seconds is not None
                else None
            ),
            channel_name=channel_name,
        )

    @classmethod
    def hook_config(cls, db: Session) -> HookConfig:
        """Resolve the profile's in-video hook caption overlay settings."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        enabled_val = (
            profile.hook_enabled
            if profile.hook_enabled is not None
            else preset.hook_enabled
        )
        return HookConfig(
            enabled=bool(enabled_val),
            text=profile.hook_text,
            start_seconds=(
                float(profile.hook_start_seconds)
                if profile.hook_start_seconds is not None
                else 0.0
            ),
            duration_seconds=(
                float(profile.hook_duration_seconds)
                if profile.hook_duration_seconds is not None
                else preset.hook_duration_seconds
            ),
            position=profile.hook_position or preset.hook_position,
        )

    @classmethod
    def kill_effects_config(
        cls, db: Session, events: list[dict[str, Any]] | None = None
    ) -> KillEffectsConfig:
        """Resolve event-aware payoff and kill effects settings."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        enabled_val = (
            profile.kill_effects_enabled
            if profile.kill_effects_enabled is not None
            else preset.kill_effects_enabled
        )
        return KillEffectsConfig(
            enabled=bool(enabled_val),
            events=events or [],
        )

    @classmethod
    def tracking_config(cls, db: Session) -> TrackingConfig:
        """Resolve dynamic vertical reframing tracking settings."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        enabled_val = (
            profile.tracking_enabled
            if profile.tracking_enabled is not None
            else preset.tracking_enabled
        )
        return TrackingConfig(
            enabled=bool(enabled_val),
        )

    @classmethod
    def music_config(cls, db: Session) -> MusicConfig:
        """Resolve background music configuration."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        has_music = bool(profile.bg_music_path and Path(profile.bg_music_path).exists())
        volume_val = (
            float(profile.bg_music_volume)
            if profile.bg_music_volume is not None
            else preset.bg_music_volume
        )
        return MusicConfig(
            enabled=has_music,
            path=profile.bg_music_path,
            volume=volume_val,
        )

    @classmethod
    def loop_config(cls, db: Session) -> LoopConfig:
        """Resolve seamless loop optimization configuration."""
        profile = cls.get_or_create(db)
        preset = get_presentation_preset(profile.presentation_preset)
        loop_val = (
            bool(profile.loop_optimization)
            if profile.loop_optimization is not None
            else preset.loop_optimization
        )
        return LoopConfig(
            enabled=loop_val,
        )

    @classmethod
    def target_fps(cls, db: Session) -> int | None:
        """Resolve target frame rate setting."""
        profile = cls.get_or_create(db)
        return profile.target_fps

    @classmethod
    def list_presets(cls) -> list[PresentationPresetResponse]:
        """List all deterministic presentation presets and their specifications."""
        result: list[PresentationPresetResponse] = []
        for preset in PRESENTATION_PRESETS.values():
            result.append(
                PresentationPresetResponse(
                    name=preset.name,
                    label=preset.label,
                    description=preset.description,
                    branding_enabled=preset.branding_enabled,
                    branding_intro=preset.branding_intro,
                    branding_outro=preset.branding_outro,
                    watermark_enabled=preset.watermark_enabled,
                    watermark_position=preset.watermark_position,
                    watermark_opacity=preset.watermark_opacity,
                    watermark_scale=preset.watermark_scale,
                    watermark_margin=preset.watermark_margin,
                    cta_enabled=preset.cta_enabled,
                    cta_style=_cta_style(preset.cta_style),
                    cta_seconds=preset.cta_seconds,
                    default_framing_preset=preset.default_framing_preset,
                    default_quality_preset=preset.default_quality_preset,
                    hook_enabled=preset.hook_enabled,
                    hook_position=preset.hook_position,
                    hook_duration_seconds=preset.hook_duration_seconds,
                    kill_effects_enabled=preset.kill_effects_enabled,
                    tracking_enabled=preset.tracking_enabled,
                    bg_music_volume=preset.bg_music_volume,
                    loop_optimization=preset.loop_optimization,
                )
            )
        return result

    @classmethod
    def save_watermark(
        cls, db: Session, data: bytes, filename: str
    ) -> tuple[ChannelProfileResponse, str]:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in WATERMARK_EXTENSIONS:
            raise ValueError("Unsupported watermark format. Use PNG, JPG, or WEBP.")
        if not data:
            raise ValueError("Watermark file is empty.")
        if len(data) > MAX_WATERMARK_BYTES:
            raise ValueError("Watermark file is too large (max 15 MB).")
        if not cls._looks_like_image(data):
            raise ValueError("Uploaded watermark does not look like an image.")

        assets_dir = settings.channel_assets_path
        assets_dir.mkdir(parents=True, exist_ok=True)
        target = assets_dir / f"watermark{suffix}"

        profile = cls.get_or_create(db)
        old_path = Path(profile.watermark_path) if profile.watermark_path else None
        if old_path and old_path != target and old_path.exists():
            try:
                old_path.unlink()
            except OSError as exc:
                logger.warning("Could not remove old watermark %s: %s", old_path, exc)

        target.write_bytes(data)
        profile.watermark_path = str(target)
        profile.watermark_enabled = True
        profile.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(profile)
        return cls.to_response(db, profile), target.name

    @classmethod
    def delete_watermark(cls, db: Session) -> ChannelProfileResponse:
        profile = cls.get_or_create(db)
        if profile.watermark_path:
            path = Path(profile.watermark_path)
            try:
                if path.is_relative_to(settings.channel_assets_path) and path.exists():
                    path.unlink()
            except OSError as exc:
                logger.warning("Could not remove watermark %s: %s", path, exc)
        profile.watermark_path = None
        profile.watermark_enabled = False
        profile.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(profile)
        return cls.to_response(db, profile)

    @classmethod
    def watermark_file(cls, db: Session) -> Path | None:
        profile = cls.get_or_create(db)
        if not profile.watermark_path:
            return None
        path = Path(profile.watermark_path)
        if not path.exists():
            return None
        return path

    @staticmethod
    def _looks_like_image(data: bytes) -> bool:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return True
        if data.startswith(b"\xff\xd8\xff"):
            return True
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return True
        return False
