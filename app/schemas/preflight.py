"""Pydantic schemas for startup system preflight checks and health inspection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolStatus(BaseModel):
    """Status report for a single system CLI tool or package."""

    name: str = Field(..., description="Tool name (e.g. ffmpeg, ffprobe, yt-dlp)")
    status: str = Field(..., description="'ok', 'warning', or 'error'")
    installed: bool = Field(..., description="Whether the tool is available")
    version: str | None = Field(default=None, description="Detected version string")
    path: str | None = Field(default=None, description="Executable or module path")
    error: str | None = Field(
        default=None, description="Diagnostic error if missing or failed"
    )
    remedy: str | None = Field(
        default=None, description="Recommended resolution or installation step"
    )


class DiskStatus(BaseModel):
    """Disk space storage probe result for local media assets."""

    path: str = Field(..., description="Probed storage filesystem path")
    status: str = Field(..., description="'ok', 'warning', or 'error'")
    total_gb: float = Field(..., description="Total volume space in gigabytes")
    used_gb: float = Field(..., description="Used volume space in gigabytes")
    free_gb: float = Field(..., description="Free volume space in gigabytes")
    percent_used: float = Field(..., description="Percentage of storage used (0-100)")
    min_required_gb: float = Field(
        ..., description="Minimum recommended free space in gigabytes"
    )
    error: str | None = Field(
        default=None, description="Diagnostic message if space is low"
    )
    remedy: str | None = Field(
        default=None, description="Recommended remediation action"
    )


class PreflightReport(BaseModel):
    """Aggregate system preflight report covering CLI tools, media processors, and disk."""

    ready: bool = Field(
        ..., description="True if all critical media dependencies and storage are ready"
    )
    status: str = Field(..., description="'healthy', 'degraded', or 'unhealthy'")
    checks: dict[str, Any] = Field(
        ..., description="Individual checks keyed by tool or resource name"
    )
    errors: list[str] = Field(
        default_factory=list, description="Critical dependency error messages"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-critical advisory warnings"
    )
