"""Pydantic schemas for YouTube OAuth authentication and programmatic video/shorts uploads."""

from pydantic import BaseModel, Field


class YouTubeAuthStatusResponse(BaseModel):
    is_authenticated: bool
    channel_title: str | None = None
    channel_id: str | None = None
    channel_handle: str | None = None
    thumbnail_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    client_configured: bool = False
    message: str | None = None


class YouTubeAuthUrlResponse(BaseModel):
    auth_url: str
    redirect_uri: str
    client_id: str | None = None
    state: str | None = None


class YouTubeAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None
    state: str | None = None
    code_verifier: str | None = None


class YouTubeCredentialsRequest(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    client_secrets_json: str | None = None


class YouTubeUploadRequest(BaseModel):
    title: str | None = Field(
        None, max_length=100, description="Video title (max 100 characters)"
    )
    description: str | None = Field(
        None, max_length=5000, description="Video description"
    )
    tags: list[str] | None = Field(None, description="Video tags")
    privacy: str | None = Field(
        None, description="Privacy status: 'private', 'unlisted', or 'public' (unset defers to staged metadata / public)"
    )
    format: str | None = Field(
        None,
        description="Render format: 'vertical_blur', 'vertical_crop', or 'landscape'. Auto-detected if omitted.",
    )
    is_short: bool | None = Field(
        None,
        description="Whether to optimize upload as YouTube Short (appends #Shorts). Defaults to True for vertical formats.",
    )
    category_id: str = Field(
        "20", description="YouTube category ID (default '20' for Gaming)"
    )
    sync: bool = Field(
        False, description="Whether to wait synchronously for upload completion"
    )


class YouTubeUploadResult(BaseModel):
    clip_id: str
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    title: str
    format: str
    is_short: bool
    status: str  # "completed", "uploading", "failed"
    privacy: str
    progress: float = 0.0
    error_message: str | None = None
    uploaded_at: str | None = None


class YouTubeBatchUploadResponse(BaseModel):
    total_requested: int
    total_succeeded: int
    total_failed: int
    results: list[YouTubeUploadResult]
    message: str
