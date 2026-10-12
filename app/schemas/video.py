"""Pydantic schemas for video operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class VideoResponse(VideoBase):
    model_config = ConfigDict(from_attributes=True)

    is_downloaded: bool = False
    local_file_path: str | None = None
    file_size_bytes: int | None = None
    download_status: str = "not_downloaded"
    download_progress: float = 0.0
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
        description="Filter: all, downloaded, not_downloaded, downloading",
    )
    search: str | None = Field(None, description="Search term in title or channel name")


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
