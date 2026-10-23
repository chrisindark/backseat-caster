"""Ultimate charge tracking, cast detection and multi-kill correlation.

The bottom-center ``ultimate_meter`` ROI is sampled together with the other HUD
regions. This module reads it three ways:

1. **Numeric OCR** — ``42%`` / ``100%`` text (primary signal).
2. **Circular gauge fill** — samples a ring of pixels and measures the charged
   fraction, for skins/HUD scales where the number is unreadable.
3. **Ready flash** — explicit ``READY`` text or a (near) fully charged ring.

Readings collapse into *cast* events when the meter drops sharply from a
charged state, which can then be correlated with killfeed eliminations to prove
the ultimate actually converted into a multi-kill.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import BaseModel, Field

from app.services.highlight.ocr import OCRReader, OCRToken
from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)

logger = logging.getLogger(__name__)

PERCENT_PATTERN: re.Pattern[str] = re.compile(r"(\d{1,3})\s*%?")
READY_PATTERN: re.Pattern[str] = re.compile(
    r"\b(READY|FULL(?:Y)?\s*CHARGED|CHARGED|ULTIMATE\s*READY)\b", re.IGNORECASE
)


class UltimateMeterConfig(BaseModel):
    """Configuration for ultimate meter OCR, gauge fallback and cast detection."""

    ready_threshold: float = Field(
        default=95.0, description="Charge percent at or above which the ult is ready"
    )
    cast_trigger_percent: float = Field(
        default=80.0, description="Minimum charge before a drop counts as a cast"
    )
    cast_drop_percent: float = Field(
        default=35.0, description="Required charge drop to register an ultimate cast"
    )
    min_seconds_between_casts: float = Field(
        default=8.0, description="Debounce interval between detected casts"
    )
    correlation_window_seconds: float = Field(
        default=8.0,
        description="How long after a cast kills still count as ultimate payoff",
    )
    gauge_ring_radius: float = Field(
        default=18.0,
        description="Ring sample radius in normalized ROI pixels (0 disables gauge fallback)",
    )
    gauge_ring_samples: int = Field(
        default=48, description="Number of points sampled around the gauge ring"
    )
    min_gauge_fill_ratio: float = Field(
        default=0.03,
        description="Below this charged fraction the gauge is considered absent",
    )
    ready_ring_ratio: float = Field(
        default=0.92, description="Charged ring fraction that implies a ready ultimate"
    )
    charge_pixel_brightness: int = Field(
        default=190,
        description="Per-channel brightness a pixel needs to count as charged",
    )
    charge_pixel_sum: int = Field(
        default=400, description="RGB channel sum a pixel needs to count as charged"
    )
    ocr_min_confidence: float = Field(
        default=0.35, description="Minimum OCR confidence for meter text"
    )


class UltimateReading(BaseModel):
    """Single ultimate meter sample."""

    timestamp: float = Field(..., description="Frame timestamp in seconds")
    charge_percent: float | None = Field(
        default=None, description="Charge percentage (0-100) when measurable"
    )
    ready: bool = Field(default=False, description="True when the meter reads ready")
    method: str = Field(..., description="Signal source: ocr, gauge, or ready_flash")
    confidence: float = Field(default=0.0, description="Reading confidence (0-1)")
    raw_text: str = Field(default="", description="OCR text used for the reading")


class UltimateCast(BaseModel):
    """Detected ultimate ability usage."""

    timestamp: float = Field(..., description="Timestamp the drain was observed")
    charge_before: float | None = Field(
        default=None, description="Last charged percentage before the cast"
    )
    charge_after: float | None = Field(
        default=None, description="Percentage observed after the cast"
    )
    followed_by_multi_kill: bool = Field(
        default=False,
        description="True when 2+ kills landed inside the correlation window",
    )
    kills_within_window: int = Field(
        default=0, description="Eliminations inside the correlation window"
    )
    seconds_to_kill: float | None = Field(
        default=None, description="Seconds from cast to the first correlated kill"
    )


class WindowUltimateTracking(BaseModel):
    """Ultimate meter tracking results for one candidate window."""

    window_start: float = Field(..., description="Window start timestamp")
    window_end: float = Field(..., description="Window end timestamp")
    readings: list[UltimateReading] = Field(
        default_factory=list, description="Chronological meter samples"
    )
    casts: list[UltimateCast] = Field(
        default_factory=list, description="Ultimate casts detected in the window"
    )
    peak_charge: float | None = Field(
        default=None, description="Highest measured charge in the window"
    )
    ready_detected: bool = Field(
        default=False, description="True if the meter was ready at any sample"
    )


class BatchUltimateResult(BaseModel):
    """Ultimate tracking across all analysed candidate windows."""

    file_path: str = Field(..., description="Source media path")
    windows: list[WindowUltimateTracking] = Field(
        default_factory=list, description="Per-window tracking results"
    )
    casts: list[UltimateCast] = Field(
        default_factory=list, description="All casts detected across windows"
    )
    processing_time_seconds: float = Field(
        default=0.0, description="Wall-clock analysis time"
    )


def _effective_charge(reading: UltimateReading) -> float | None:
    """Normalize readiness into a percentage for cast math."""
    if reading.charge_percent is not None:
        return reading.charge_percent
    if reading.ready:
        return 100.0
    return None


def parse_charge_percent(text: str) -> float | None:
    """Extract a 0-100 charge percentage from OCR text."""
    match = PERCENT_PATTERN.search(text)
    if not match:
        return None
    value = float(match.group(1))
    if value < 0.0 or value > 100.0:
        return None
    return value


class UltimateMeterTracker:
    """Reads the ultimate meter and detects casts plus their kill payoff."""

    def __init__(
        self,
        config: UltimateMeterConfig | None = None,
        ocr_reader: OCRReader | None = None,
    ) -> None:
        self.config = config or UltimateMeterConfig()
        self._ocr = ocr_reader or OCRReader(
            min_confidence=self.config.ocr_min_confidence
        )

    # --------------------------------------------------------------- signals
    def estimate_gauge_fill(self, frame: ROIFrame) -> float | None:
        """Estimate charge from the fraction of bright ring/gauge pixels."""
        radius = self.config.gauge_ring_radius
        if radius <= 0 or frame.width <= 2 or frame.height <= 2:
            return None

        center_x = frame.width / 2.0
        center_y = frame.height / 2.0
        radius = min(radius, min(frame.width, frame.height) / 2.0 - 1.0)
        if radius <= 0:
            return None

        array = np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
            (frame.height, frame.width, 3)
        )
        samples = max(8, self.config.gauge_ring_samples)
        charged = 0

        for index in range(samples):
            angle = (2.0 * math.pi * index) / samples
            x = int(round(center_x + radius * math.cos(angle)))
            y = int(round(center_y + radius * math.sin(angle)))
            if not (0 <= x < frame.width and 0 <= y < frame.height):
                continue
            r, g, b = (int(channel) for channel in array[y, x])
            if (
                max(r, g, b) >= self.config.charge_pixel_brightness
                and (r + g + b) >= self.config.charge_pixel_sum
            ):
                charged += 1

        fraction = charged / samples
        if fraction < self.config.min_gauge_fill_ratio:
            return None
        return round(min(1.0, fraction) * 100.0, 1)

    def read_frame(
        self, frame: ROIFrame, tokens: list[OCRToken] | None = None
    ) -> UltimateReading | None:
        """Read a single ultimate meter frame."""
        frame_tokens = tokens if tokens is not None else self._ocr.read(frame)
        raw_text = " ".join(token.text for token in frame_tokens)

        # 1. Numeric OCR (highest fidelity signal).
        for token in frame_tokens:
            percent = parse_charge_percent(token.text)
            if percent is not None:
                return UltimateReading(
                    timestamp=round(frame.timestamp, 3),
                    charge_percent=percent,
                    ready=percent >= self.config.ready_threshold,
                    method="ocr",
                    confidence=round(token.confidence, 3),
                    raw_text=raw_text,
                )

        # 2. Explicit READY flash text.
        for token in frame_tokens:
            if READY_PATTERN.search(token.text):
                return UltimateReading(
                    timestamp=round(frame.timestamp, 3),
                    charge_percent=100.0,
                    ready=True,
                    method="ready_flash",
                    confidence=round(token.confidence, 3),
                    raw_text=raw_text,
                )

        # 3. Circular gauge fill fallback (no readable text).
        gauge_percent = self.estimate_gauge_fill(frame)
        if gauge_percent is not None:
            return UltimateReading(
                timestamp=round(frame.timestamp, 3),
                charge_percent=gauge_percent,
                ready=gauge_percent / 100.0 >= self.config.ready_ring_ratio,
                method="gauge",
                confidence=0.5,
                raw_text=raw_text,
            )

        return None

    # ------------------------------------------------------------- tracking
    def detect_casts(self, readings: Sequence[UltimateReading]) -> list[UltimateCast]:
        """Detect ultimate casts from sharp meter drains."""
        casts: list[UltimateCast] = []
        last_charged: UltimateReading | None = None
        last_cast_timestamp: float | None = None

        for reading in sorted(readings, key=lambda r: r.timestamp):
            charge = _effective_charge(reading)
            if charge is None:
                continue

            if charge >= self.config.cast_trigger_percent:
                last_charged = reading
                continue

            if last_charged is None:
                continue

            charged_value = _effective_charge(last_charged) or 0.0
            if charged_value - charge < self.config.cast_drop_percent:
                continue

            if (
                last_cast_timestamp is not None
                and reading.timestamp - last_cast_timestamp
                < self.config.min_seconds_between_casts
            ):
                continue

            casts.append(
                UltimateCast(
                    timestamp=round(reading.timestamp, 3),
                    charge_before=last_charged.charge_percent,
                    charge_after=reading.charge_percent,
                )
            )
            last_cast_timestamp = reading.timestamp
            last_charged = None

        return casts

    def correlate_with_kills(
        self,
        casts: Sequence[UltimateCast],
        kill_timestamps: Sequence[float],
        window_seconds: float | None = None,
    ) -> list[UltimateCast]:
        """Attach post-cast elimination outcomes to each cast."""
        window = (
            self.config.correlation_window_seconds
            if window_seconds is None
            else window_seconds
        )
        correlated: list[UltimateCast] = []

        for cast in casts:
            kills = sorted(
                timestamp
                for timestamp in kill_timestamps
                if cast.timestamp <= timestamp <= cast.timestamp + window
            )
            correlated.append(
                cast.model_copy(
                    update={
                        "kills_within_window": len(kills),
                        "followed_by_multi_kill": len(kills) >= 2,
                        "seconds_to_kill": (
                            round(kills[0] - cast.timestamp, 3) if kills else None
                        ),
                    }
                )
            )
        return correlated

    def track_window(
        self, window_rois: WindowROIExtractionResult
    ) -> WindowUltimateTracking | None:
        """Track meter readings and casts across one candidate window."""
        frames = window_rois.frames_by_roi.get("ultimate_meter", [])
        if not frames:
            return None

        readings: list[UltimateReading] = []
        for frame in sorted(frames, key=lambda f: f.timestamp):
            reading = self.read_frame(frame)
            if reading is not None:
                readings.append(reading)

        if not readings:
            return None

        charges = [
            reading.charge_percent
            for reading in readings
            if reading.charge_percent is not None
        ]
        return WindowUltimateTracking(
            window_start=window_rois.window_start,
            window_end=window_rois.window_end,
            readings=readings,
            casts=self.detect_casts(readings),
            peak_charge=max(charges) if charges else None,
            ready_detected=any(reading.ready for reading in readings),
        )

    def evaluate_batch(
        self,
        batch_rois: BatchROIExtractionResult,
        kill_timestamps: Sequence[float] | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> BatchUltimateResult:
        """Track ultimate meters across all extracted candidate windows."""
        start = time.perf_counter()
        windows: list[WindowUltimateTracking] = []
        casts: list[UltimateCast] = []
        total = len(batch_rois.windows_extracted)

        for index, window in enumerate(batch_rois.windows_extracted, 1):
            if progress_callback and total > 0:
                progress_callback(
                    round((index - 1) / total * 100.0, 1),
                    f"Tracking ultimate charge (window {index}/{total})",
                )
            tracking = self.track_window(window)
            if tracking:
                windows.append(tracking)
                casts.extend(tracking.casts)

        if kill_timestamps is not None and casts:
            casts = self.correlate_with_kills(casts, kill_timestamps)
            by_timestamp = {cast.timestamp: cast for cast in casts}
            for tracking in windows:
                tracking.casts = [
                    by_timestamp.get(cast.timestamp, cast) for cast in tracking.casts
                ]

        if progress_callback:
            progress_callback(100.0, "Ultimate charge tracking completed")

        elapsed = round(time.perf_counter() - start, 3)
        logger.info(
            "Ultimate tracking complete for %s: %d readings windows, %d casts in %.2fs.",
            batch_rois.file_path,
            len(windows),
            len(casts),
            elapsed,
        )
        return BatchUltimateResult(
            file_path=batch_rois.file_path,
            windows=windows,
            casts=casts,
            processing_time_seconds=elapsed,
        )


def track_ultimate_batch(
    batch_rois: BatchROIExtractionResult,
    config: UltimateMeterConfig | None = None,
    kill_timestamps: Sequence[float] | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> BatchUltimateResult:
    """Convenience function for batch ultimate meter tracking."""
    tracker = UltimateMeterTracker(config=config)
    return tracker.evaluate_batch(
        batch_rois,
        kill_timestamps=kill_timestamps,
        progress_callback=progress_callback,
    )
