"""Pydantic schemas for YouTube OAuth authentication and programmatic video/shorts uploads."""

from datetime import datetime

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
    publish_at: datetime | None = Field(
        None,
        description="Native YouTube publishAt timestamp. Future timestamps upload the video as private and let YouTube release it.",
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
    scheduled_publish_at: str | None = None
    error_message: str | None = None
    uploaded_at: str | None = None


class YouTubeBatchUploadResponse(BaseModel):
    total_requested: int
    total_succeeded: int
    total_failed: int
    results: list[YouTubeUploadResult]
    message: str


class YouTubeQuotaResponse(BaseModel):
    """Daily YouTube Data API quota consumption and remaining upload capacity."""

    quota_day: str
    daily_limit_units: int
    units_used: int
    units_remaining: int
    upload_quota_cost: int
    max_uploads_per_day: int
    uploads_today: int
    uploads_remaining: int
    can_upload: bool
    resets_at: str


class YouTubeScheduleRequest(BaseModel):
    """Set or clear the native YouTube publishAt timestamp for a staged clip."""

    publish_at: datetime | None = Field(
        None,
        description="Future timestamp for YouTube to release the clip, or null to clear scheduling.",
    )


class AutoStageRequest(BaseModel):
    """Trigger automatic rendering, metadata generation and scheduling for a video."""

    video_id: str
    top_n: int | None = Field(
        None, ge=1, le=20, description="How many top-scoring candidates to stage"
    )
    min_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum candidate score to stage"
    )
    clipping_mode: str | None = Field(
        None,
        description="Vertical render mode: 'third_person', 'direct_crop', 'cinematic', or 'vertical_blur'",
    )
    schedule: bool = Field(
        True, description="Assign staggered native publishAt slots to staged clips"
    )


class AutoStagedClipResponse(BaseModel):
    """A clip that the autonomous pipeline rendered and staged for publishing."""

    clip_id: str
    candidate_id: str
    video_id: str
    score: float
    title: str
    is_selected_for_upload: bool
    scheduled_publish_at: str | None = None
    metadata_source: str = "fallback"


class AutoStageResponse(BaseModel):
    """Result of an auto-stage run."""

    video_id: str
    staged_count: int
    clips: list[AutoStagedClipResponse] = Field(default_factory=list)
    message: str


class StagedClipsResponse(BaseModel):
    """Clips awaiting creator review or scheduled release."""

    items: list[dict] = Field(default_factory=list)
    total: int = 0
    quota: YouTubeQuotaResponse | None = None
