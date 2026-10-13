"""Schemas package."""

from app.core.responses import BaseResponse
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadRequest,
    DownloadTaskResponse,
    SyncChannelRequest,
    SyncChannelResponse,
    VideoBase,
    VideoCreateRequest,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoUpdateRequest,
)

__all__ = [
    "BaseResponse",
    "DeleteVideoResponse",
    "DownloadRequest",
    "DownloadTaskResponse",
    "SyncChannelRequest",
    "SyncChannelResponse",
    "VideoBase",
    "VideoCreateRequest",
    "VideoListResponse",
    "VideoResponse",
    "VideoStatusResponse",
    "VideoUpdateRequest",
]
