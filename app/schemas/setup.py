"""Pydantic schemas for first-run setup wizard, in-app settings, and demo seeding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SetupCheckItem(BaseModel):
    """Diagnostic check item evaluated in the setup wizard."""

    name: str = Field(
        description="Check identifier (e.g. ffmpeg, disk_space, ai_key, youtube)"
    )
    title: str = Field(description="Human-readable title")
    status: str = Field(description="'ok', 'warning', or 'error'")
    required: bool = Field(
        description="Whether this check is required for core functionality"
    )
    message: str = Field(description="Status description message")
    remedy: str | None = Field(
        None, description="Actionable remedy instructions if warning or error"
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Diagnostic metadata"
    )


class SetupStatusResponse(BaseModel):
    """Aggregate setup status evaluated across the 4 checks."""

    ready: bool = Field(
        description="True if all required checks (FFmpeg, Disk Space) pass"
    )
    checks: list[SetupCheckItem] = Field(default_factory=list)
    ai_status: dict[str, Any] = Field(default_factory=dict)
    youtube_status: dict[str, Any] = Field(default_factory=dict)
    sample_project: dict[str, Any] = Field(default_factory=dict)


class SetupSettingsResponse(BaseModel):
    """Current in-app settings configurable via the setup UI."""

    llm_enabled: bool = False
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_has_api_key: bool = False
    default_clipping_mode: str = "third_person"
    auto_stage_top_n: int = 3
    auto_stage_min_score: float = 0.6
    auto_cleanup_uploaded_renders: bool = True
    auto_cleanup_vod: bool = False
    youtube_redirect_uri: str = "http://localhost:3001/api/v1/youtube/auth/callback"


class UpdateSetupSettingsRequest(BaseModel):
    """Request payload to update runtime settings without modifying .env."""

    llm_enabled: bool | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    default_clipping_mode: str | None = None
    auto_stage_top_n: int | None = None
    auto_stage_min_score: float | None = None
    auto_cleanup_uploaded_renders: bool | None = None
    auto_cleanup_vod: bool | None = None
    youtube_redirect_uri: str | None = None


class DemoProjectRequest(BaseModel):
    """Options for generating and staging the instant 60-second demo highlight."""

    auto_render: bool = Field(
        True, description="Whether to immediately render the 3 highlight Shorts"
    )
    sync: bool = Field(
        True,
        description="Whether to render synchronously (completes before response)",
    )


class DemoProjectResponse(BaseModel):
    """Result of seeding the demo project and rendering candidate Shorts."""

    success: bool
    message: str
    video_id: str
    video_title: str
    candidates_count: int
    staged_jobs_count: int
    rendered_jobs_count: int
    clip_ids: list[str] = Field(default_factory=list)
