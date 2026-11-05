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
        None,
        description="Privacy status: 'private', 'unlisted', or 'public' (unset defers to staged metadata / public)",
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
    error_code: str | None = None
    retry_at: str | None = None
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
    failed_uploads: int = 0
    can_upload: bool
    blocked_reason: str | None = None
    blocked_until: str | None = None
    upload_budget_units: int = 8000
    analytics_budget_units: int = 2000
    upload_units_used: int = 0
    analytics_units_used: int = 0
    analytics_units_remaining: int = 2000
    upload_units_remaining: int = 8000
    upload_budget_exhausted: bool = False
    analytics_budget_exhausted: bool = False
    can_analytics: bool = True
    analytics_blocked: bool = False
    usage_fraction: float = 0.0
    analytics_threshold: float = 0.8
    analytics_batch_limit: int = 50
    backoff_max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    api_quota_exhausted: bool = False
    upload_limit_exceeded: bool = False
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_error_at: str | None = None
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
    same_day_catchup: bool = Field(
        True,
        description="Schedule all clips on the same day by catching up missed earlier slots at the next available slot",
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
    llm_available: bool = Field(
        False, description="Whether an LLM provider is configured for AI copy"
    )


# Phase 11: Analytics & Slot Optimization Schemas
class SlotPerformanceItem(BaseModel):
    slot: str
    videos_count: int
    avg_views: float
    avg_velocity_3h: float
    avg_velocity_24h: float
    avg_velocity_72h: float = 0.0
    avg_velocity_7d: float = 0.0
    engagement_rate: float
    performance_score: float
    rank: int = 1
    recommended: bool = False


class SlotAnalyticsResponse(BaseModel):
    timezone: str
    total_tracked_videos: int
    slots: list[SlotPerformanceItem] = Field(default_factory=list)
    recommended_slots: list[str] = Field(default_factory=list)
    summary: str


class AnalyticsSyncResponse(BaseModel):
    polled_count: int
    updated_count: int
    snapshots_created: int
    message: str


class VelocitySnapshotItem(BaseModel):
    hours: float
    views: int
    likes: int
    comments: int = 0
    recorded_at: str | None = None


class ClipVelocityTimelineResponse(BaseModel):
    clip_id: str
    job_id: str | None = None
    youtube_video_id: str | None = None
    latest_views: int = 0
    latest_likes: int = 0
    velocity_3h: int = 0
    velocity_24h: int = 0
    velocity_72h: int = 0
    velocity_7d: int = 0
    snapshots: list[VelocitySnapshotItem] = Field(default_factory=list)


class ApplyOptimalSlotsResponse(BaseModel):
    applied_slots: list[str]
    timezone: str
    message: str
