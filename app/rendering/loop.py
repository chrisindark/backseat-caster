"""Loop optimization and boundary continuity analysis (Milestone 5)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LoopAnalysisResult(BaseModel):
    """Result of analyzing clip start and end boundaries for seamless looping."""

    enabled: bool = False
    visual_similarity: float = 0.0  # 0.0 to 1.0 (higher = smoother visual match)
    audio_seam_smoothed: bool = False
    is_seamless_candidate: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "visual_similarity": round(self.visual_similarity, 3),
            "audio_seam_smoothed": self.audio_seam_smoothed,
            "is_seamless_candidate": self.is_seamless_candidate,
        }


def analyze_loop_continuity(
    source_path: Path,
    start_seconds: float,
    duration_seconds: float,
    tolerance_seconds: float = 0.10,
) -> LoopAnalysisResult:
    """Analyze visual match between the beginning and ending frames of the clip."""
    if not Path(source_path).exists() or duration_seconds < 1.0:
        return LoopAnalysisResult(
            enabled=True, visual_similarity=0.0, audio_seam_smoothed=True
        )

    try:
        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            return LoopAnalysisResult(
                enabled=True, visual_similarity=0.0, audio_seam_smoothed=True
            )

        # Sample frame near start
        cap.set(cv2.CAP_PROP_POS_MSEC, (start_seconds + tolerance_seconds) * 1000.0)
        ret1, frame1 = cap.read()

        # Sample frame near end
        end_time = start_seconds + max(0.5, duration_seconds - tolerance_seconds)
        cap.set(cv2.CAP_PROP_POS_MSEC, end_time * 1000.0)
        ret2, frame2 = cap.read()
        cap.release()

        if not ret1 or not ret2 or frame1 is None or frame2 is None:
            return LoopAnalysisResult(
                enabled=True, visual_similarity=0.0, audio_seam_smoothed=True
            )

        gray1 = cv2.cvtColor(cv2.resize(frame1, (160, 90)), cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(cv2.resize(frame2, (160, 90)), cv2.COLOR_BGR2GRAY)

        # Mean absolute difference in pixel luminance [0, 255]
        diff = float(
            np.mean(np.abs(gray1.astype(np.float32) - gray2.astype(np.float32)))
        )
        # Normalized similarity: 0.0 (completely different) to 1.0 (identical)
        sim = max(0.0, min(1.0, 1.0 - (diff / 128.0)))
        candidate = sim >= 0.65

        return LoopAnalysisResult(
            enabled=True,
            visual_similarity=sim,
            audio_seam_smoothed=True,
            is_seamless_candidate=candidate,
        )
    except Exception as exc:
        logger.warning("Loop analysis failed: %s", exc)
        return LoopAnalysisResult(
            enabled=True, visual_similarity=0.0, audio_seam_smoothed=True
        )
