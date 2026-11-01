"""Computer vision player tracking and dynamic vertical crop reframing (Milestone 4).

Tracks player/action focal points across the gameplay window and constructs
smooth, bounded horizontal pan trajectories with fallback to static center crop.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TrackingConfig(BaseModel):
    """Configuration for computer-vision dynamic vertical reframing (Milestone 4)."""

    enabled: bool = Field(
        False, description="Enable CV-based dynamic player tracking crop"
    )
    sample_rate_hz: float = Field(
        2.0, ge=0.5, le=10.0, description="Tracking frame sampling rate in Hz"
    )
    smoothness: float = Field(
        0.25, ge=0.05, le=0.8, description="EMA smoothing factor (lower = smoother)"
    )
    max_pan_speed: float = Field(
        0.15,
        ge=0.02,
        le=0.5,
        description="Max horizontal pan speed per second in normalized width",
    )
    min_confidence: float = Field(
        0.35,
        ge=0.1,
        le=1.0,
        description="Minimum confidence threshold before falling back to static crop",
    )


class TrackingKeyframe(BaseModel):
    """Single tracked focal moment in time."""

    time: float = Field(..., description="Timestamp in seconds relative to clip start")
    normalized_x: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized horizontal focal center (0.5 is center)",
    )


class TrackingResult(BaseModel):
    """Result of analyzing clip footage for player/action reframing."""

    enabled: bool = False
    confidence: float = 0.0
    fallback_used: bool = True
    keyframes: list[TrackingKeyframe] = Field(default_factory=list)
    crop_x_expr: str = "(in_w-out_w)/2"

    def describe(self) -> dict[str, Any]:
        """Serialisable summary recorded in the render manifest."""
        return {
            "enabled": self.enabled,
            "confidence": round(self.confidence, 3),
            "fallback_used": self.fallback_used,
            "keyframe_count": len(self.keyframes),
            "crop_x_expr": self.crop_x_expr,
        }


def build_trajectory_expression(
    keyframes: list[TrackingKeyframe],
) -> str:
    """Build an FFmpeg crop-x expression from linear keyframe interpolation.

    Ensures the crop window smoothly interpolates across time and is strictly
    clamped to valid source bounds: min(max(0, x), in_w - out_w).
    """
    if len(keyframes) < 2:
        return "(in_w-out_w)/2"

    expr = f"({keyframes[-1].normalized_x:.3f}*in_w-out_w/2)"
    for i in range(len(keyframes) - 2, -1, -1):
        k0 = keyframes[i]
        k1 = keyframes[i + 1]
        dt = max(0.01, k1.time - k0.time)
        dx = k1.normalized_x - k0.normalized_x
        seg = f"(({k0.normalized_x:.3f}+{dx:.3f}*(t-{k0.time:.2f})/{dt:.2f})*in_w-out_w/2)"
        expr = f"if(lte(t,{k1.time:.2f}),{seg},{expr})"

    return f"min(max(0,{expr}),in_w-out_w)"


class PlayerTracker:
    """Detects gameplay focal centers and generates smoothed reframing paths."""

    def __init__(self, config: TrackingConfig | None = None) -> None:
        self.config = config or TrackingConfig()

    def track_clip(
        self,
        source_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> TrackingResult:
        """Analyze source video and return tracking keyframes and crop expression.

        Degrades gracefully to static center crop if video cannot be opened,
        is too short, or lacks sufficient detection confidence.
        """
        if not self.config.enabled:
            return TrackingResult(
                enabled=False, fallback_used=True, crop_x_expr="(in_w-out_w)/2"
            )

        if not Path(source_path).exists() or duration_seconds < 0.5:
            logger.info(
                "Tracking falling back to static crop: invalid video or duration too short"
            )
            return TrackingResult(
                enabled=True, fallback_used=True, crop_x_expr="(in_w-out_w)/2"
            )

        try:
            return self._analyze_footage(source_path, start_seconds, duration_seconds)
        except Exception as exc:
            logger.warning(
                "Player tracking failed with error: %s, falling back to static crop",
                exc,
            )
            return TrackingResult(
                enabled=True, fallback_used=True, crop_x_expr="(in_w-out_w)/2"
            )

    def _analyze_footage(
        self,
        source_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> TrackingResult:
        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            return TrackingResult(
                enabled=True, fallback_used=True, crop_x_expr="(in_w-out_w)/2"
            )

        step_seconds = 1.0 / max(0.5, self.config.sample_rate_hz)
        num_samples = max(2, int(duration_seconds / step_seconds) + 1)

        raw_points: list[tuple[float, float, float]] = []  # (t_rel, norm_x, conf)

        for i in range(num_samples):
            t_rel = min(duration_seconds, i * step_seconds)
            t_abs = start_seconds + t_rel
            cap.set(cv2.CAP_PROP_POS_MSEC, t_abs * 1000.0)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Resize to fast thumbnail resolution
            small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
            sh, sw = small.shape[:2]

            # Exclude top 16% (HUD/score) and bottom 16% (abilities/health bar)
            y0, y1 = int(sh * 0.16), int(sh * 0.84)
            # Focus on central action corridor (middle 70% width)
            x0, x1 = int(sw * 0.15), int(sw * 0.85)
            roi = small[y0:y1, x0:x1]

            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # Horizontal Sobel edge response
            grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            col_weights = np.abs(grad_x).sum(axis=0)
            total_energy = float(col_weights.sum())

            if total_energy > 10.0:
                indices = np.arange(len(col_weights))
                centroid_local = float(np.sum(indices * col_weights) / total_energy)
                centroid_global = x0 + centroid_local
                norm_x = centroid_global / float(sw)
                # Keep within safe bounds [0.35, 0.65] to avoid extreme edges
                clamped_x = max(0.35, min(0.65, norm_x))
                conf = 0.80
            else:
                clamped_x = 0.50
                conf = 0.20

            raw_points.append((t_rel, clamped_x, conf))

        cap.release()

        if len(raw_points) < 2:
            return TrackingResult(
                enabled=True, fallback_used=True, crop_x_expr="(in_w-out_w)/2"
            )

        mean_conf = float(np.mean([p[2] for p in raw_points]))
        if mean_conf < self.config.min_confidence:
            logger.info(
                "Tracking confidence %.2f below threshold %.2f; using static fallback",
                mean_conf,
                self.config.min_confidence,
            )
            return TrackingResult(
                enabled=True,
                confidence=mean_conf,
                fallback_used=True,
                crop_x_expr="(in_w-out_w)/2",
            )

        # Apply exponential smoothing and pan velocity clamping
        smoothed_keyframes: list[TrackingKeyframe] = []
        alpha = self.config.smoothness
        curr_x = raw_points[0][1]

        smoothed_keyframes.append(
            TrackingKeyframe(time=raw_points[0][0], normalized_x=round(curr_x, 3))
        )

        for i in range(1, len(raw_points)):
            t_rel, target_x, _ = raw_points[i]
            dt = max(0.01, t_rel - raw_points[i - 1][0])
            max_delta = self.config.max_pan_speed * dt

            # EMA step
            next_x = alpha * target_x + (1.0 - alpha) * curr_x
            delta = next_x - curr_x
            if abs(delta) > max_delta:
                next_x = curr_x + math.copysign(max_delta, delta)

            curr_x = max(0.35, min(0.65, next_x))
            smoothed_keyframes.append(
                TrackingKeyframe(time=round(t_rel, 3), normalized_x=round(curr_x, 3))
            )

        crop_expr = build_trajectory_expression(smoothed_keyframes)

        return TrackingResult(
            enabled=True,
            confidence=round(mean_conf, 3),
            fallback_used=False,
            keyframes=smoothed_keyframes,
            crop_x_expr=crop_expr,
        )
