"""Pydantic schemas for video operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoBase(BaseModel):
    id: str
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    duration: int = 0
    duration_formatted: str = "0:00"
    channel_name: str | None = None
    channel_id: str | None = None
    channel_url: str | None = None
    view_count: int = 0
    published_at: str | None = None
    webpage_url: str

    @field_validator("duration", mode="before")
    @classmethod
    def set_duration(cls, v: Any) -> int:
        return 0 if v is None else int(v)

    @field_validator("view_count", mode="before")
    @classmethod
    def set_view_count(cls, v: Any) -> int:
        return 0 if v is None else int(v)


class UploadedHighlightSummary(BaseModel):
    clip_id: str
    youtube_video_id: str | None = None
    youtube_upload_url: str | None = None
    youtube_uploaded_at: datetime | None = None
    title: str | None = None
    format: str | None = None


class VideoResponse(VideoBase):
    model_config = ConfigDict(from_attributes=True)

    is_downloaded: bool = False
    local_file_path: str | None = None
    file_size_bytes: int | None = None
    download_status: str = "not_downloaded"
    download_progress: float = 0.0
    error_message: str | None = None

    # Highlight detection & mining lifecycle
    highlight_status: str | None = "idle"
    highlight_progress: float = 0.0
    highlight_stage: str = ""
    highlight_candidate_count: int = 0

    # Rendering & YouTube upload tracking
    rendered_clip_count: int = 0
    uploaded_clip_count: int = 0
    has_uploaded_highlights: bool = False
    uploaded_highlights: list[UploadedHighlightSummary] = []

    # Disk storage and cleanup indicators
    can_cleanup_vod: bool = False
    can_cleanup_renders: bool = False

    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("highlight_progress", mode="before")
    @classmethod
    def set_highlight_progress(cls, v: Any) -> float:
        return 0.0 if v is None else float(v)

    @field_validator("highlight_stage", mode="before")
    @classmethod
    def set_highlight_stage(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("highlight_status", mode="before")
    @classmethod
    def set_highlight_status(cls, v: Any) -> str:
        return "idle" if v is None else str(v)

    @field_validator("download_status", mode="before")
    @classmethod
    def set_download_status(cls, v: Any) -> str:
        return "not_downloaded" if v is None else str(v)

    @field_validator("download_progress", mode="before")
    @classmethod
    def set_download_progress(cls, v: Any) -> float:
        return 0.0 if v is None else float(v)

    @field_validator("highlight_candidate_count", mode="before")
    @classmethod
    def set_highlight_candidate_count(cls, v: Any) -> int:
        return 0 if v is None else int(v)


class VideoListRequest(BaseModel):
    page: int = Field(
        1,
        ge=1,
        description="Page number",
    )
    limit: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum number of videos to fetch/sync from table",
    )
    channel: str | None = Field(
        None, description="YouTube channel handle or name (e.g., @chrisindark)"
    )
    status_filter: str | None = Field(
        None,
        alias="status",
        description="Filter: all, downloaded, not_downloaded, downloading, highlights_mined, uploaded, cleanup_ready",
    )
    search: str | None = Field(None, description="Search term in title or channel name")


class VideoStorageCleanupRequest(BaseModel):
    clean_vod: bool = Field(
        True,
        description="Whether to delete the raw downloaded source VOD file to reclaim disk space",
    )
    clean_uploaded_renders: bool = Field(
        True,
        description="Whether to delete local render directories for clips already uploaded to YouTube",
    )
    clean_all_renders: bool = Field(
        False,
        description="Whether to delete all local render directories for this video regardless of upload status",
    )


class VideoStorageCleanupResponse(BaseModel):
    video_id: str
    reclaimed_bytes: int = 0
    reclaimed_formatted: str = "0 MB"
    vod_deleted: bool = False
    renders_deleted_count: int = 0
    message: str


class VideoListResponse(BaseModel):
    items: list[VideoResponse]
    total: int
    page: int
    limit: int
    total_pages: int
    channel_title: str | None = None
    channel_url: str | None = None


class YouTubeChannelVideoItem(VideoBase):
    is_in_database: bool = False
    is_downloaded: bool = False
    download_status: str = "not_downloaded"


class YouTubeChannelVideosResponse(BaseModel):
    channel_title: str
    channel_id: str | None = None
    channel_url: str
    limit: int
    offset: int
    total_loaded: int = 0
    has_more: bool = True
    videos: list[YouTubeChannelVideoItem]


class SyncChannelRequest(BaseModel):
    channel_url: str | None = Field(
        None, description="YouTube channel handle, URL, or ID (e.g., @MarvelRivals)"
    )
    limit: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum number of videos to fetch/sync from channel",
    )
    offset: int = Field(
        0,
        ge=0,
        description="Number of videos to skip from the beginning of the channel",
    )
    videos: list[VideoBase] | None = Field(
        None,
        description="Explicit list of selected video items to add to database",
    )


class SyncChannelResponse(BaseModel):
    status: str
    channel_title: str
    channel_url: str
    total_found: int
    new_added: int
    updated: int = 0
    skipped: int = 0
    message: str


class DownloadRequest(BaseModel):
    quality: str | None = Field(
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        description="yt-dlp format selector",
    )


class DownloadTaskResponse(BaseModel):
    video_id: str
    download_status: str
    download_progress: float = 0.0
    local_file_path: str | None = None
    task_id: str | None = None
    message: str


class VideoStatusResponse(BaseModel):
    video_id: str
    is_downloaded: bool
    download_status: str
    download_progress: float = 0.0
    local_file_path: str | None = None
    file_size_bytes: int | None = None
    error_message: str | None = None


class DeleteVideoResponse(BaseModel):
    status: str
    message: str


class VideoCreateRequest(BaseModel):
    id: str | None = Field(
        None,
        description="YouTube Video ID or custom identifier. If omitted, extracted from webpage_url or auto-generated.",
    )
    title: str = Field(..., min_length=1, description="Video title")
    description: str | None = Field(None, description="Video description")
    thumbnail_url: str | None = Field(None, description="Video thumbnail URL")
    duration: int = Field(0, ge=0, description="Duration in seconds")
    duration_formatted: str | None = Field(
        None, description="Formatted duration e.g. '12:34'"
    )
    channel_name: str | None = Field(None, description="Channel or creator name")
    channel_id: str | None = Field(None, description="Channel ID")
    channel_url: str | None = Field(None, description="Channel URL")
    view_count: int = Field(0, ge=0, description="View count")
    published_at: str | None = Field(None, description="Published date string")
    webpage_url: str | None = Field(
        None,
        description="Video page URL. If omitted and id is provided, defaults to YouTube watch URL.",
    )


class VideoUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, description="Updated video title")
    description: str | None = Field(None, description="Updated video description")
    thumbnail_url: str | None = Field(None, description="Updated thumbnail URL")
    duration: int | None = Field(None, ge=0, description="Updated duration in seconds")
    duration_formatted: str | None = Field(
        None, description="Updated formatted duration"
    )
    channel_name: str | None = Field(None, description="Updated channel name")
    channel_id: str | None = Field(None, description="Updated channel ID")
    channel_url: str | None = Field(None, description="Updated channel URL")
    view_count: int | None = Field(None, ge=0, description="Updated view count")
    published_at: str | None = Field(None, description="Updated published date")
    webpage_url: str | None = Field(None, description="Updated webpage URL")
    is_downloaded: bool | None = Field(None, description="Whether downloaded locally")
    local_file_path: str | None = Field(None, description="Local file path")
    file_size_bytes: int | None = Field(None, ge=0, description="File size in bytes")
    download_status: str | None = Field(None, description="Download status")
    download_progress: float | None = Field(
        None, ge=0.0, le=100.0, description="Download progress percentage"
    )
    error_message: str | None = Field(None, description="Download or error message")
