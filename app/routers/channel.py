"""Channel brand profile API: render, publishing and watermark defaults."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.channel import (
    ChannelProfileResponse,
    ChannelProfileUpdate,
    MusicUploadResponse,
    PresentationPresetResponse,
    WatermarkUploadResponse,
)
from app.services.channel_profile import ChannelProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel", tags=["Channel Branding"])


@router.get("/presets", response_model=BaseResponse[list[PresentationPresetResponse]])
def list_presentation_presets():
    """List available presentation presets (viral_kill, cinematic_kill, multi_kill_montage)."""
    try:
        presets = ChannelProfileService.list_presets()
        return BaseResponse.success_response(response=presets)
    except Exception as e:
        logger.exception("Failed to list presentation presets: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list presentation presets: {e!s}",
        )


@router.get("/profile", response_model=BaseResponse[ChannelProfileResponse])
def get_channel_profile(db: Session = Depends(get_db)):
    """Return the channel-wide branding and publishing defaults."""
    try:
        profile = ChannelProfileService.to_response(db)
        return BaseResponse.success_response(response=profile)
    except Exception as e:
        logger.exception("Failed to load channel profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load channel profile: {e!s}",
        )


@router.put("/profile", response_model=BaseResponse[ChannelProfileResponse])
@router.patch("/profile", response_model=BaseResponse[ChannelProfileResponse])
def update_channel_profile(
    request: ChannelProfileUpdate,
    db: Session = Depends(get_db),
):
    """Update any channel default; omitted fields are left unchanged."""
    try:
        profile = ChannelProfileService.update(db, request)
        return BaseResponse.success_response(response=profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update channel profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update channel profile: {e!s}",
        )


@router.post("/watermark", response_model=BaseResponse[WatermarkUploadResponse])
def upload_channel_watermark(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload (or replace) the channel watermark/logo image."""
    try:
        data = file.file.read()
        profile, filename = ChannelProfileService.save_watermark(
            db, data=data, filename=file.filename or "watermark.png"
        )
        return BaseResponse.success_response(
            response=WatermarkUploadResponse(
                profile=profile,
                filename=filename,
                message="Watermark uploaded and enabled for every new render.",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to upload channel watermark: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload watermark: {e!s}",
        )


@router.delete("/watermark", response_model=BaseResponse[ChannelProfileResponse])
def delete_channel_watermark(db: Session = Depends(get_db)):
    """Remove the channel watermark and disable the overlay."""
    try:
        profile = ChannelProfileService.delete_watermark(db)
        return BaseResponse.success_response(response=profile)
    except Exception as e:
        logger.exception("Failed to delete channel watermark: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete watermark: {e!s}",
        )


@router.post("/music", response_model=BaseResponse[MusicUploadResponse])
def upload_channel_music(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload (or replace) the channel background music audio track."""
    try:
        data = file.file.read()
        profile, filename = ChannelProfileService.save_music(
            db, data=data, filename=file.filename or "bg_music.mp3"
        )
        return BaseResponse.success_response(
            response=MusicUploadResponse(
                profile=profile,
                filename=filename,
                message="Background music uploaded and configured for renders.",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to upload channel background music: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload music: {e!s}",
        )


@router.delete("/music", response_model=BaseResponse[ChannelProfileResponse])
def delete_channel_music(db: Session = Depends(get_db)):
    """Remove the uploaded background music track."""
    try:
        profile = ChannelProfileService.delete_music(db)
        return BaseResponse.success_response(response=profile)
    except Exception as e:
        logger.exception("Failed to delete background music: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete background music: {e!s}",
        )


@router.get("/music")
def get_channel_music(db: Session = Depends(get_db)):
    """Stream the uploaded background music track for previews."""
    path = ChannelProfileService.music_file(db)
    if not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No channel background music uploaded.",
        )
    media_type = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }.get(path.suffix.lower(), "audio/mpeg")
    return FileResponse(path=path, media_type=media_type, filename=path.name)


@router.get("/watermark")
def get_channel_watermark(db: Session = Depends(get_db)):
    """Stream the uploaded watermark image for previews."""
    path = ChannelProfileService.watermark_file(db)
    if not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No channel watermark uploaded.",
        )
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path=path, media_type=media_type)


@router.get("/assets/bell-chime")
def get_bell_chime():
    """Stream the bundled bell chime so creators can hear it before enabling CTA."""
    from app.services.tts import _find_bell

    path = _find_bell()
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No bell chime asset found (expected data/bell_chime.wav).",
        )
    return FileResponse(path=path, media_type="audio/wav", filename=path.name)


@router.get("/branding/preview")
def preview_branding_card(
    kind: Literal["intro", "outro", "overlay"] = "intro",
    orientation: Literal["landscape", "vertical"] = "landscape",
    title: str | None = None,
    subtitle: str | None = None,
    background: str | None = None,
    accent: str | None = None,
    text_color: str | None = None,
    db: Session = Depends(get_db),
):
    """Render a sample card/overlay PNG with the current profile branding or live preview parameters."""
    from app.rendering.branding import (
        render_card_png,
        render_cta_overlay_png,
    )

    branding = ChannelProfileService.branding_config(db)
    cta = ChannelProfileService.cta_config(db)

    size = (1080, 1920) if orientation == "vertical" else (1920, 1080)

    bg_color = background or branding.background_color
    accent_color = accent or branding.accent_color
    txt_color = text_color or branding.text_color

    tmp_dir = Path(tempfile.mkdtemp(prefix="brand_preview_"))
    out_path = tmp_dir / f"{kind}_{orientation}.png"

    if kind == "intro":
        card_title = title if title is not None else branding.resolved_intro_title()
        card_subtitle = subtitle if subtitle is not None else branding.intro_subtitle
        render_card_png(
            out_path,
            size=size,
            title=card_title,
            subtitle=card_subtitle,
            background=bg_color,
            accent=accent_color,
            text_color=txt_color,
            font_path=branding.font_path,
            kind="intro",
        )
    elif kind == "outro":
        card_title = (
            title if title is not None else (branding.outro_title or "SUBSCRIBE")
        )
        card_subtitle = (
            subtitle if subtitle is not None else branding.resolved_outro_subtitle()
        )
        render_card_png(
            out_path,
            size=size,
            title=card_title,
            subtitle=card_subtitle,
            background=bg_color,
            accent=accent_color,
            text_color=txt_color,
            font_path=branding.font_path,
            kind="outro",
        )
    else:
        overlay_headline = title if title is not None else cta.headline
        overlay_subtitle = subtitle if subtitle is not None else cta.subtitle
        render_cta_overlay_png(
            out_path,
            size=size,
            headline=overlay_headline,
            subtitle=overlay_subtitle,
            accent=accent_color,
            text_color=txt_color,
            font_path=branding.font_path,
        )

    return FileResponse(
        path=out_path,
        media_type="image/png",
        # The preview is a throwaway file; clean up once it has been streamed.
        background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
    )
