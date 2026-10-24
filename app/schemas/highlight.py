"""Pydantic schemas for Highlight Mining API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriggerEventSchema(BaseModel):
    """Specific moment of action inside a highlight clip."""

    time: float = Field(..., description="Timestamp of the event in seconds")
    label: str = Field(
        ...,
        description="Event label (e.g. Elimination, DOUBLE KO, TEAM WIPE, Peak Excitement)",
    )
    roi_name: str = Field(default="center_ko", description="Region where detected")
    confidence: float = Field(default=1.0, description="Detection confidence")

    model_config = ConfigDict(from_attributes=True, extra="allow")


class HighlightDetailsSchema(BaseModel):
    """Rich structured metadata describing the highlight contents."""

    kill_count: int | None = Field(
        default=None, description="Total kills scored during the highlight clip"
    )
    has_ultimate: bool | None = Field(
        default=None,
        description="True if an ultimate ability cast or shutdown was involved",
    )
    is_team_wipe: bool | None = Field(
        default=None, description="True if the clip resulted in a team wipe"
    )
    game_phase: str | None = Field(
        default="regular", description="Game state: overtime, clutch, or regular"
    )
    streak_count: int | None = Field(
        default=None,
        description="Active kill streak milestone (e.g. 5 for 5-player KO streak)",
    )
    climax_start_seconds: float | None = Field(
        default=None, description="Start timestamp of the core action climax in seconds"
    )
    climax_end_seconds: float | None = Field(
        default=None, description="End timestamp of the core action climax in seconds"
    )
    trigger_events: list[TriggerEventSchema] = Field(
        default_factory=list,
        description="Chronological event timestamps and labels",
    )
    hero_name: str | None = Field(
        default=None,
        description="Identified played hero from HUD portrait template matching",
    )
    multi_kill_chain: int | None = Field(
        default=None,
        description="Rapid killfeed eliminations credited inside the clip",
    )
    abilities_used: list[str] = Field(
        default_factory=list,
        description="Ability names whose cooldown ended inside the clip",
    )
    killfeed_chain: dict[str, Any] | None = Field(
        default=None,
        description="Structured killfeed rows, attribution and multi-kill chain",
    )
    ultimate_casts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ultimate casts with their post-cast kill payoff",
    )

    model_config = ConfigDict(from_attributes=True, extra="allow")


class HighlightCandidateResponse(BaseModel):
    """Single ranked highlight candidate clip."""

    candidate_id: str = Field(..., description="Unique highlight candidate ID")
    video_id: str = Field(..., description="Source video ID")
    start_seconds: float = Field(..., description="Start timestamp in seconds")
    end_seconds: float = Field(..., description="End timestamp in seconds")
    duration_seconds: float = Field(..., description="Duration in seconds")
    score: float = Field(..., description="Quality score between 0.0 and 1.0")
    event_type: str = Field(..., description="Primary event classification")
    game: str = Field(default="generic", description="Game name")
    details: HighlightDetailsSchema = Field(
        default_factory=HighlightDetailsSchema,
        description="Structured highlight details",
    )
    thumbnail_url: str | None = Field(
        None, description="API URL path for thumbnail preview"
    )
    thumbnail_path: str | None = Field(
        None, description="Filesystem path to extracted thumbnail"
    )
    peak_timestamp: float = Field(
        default=0.0, description="Timestamp of peak action climax"
    )
    suggested_title: str = Field(
        default="", description="Catchy Shorts title with emojis"
    )
    suggested_tags: list[str] = Field(
        default_factory=list, description="Recommended YouTube hashtags and tags"
    )
    created_at: str | None = Field(None, description="Creation ISO datetime")
    updated_at: str | None = Field(None, description="Last update ISO datetime")

    model_config = ConfigDict(from_attributes=True, extra="allow")


class HighlightRunResponse(BaseModel):
    """Performance metrics, latencies, and output details of a highlight detection run."""

    id: str = Field(..., description="Unique highlight run ID")
    video_id: str = Field(..., description="Source video ID")
    status: str = Field(
        ..., description="Run status: pending, scanning, completed, failed"
    )
    game: str = Field(default="generic", description="Game identifier used")
    detector_used: str | None = Field(None, description="Detector strategy applied")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Configuration parameters"
    )
    audio_scan_duration_seconds: float | None = Field(
        None, description="Audio scan duration in seconds"
    )
    roi_extract_duration_seconds: float | None = Field(
        None, description="ROI extraction duration in seconds"
    )
    visual_match_duration_seconds: float | None = Field(
        None, description="Visual/OCR matching duration in seconds"
    )
    cluster_duration_seconds: float | None = Field(
        None, description="Clustering and thumbnail duration in seconds"
    )
    total_duration_seconds: float | None = Field(
        None, description="Total pipeline latency in seconds"
    )
    video_duration_seconds: float | None = Field(
        None, description="Source video duration in seconds"
    )
    audio_windows_count: int = Field(
        0, description="Total high-energy action windows found"
    )
    frames_analyzed_count: int = Field(
        0, description="Total visual frames extracted and evaluated"
    )
    visual_events_count: int = Field(
        0, description="Total visual trigger events detected"
    )
    candidates_produced_count: int = Field(
        0, description="Total highlight candidates retained"
    )
    speedup_factor: float | None = Field(
        None,
        description="Processing speed relative to realtime (video_dur / total_dur)",
    )
    celery_task_id: str | None = Field(
        None, description="Celery task ID if executed as worker job"
    )
    error_message: str | None = Field(None, description="Error message if run failed")
    started_at: str | None = Field(None, description="Run start ISO datetime")
    completed_at: str | None = Field(None, description="Run completion ISO datetime")
    created_at: str | None = Field(None, description="Creation ISO datetime")

    model_config = ConfigDict(from_attributes=True)


class HighlightRunListResponse(BaseModel):
    """List of historical detection runs for a video."""

    video_id: str
    count: int
    runs: list[HighlightRunResponse] = Field(default_factory=list)


class HighlightCandidateListResponse(BaseModel):
    """List of highlight candidates for a video."""

    video_id: str
    status: str
    count: int
    candidates: list[HighlightCandidateResponse] = Field(default_factory=list)


class HighlightStatusResponse(BaseModel):
    """Polling status of highlight scan for a video."""

    video_id: str
    status: str = Field(
        ..., description="Scanning status: idle, pending, scanning, completed, failed"
    )
    progress: float = Field(0.0, description="Detection progress percentage (0-100)")
    stage: str = Field("", description="Current pipeline stage description")
    error: str | None = Field(None, description="Error details if scan failed")
    candidate_count: int = Field(default=0, description="Total candidates found so far")
    task_id: str | None = Field(
        None, description="Background/Celery task ID if in flight"
    )
    latest_run: HighlightRunResponse | None = Field(
        None, description="Performance metrics of the most recent detection run"
    )


class DetectHighlightsRequest(BaseModel):
    """Parameters to trigger a highlight scan on a video."""

    game: str | None = Field(
        None,
        description="Target game identifier ('marvel_rivals', 'generic', etc.). Inferred from video if omitted.",
    )
    force_rescan: bool = Field(
        False, description="Re-run pipeline even if already scanned"
    )
    min_score: float = Field(
        0.5, ge=0.0, le=1.0, description="Minimum candidate score to retain"
    )
    auto_render_top_n: int | None = Field(
        None,
        ge=0,
        le=20,
        description="Automatically render and stage the top N candidates after clustering (0 disables).",
    )
    clipping_mode: str | None = Field(
        None,
        description="Vertical render mode used for auto-staged clips: 'third_person', 'direct_crop', 'cinematic', or 'vertical_blur'.",
    )
    sync: bool = Field(
        False,
        description="If True, wait for detection to finish synchronously before returning",
    )


class DetectHighlightsResponse(BaseModel):
    """Response returned when a highlight scan is triggered."""

    video_id: str
    status: str
    message: str
    task_id: str | None = None
    run_id: str | None = None
    auto_staged_count: int = 0


class DeleteHighlightsResponse(BaseModel):
    """Response returned when highlight candidates are cleared."""

    video_id: str
    deleted_count: int
    message: str
