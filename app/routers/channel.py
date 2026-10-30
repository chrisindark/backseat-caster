"""Channel brand profile API: render, publishing and watermark defaults."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.channel import (
    ChannelProfileResponse,
    ChannelProfileUpdate,
    WatermarkUploadResponse,
)
from app.services.channel_profile import ChannelProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel", tags=["Channel Branding"])


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
