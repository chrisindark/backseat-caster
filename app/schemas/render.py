from pydantic import BaseModel, Field

VALID_RENDER_MODES = {
    "landscape",
    "vertical_blur",
    "third_person",
    "direct_crop",
    "cinematic",
    "custom",
    "vertical_crop",
}


class RenderClipRequest(BaseModel):
    video_id: str
    start_seconds: float = Field(..., ge=0, description="Start time in seconds")
    duration_seconds: float = Field(
        ..., gt=0, le=300, description="Duration in seconds (max 5 mins)"
    )
    narration_path: str | None = Field(
        None, description="Optional path to voiceover audio file"
    )
    encoder: str = Field("auto", description="auto, h264_videotoolbox, or libx264")
    overwrite: bool = True
    clip_id: str | None = None
    crop_preset: str = Field(
        "third_person",
        description="Vertical crop layout preset: 'third_person' (33% blur), 'direct_crop' (0% blur), 'cinematic' (25% blur), or 'custom'",
    )
    crop_blur_padding: float | None = Field(
        None,
        ge=0.0,
        le=0.6,
        description="Custom top/bottom blur padding ratio (0.0 to 0.6). If omitted, uses crop_preset value.",
    )
    modes: list[str] | None = Field(
        None,
        description="List of modes to render: 'landscape', 'vertical_blur', 'third_person', 'direct_crop', 'cinematic', 'custom'. Defaults to ['landscape', 'vertical_blur', crop_preset or 'third_person'].",
    )
    sync: bool = Field(
        False,
        description="If True, wait for render to finish synchronously before returning.",
    )


class RenderClipResponse(BaseModel):
    job_id: str | None = None
    clip_id: str
    status: str
    progress: float = 0.0
    output_dir: str
    landscape_path: str | None = None
    vertical_blur_path: str | None = None
    vertical_crop_path: str | None = None
    manifest_path: str | None = None
    encoder_used: str | None = None
    render_duration_seconds: float | None = None
    error_message: str | None = None
    modes: list[str] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    message: str


class RenderJobResponse(BaseModel):
    job_id: str
    clip_id: str
    video_id: str
    status: str  # pending, rendering, completed, failed
    progress: float = 0.0
    start_seconds: float
    duration_seconds: float
    narration_path: str | None = None
    encoder: str = "auto"
    crop_preset: str = "third_person"
    crop_blur_padding: float | None = None
    output_dir: str | None = None
    landscape_path: str | None = None
    vertical_blur_path: str | None = None
    vertical_crop_path: str | None = None
    manifest_path: str | None = None
    encoder_used: str | None = None
    render_duration_seconds: float | None = None
    error_message: str | None = None
    celery_task_id: str | None = None
    video_title: str | None = None
    video_thumbnail_url: str | None = None
    channel_name: str | None = None
    is_selected_for_upload: bool = False
    selected_format: str | None = None
    upload_metadata: str | None = None
    modes: list[str] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    youtube_video_id: str | None = None
    youtube_upload_status: str | None = "not_uploaded"
    youtube_upload_progress: float | None = 0.0
    youtube_upload_url: str | None = None
    youtube_uploaded_at: str | None = None
    youtube_upload_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    message: str | None = None


class UploadSelectionRequest(BaseModel):
    is_selected: bool
    preferred_format: str | None = Field(
        "vertical_blur",
        description="Preferred format for publishing: 'vertical_blur', 'vertical_crop', or 'landscape'",
    )
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    privacy: str | None = Field(
        "public", description="'private', 'unlisted', or 'public'"
    )


class BulkDeleteRendersRequest(BaseModel):
    clip_ids: list[str] = Field(
        ..., min_length=1, description="List of clip IDs or job IDs to delete"
    )
    sync: bool = Field(
        True,
        description="Whether to perform deletion synchronously or dispatch to background task / Celery",
    )


class BulkDeleteRendersResponse(BaseModel):
    deleted_clip_ids: list[str] = Field(default_factory=list)
    failed_clip_ids: list[str] = Field(default_factory=list)
    not_found_clip_ids: list[str] = Field(default_factory=list)
    deleted_count: int = 0
    total_requested: int = 0
    task_id: str | None = None
    message: str


class RenderJobUpdateRequest(BaseModel):
    status: str | None = Field(
        None,
        description="Job lifecycle status: 'pending', 'rendering', 'completed', or 'failed'",
    )
    progress: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Render progress percentage (0.0 to 100.0)",
    )
    error_message: str | None = Field(None, description="Error details if job failed")
    crop_preset: str | None = Field(
        None,
        description="Vertical crop layout preset: 'third_person', 'direct_crop', 'cinematic', or 'custom'",
    )
    crop_blur_padding: float | None = Field(
        None,
        ge=0.0,
        le=0.6,
        description="Top/bottom blur padding ratio (0.0 to 0.6)",
    )
    is_selected_for_upload: bool | None = Field(
        None, description="Whether clip is staged for YouTube upload"
    )
    selected_format: str | None = Field(
        None,
        description="Selected video format: 'vertical_blur', 'vertical_crop', or 'landscape'",
    )
    upload_metadata: str | None = Field(
        None,
        description="Serialized JSON metadata for upload (title, description, tags, privacy)",
    )
    youtube_video_id: str | None = Field(
        None, description="YouTube Video ID once uploaded"
    )
    youtube_upload_status: str | None = Field(
        None,
        description="YouTube upload status: 'not_uploaded', 'uploading', 'completed', 'failed'",
    )
    youtube_upload_progress: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="YouTube upload progress percentage",
    )
    youtube_upload_url: str | None = Field(
        None, description="YouTube watch URL once uploaded"
    )
    youtube_upload_error: str | None = Field(
        None, description="YouTube upload error message"
    )
