"""HighlightRun SQLAlchemy model for tracking pipeline latencies and metrics."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class HighlightRun(Base):
    """Tracks execution latencies, pipeline stage metrics, and outputs for a highlight detection run."""

    __tablename__ = "highlight_runs"

    id = Column(String(64), primary_key=True, index=True)  # e.g., hrun_a8f12c
    video_id = Column(
        String(64),
        index=True,
        nullable=False,
    )

    status = Column(
        String(32), default="pending", index=True
    )  # pending, scanning, completed, failed
    game = Column(String(64), default="generic")
    detector_used = Column(String(64), nullable=True)

    # Configuration parameters used for this run
    parameters_json = Column(Text, nullable=True)

    # Stage Latencies (in seconds)
    audio_scan_duration_seconds = Column(Float, nullable=True)
    roi_extract_duration_seconds = Column(Float, nullable=True)
    visual_match_duration_seconds = Column(Float, nullable=True)
    cluster_duration_seconds = Column(Float, nullable=True)
    total_duration_seconds = Column(Float, nullable=True)

    # Volume & Yield Metrics
    video_duration_seconds = Column(Float, nullable=True)
    audio_windows_count = Column(Integer, default=0)
    frames_analyzed_count = Column(Integer, default=0)
    visual_events_count = Column(Integer, default=0)
    candidates_produced_count = Column(Integer, default=0)
    speedup_factor = Column(Float, nullable=True)

    # Celery & error details
    celery_task_id = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    video = relationship(
        "Video",
        primaryjoin="HighlightRun.video_id == Video.id",
        foreign_keys="HighlightRun.video_id",
        back_populates="highlight_runs",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert run record to dictionary matching response schema."""
        params_dict: dict[str, Any] = {}
        if self.parameters_json:
            try:
                params_dict = json.loads(self.parameters_json)
            except Exception:
                params_dict = {}

        return {
            "id": self.id,
            "video_id": self.video_id,
            "status": self.status,
            "game": self.game or "generic",
            "detector_used": self.detector_used,
            "parameters": params_dict,
            "audio_scan_duration_seconds": self.audio_scan_duration_seconds,
            "roi_extract_duration_seconds": self.roi_extract_duration_seconds,
            "visual_match_duration_seconds": self.visual_match_duration_seconds,
            "cluster_duration_seconds": self.cluster_duration_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "video_duration_seconds": self.video_duration_seconds,
            "audio_windows_count": self.audio_windows_count or 0,
            "frames_analyzed_count": self.frames_analyzed_count or 0,
            "visual_events_count": self.visual_events_count or 0,
            "candidates_produced_count": self.candidates_produced_count or 0,
            "speedup_factor": self.speedup_factor,
            "celery_task_id": self.celery_task_id,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
