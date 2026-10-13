"""Schemas package."""

from app.core.responses import BaseResponse
from app.schemas.highlight import (
    DeleteHighlightsResponse,
    DetectHighlightsRequest,
    DetectHighlightsResponse,
    HighlightCandidateListResponse,
    HighlightCandidateResponse,
    HighlightDetailsSchema,
    HighlightRunListResponse,
    HighlightRunResponse,
    HighlightStatusResponse,
    TriggerEventSchema,
)
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
    "DeleteHighlightsResponse",
    "DeleteVideoResponse",
    "DetectHighlightsRequest",
    "DetectHighlightsResponse",
    "DownloadRequest",
    "DownloadTaskResponse",
    "HighlightCandidateListResponse",
    "HighlightCandidateResponse",
    "HighlightDetailsSchema",
    "HighlightRunListResponse",
    "HighlightRunResponse",
    "HighlightStatusResponse",
    "SyncChannelRequest",
    "SyncChannelResponse",
    "TriggerEventSchema",
    "VideoBase",
    "VideoCreateRequest",
    "VideoListResponse",
    "VideoResponse",
    "VideoStatusResponse",
    "VideoUpdateRequest",
]
