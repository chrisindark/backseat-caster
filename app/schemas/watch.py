"""Pydantic schemas for the zero-click watch folder and auto-mine pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WatchIngestItem(BaseModel):
    """One file observed by the watch folder scan."""

    source_name: str
    status: str = Field(
        description="'ingested', 'already_ingested', 'would_ingest', or 'failed'"
    )
    video_id: str | None = None
    title: str | None = None
    error: str | None = None


class WatchScanResponse(BaseModel):
    """Outcome of a single watch folder scan pass."""

    enabled: bool
    watch_dir: str | None = None
    discovered: int = 0
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    items: list[WatchIngestItem] = Field(default_factory=list)
    message: str = ""


class WatchStatusResponse(BaseModel):
    """Configuration and recent history for the watch folder."""

    enabled: bool
    watch_dir: str | None = None
    exists: bool = False
    pending_files: int = 0
    poll_interval_minutes: int = 0
    delete_after_ingest: bool = False
    stability_seconds: int = 10
    supported_extensions: list[str] = Field(default_factory=list)
    recent_ingests: list[dict[str, Any]] = Field(default_factory=list)
