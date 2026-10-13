"""Abstract base class for highlight candidate detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.services.highlight.cluster_engine import HighlightCandidate


@dataclass
class DetectionMetrics:
    """Latency timings and yield counts across pipeline stages."""

    audio_scan_duration_seconds: float = 0.0
    roi_extract_duration_seconds: float = 0.0
    visual_match_duration_seconds: float = 0.0
    cluster_duration_seconds: float = 0.0
    video_duration_seconds: float = 0.0
    audio_windows_count: int = 0
    frames_analyzed_count: int = 0
    visual_events_count: int = 0


class BaseHighlightDetector(ABC):
    """Base interface for game-specific and generic highlight detection strategies."""

    game_id: str = "generic"
    game_display_name: str = "Generic"

    @abstractmethod
    def detect(
        self,
        video_id: str,
        media_path: Path,
        min_score: float = 0.5,
        progress_callback: Callable[[float, str], None] | None = None,
        metrics: DetectionMetrics | None = None,
    ) -> list[HighlightCandidate]:
        """
        Execute highlight candidate detection for a media file.

        Args:
            video_id: Unique identifier for the source video.
            media_path: Local filesystem path to the video file.
            min_score: Minimum candidate quality score to retain (0.0 - 1.0).
            progress_callback: Optional callback reporting (progress_percent, stage_description).
            metrics: Optional DetectionMetrics instance to record stage latencies and metrics into.

        Returns:
            List of detected HighlightCandidate instances ranked by score.
        """
        pass
