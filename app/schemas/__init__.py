"""Schemas package."""

from app.core.responses import BaseResponse
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadRequest,
    DownloadTaskResponse,
    SyncChannelRequest,
    SyncChannelResponse,
    VideoBase,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
)

__all__ = [
    "BaseResponse",
    "DeleteVideoResponse",
    "DownloadRequest",
    "DownloadTaskResponse",
    "SyncChannelRequest",
    "SyncChannelResponse",
    "VideoBase",
    "VideoListResponse",
    "VideoResponse",
    "VideoStatusResponse",
]
