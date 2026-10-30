"""Channel profile persistence and brand-default resolution."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.channel_profile import ChannelProfile
from app.rendering.config import CROP_PADDING_PRESETS, QUALITY_PRESETS, WatermarkConfig
from app.schemas.channel import (
    ChannelProfileResponse,
    ChannelProfileUpdate,
    normalize_hashtags,
)

logger = logging.getLogger(__name__)

PROFILE_ID = 1
WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_WATERMARK_BYTES = 15 * 1024 * 1024


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

        quality = (profile.default_quality_preset or "high").strip()
        if quality not in QUALITY_PRESETS:
            quality = "high"

        return ChannelProfileResponse(
            channel_name=profile.channel_name,
            watermark_enabled=bool(profile.watermark_enabled),
            has_watermark=bool(profile.watermark_path),
            watermark_url=watermark_url,
            watermark_position=profile.watermark_position or "bottom_right",
            watermark_opacity=(
                float(profile.watermark_opacity)
                if profile.watermark_opacity is not None
                else 0.85
            ),
            watermark_scale=(
                float(profile.watermark_scale)
                if profile.watermark_scale is not None
                else 0.14
            ),
            watermark_margin=(
                float(profile.watermark_margin)
                if profile.watermark_margin is not None
                else 0.03
            ),
            default_framing_preset=profile.default_framing_preset or "third_person",
            default_quality_preset=quality,
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
            elif field in ("title_template", "channel_name"):
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

    @classmethod
    def watermark_config(cls, db: Session) -> WatermarkConfig:
        profile = cls.get_or_create(db)
        path = profile.watermark_path
        enabled = bool(profile.watermark_enabled and path)
        if enabled and not Path(path).exists():
            logger.warning("Channel watermark is enabled but missing on disk: %s", path)
            enabled = False
        return WatermarkConfig(
            enabled=enabled,
            path=path if enabled else None,
            position=profile.watermark_position or "bottom_right",
            opacity=(
                float(profile.watermark_opacity)
                if profile.watermark_opacity is not None
                else 0.85
            ),
            scale=(
                float(profile.watermark_scale)
                if profile.watermark_scale is not None
                else 0.14
            ),
            margin=(
                float(profile.watermark_margin)
                if profile.watermark_margin is not None
                else 0.03
            ),
        )

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
