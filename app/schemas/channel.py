"""Pydantic schemas for the channel-wide brand profile."""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

WatermarkPosition = Literal[
    "top_left", "top_right", "bottom_left", "bottom_right", "center"
]
FramingPreset = Literal[
    "third_person", "cinematic", "direct_crop", "vertical_blur", "custom"
]
QualityPreset = Literal["high", "compact", "archive"]
PrivacyStatus = Literal["public", "unlisted", "private"]


def normalize_hashtags(values: list[str] | None) -> list[str]:
    """Strip whitespace and leading '#' while preserving order and de-duping."""
    result: list[str] = []
    for value in values or []:
        token = str(value).strip().lstrip("#").strip()
        if token and token.lower() not in {t.lower() for t in result}:
            result.append(token)
    return result


class ChannelProfileResponse(BaseModel):
    """Current channel branding, render and publishing defaults."""

    channel_name: str | None = None

    watermark_enabled: bool = False
    has_watermark: bool = False
    watermark_url: str | None = None
    watermark_position: WatermarkPosition = "bottom_right"
    watermark_opacity: float = 0.85
    watermark_scale: float = 0.14
    watermark_margin: float = 0.03

    default_framing_preset: FramingPreset = "third_person"
    default_quality_preset: QualityPreset = "high"

    # Branded intro/outro cards (effective values, including env fallbacks)
    branding_enabled: bool = False
    branding_intro: bool = True
    branding_outro: bool = True
    branding_intro_seconds: float = 1.2
    branding_outro_seconds: float = 2.0
    branding_intro_title: str | None = None
    branding_intro_subtitle: str | None = None
    branding_outro_title: str = "SUBSCRIBE"
    branding_outro_subtitle: str | None = None
    branding_background_color: str = "#0B0D13"
    branding_accent_color: str = "#F43F5E"
    branding_text_color: str = "#FFFFFF"
    branding_font_path: str | None = None

    title_template: str | None = None
    pinned_hashtags: list[str] = Field(default_factory=list)
    default_privacy: PrivacyStatus = "public"
    upload_slots: list[str] = Field(default_factory=list)
    upload_timezone: str = "UTC"

    updated_at: str | None = None


class ChannelProfileUpdate(BaseModel):
    """Partial update for any channel default.

    Omitted fields are left untouched; empty strings clear the optional text
    fields and empty lists clear the list fields.
    """

    channel_name: str | None = Field(None, max_length=255)
    watermark_enabled: bool | None = None
    watermark_position: WatermarkPosition | None = None
    watermark_opacity: float | None = Field(None, ge=0.05, le=1.0)
    watermark_scale: float | None = Field(None, ge=0.02, le=0.6)
    watermark_margin: float | None = Field(None, ge=0.0, le=0.2)

    default_framing_preset: FramingPreset | None = None
    default_quality_preset: QualityPreset | None = None

    branding_enabled: bool | None = None
    branding_intro: bool | None = None
    branding_outro: bool | None = None
    branding_intro_seconds: float | None = Field(None, ge=0.2, le=5.0)
    branding_outro_seconds: float | None = Field(None, ge=0.2, le=10.0)
    branding_intro_title: str | None = Field(None, max_length=255)
    branding_intro_subtitle: str | None = Field(None, max_length=255)
    branding_outro_title: str | None = Field(None, max_length=255)
    branding_outro_subtitle: str | None = Field(None, max_length=255)
    branding_background_color: str | None = Field(None, max_length=16)
    branding_accent_color: str | None = Field(None, max_length=16)
    branding_text_color: str | None = Field(None, max_length=16)
    branding_font_path: str | None = Field(None, max_length=1024)

    title_template: str | None = Field(None, max_length=255)
    pinned_hashtags: list[str] | None = None
    default_privacy: PrivacyStatus | None = None
    upload_slots: list[str] | None = None
    upload_timezone: str | None = Field(None, max_length=64)

    @field_validator("pinned_hashtags")
    @classmethod
    def clean_hashtags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_hashtags(value)

    @field_validator("upload_slots")
    @classmethod
    def clean_slots(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        slots: list[str] = []
        for raw in value:
            token = str(raw).strip()
            if not token:
                continue
            parts = token.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid upload slot '{raw}', expected HH:MM")
            try:
                hour, minute = int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid upload slot '{raw}', expected HH:MM"
                ) from exc
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError(f"Invalid upload slot '{raw}', expected HH:MM")
            normalized = f"{hour:02d}:{minute:02d}"
            if normalized not in slots:
                slots.append(normalized)
        return sorted(slots)

    @field_validator("upload_timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip() or "UTC"
        try:
            ZoneInfo(token)
        except Exception as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return token


class WatermarkUploadResponse(BaseModel):
    """Result of uploading the channel watermark/logo."""

    profile: ChannelProfileResponse
    filename: str
    message: str


__all__ = [
    "ChannelProfileResponse",
    "ChannelProfileUpdate",
    "FramingPreset",
    "PrivacyStatus",
    "QualityPreset",
    "WatermarkPosition",
    "WatermarkUploadResponse",
    "normalize_hashtags",
]
