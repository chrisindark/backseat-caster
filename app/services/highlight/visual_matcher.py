"""Marvel Rivals Visual Event Matcher using HSV color thresholding and RapidOCR.

Detects eliminations, multi-kills (DOUBLE KO, TRIPLE KO, TEAM WIPE), and clutch
match outcomes (VICTORY, OVERTIME) on targeted HUD regions.

Uses high-speed two-phase filtering:
1. HSV Color Gating: Fast (<1ms) check for high-contrast Marvel Rivals Gold (#FFD700)
   and Red elimination accents. Non-event frames are pruned without running OCR.
2. Lightweight OCR & Keyword Matching: Runs RapidOCR on color-positive frames and
   classifies events into standardized highlight categories with confidence scores.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)

logger = logging.getLogger(__name__)

# Event classification priorities and score weights
EVENT_HIERARCHY: list[tuple[str, str, int, float, re.Pattern[str]]] = [
    # Top Tier: Full wipes & maximum multi-kills
    (
        "team_wipe",
        "TEAM WIPE",
        6,
        1.00,
        re.compile(r"\b(TEAM\s*WIPE|HEXA\s*KO|6\s*KO|ACE)\b", re.IGNORECASE),
    ),
    (
        "penta_ko",
        "PENTA KO",
        5,
        0.95,
        re.compile(
            r"\b(PENTA\s*KO|QUINTUPLE\s*KO|5\s*KO|MEGA\s*KO)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "quad_ko",
        "QUAD KO",
        4,
        0.90,
        re.compile(
            r"\b(QUAD(?:RA?)?\s*KO|QUADRUPLE\s*KO|4\s*KO|ULTRA\s*KO)\b",
            re.IGNORECASE,
        ),
    ),
    # High-impact disruptions & streaks
    (
        "shutdown",
        "SHUTDOWN",
        1,
        0.88,
        re.compile(
            r"\b(SHUTDOWN|ULTIMATE\s*SHUTDOWN|DENIED)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "kill_streak",
        "KILL STREAK",
        1,
        0.85,
        re.compile(
            r"\b(UNSTOPPABLE|KILLING\s*SPREE|RAMPAGE|INVINCIBLE|GODLIKE)\b",
            re.IGNORECASE,
        ),
    ),
    # Standard multi-kills
    (
        "triple_ko",
        "TRIPLE KO",
        3,
        0.80,
        re.compile(r"\b(TRIPLE\s*KO|TRIPLE\s*KILL|3\s*KO)\b", re.IGNORECASE),
    ),
    # Objectives & match states (positive / clutch)
    (
        "objective_clutch",
        "OBJECTIVE CLUTCH",
        0,
        0.75,
        re.compile(
            r"\b(VICTORY|ROUND\s*WON|MATCH\s*WON|OVERTIME|CHECKPOINT|POINT\s*CAPTURED)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "double_ko",
        "DOUBLE KO",
        2,
        0.70,
        re.compile(r"\b(DOUBLE\s*KO|DOUBLE\s*KILL|2\s*KO)\b", re.IGNORECASE),
    ),
    # Base single elimination
    (
        "single_ko",
        "SINGLE KO",
        1,
        0.50,
        re.compile(
            r"(?:\+100|\b(?:ELIMINATED|FINAL\s*BLOW|KO|FIRST\s*BLOOD)\b)",
            re.IGNORECASE,
        ),
    ),
    # End-of-match state (low priority context)
    (
        "match_defeat",
        "DEFEAT",
        0,
        0.35,
        re.compile(r"\b(DEFEAT|ROUND\s*LOST)\b", re.IGNORECASE),
    ),
]


class VisualDetectionEvent(BaseModel):
    """Specific gameplay event identified via color and OCR matching."""

    timestamp: float = Field(..., description="Event timestamp in seconds")
    roi_name: str = Field(..., description="ROI region where event was detected")
    event_type: str = Field(
        ...,
        description=(
            "Classified event type: team_wipe, penta_ko, quad_ko, shutdown, "
            "kill_streak, triple_ko, objective_clutch, double_ko, single_ko, match_defeat"
        ),
    )
    label: str = Field(..., description="Matched trigger banner or text keyword")
    confidence: float = Field(..., description="Detection confidence score (0.0-1.0)")
    gold_pixel_ratio: float = Field(
        default=0.0, description="Ratio of Gold/Yellow elimination pixels"
    )
    red_pixel_ratio: float = Field(
        default=0.0, description="Ratio of Red elimination/accent pixels"
    )
    raw_text: str = Field(default="", description="Normalized raw OCR text")
    kill_count: int = Field(default=1, description="Associated elimination count")
    score_weight: float = Field(default=0.55, description="Event tier weight")


class WindowVisualMatchResult(BaseModel):
    """All visual HUD detection events within a candidate action window."""

    window_start: float = Field(..., description="Window start timestamp in seconds")
    window_end: float = Field(..., description="Window end timestamp in seconds")
    window_duration: float = Field(..., description="Window duration in seconds")
    events: list[VisualDetectionEvent] = Field(
        default_factory=list,
        description="Chronological detection events in window",
    )
    peak_event_type: str | None = Field(
        default=None,
        description="Highest tier event detected (e.g. team_wipe, triple_ko)",
    )
    total_kills: int = Field(default=0, description="Estimated kills in window")
    frames_evaluated: int = Field(default=0, description="Total ROI frames evaluated")
    frames_passed_color_filter: int = Field(
        default=0, description="Frames that triggered OCR analysis"
    )


class BatchVisualMatchResult(BaseModel):
    """Aggregated visual matching results across all candidate windows."""

    file_path: str = Field(..., description="Source video path")
    windows_matched: list[WindowVisualMatchResult] = Field(
        default_factory=list,
        description="Detection results per candidate window",
    )
    total_events_detected: int = Field(
        default=0, description="Total verified detection events across all windows"
    )
    processing_time_seconds: float = Field(
        default=0.0, description="Total wall-clock processing time"
    )


class VisualMatcherConfig(BaseModel):
    """Configuration for HSV color gating and OCR trigger matching."""

    min_gold_ratio: float = Field(
        default=0.001,
        description="Minimum ratio of Gold pixels to trigger OCR (default 0.1% / ~86 pixels)",
    )
    min_red_ratio: float = Field(
        default=0.001,
        description="Minimum ratio of Red pixels to trigger OCR (default 0.1% / ~86 pixels)",
    )
    ocr_min_confidence: float = Field(
        default=0.35, description="Minimum OCR word confidence threshold"
    )
    skip_ocr_without_color: bool = Field(
        default=True,
        description="If True, skips OCR unless gold or red color ratio exceeds threshold",
    )
    # HSV bounds for Marvel Rivals Gold (#FFD700): OpenCV H=[0,180], S=[0,255], V=[0,255]
    hsv_gold_lower: tuple[int, int, int] = (15, 100, 140)
    hsv_gold_upper: tuple[int, int, int] = (38, 255, 255)
    # HSV bounds for Marvel Rivals Red: wraps around 0 and 180
    hsv_red_lower1: tuple[int, int, int] = (0, 100, 140)
    hsv_red_upper1: tuple[int, int, int] = (10, 255, 255)
    hsv_red_lower2: tuple[int, int, int] = (170, 100, 140)
    hsv_red_upper2: tuple[int, int, int] = (180, 255, 255)


class VisualMatcher:
    """Two-phase visual event extraction engine."""

    def __init__(self, config: VisualMatcherConfig | None = None) -> None:
        self.config = config or VisualMatcherConfig()
        self._ocr_engine: Any = None
        self._init_ocr()

    def _init_ocr(self) -> None:
        """Initialize RapidOCR engine lazily."""
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr_engine = RapidOCR()
            logger.debug("RapidOCR engine initialized successfully.")
        except Exception as e:
            logger.warning(
                "Failed to initialize RapidOCR; falling back to mock/color-only mode: %s",
                e,
            )
            self._ocr_engine = None

    def check_color_triggers(self, frame: ROIFrame) -> tuple[bool, float, float]:
        """
        Check if frame contains gold or red Marvel Rivals elimination accents.

        Returns (has_trigger, gold_ratio, red_ratio).
        """
        try:
            import cv2

            arr = np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
                (frame.height, frame.width, 3)
            )
            hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

            # 1. Gold mask
            g_low = np.array(self.config.hsv_gold_lower, dtype=np.uint8)
            g_high = np.array(self.config.hsv_gold_upper, dtype=np.uint8)
            gold_mask = cv2.inRange(hsv, g_low, g_high)
            gold_count = int(cv2.countNonZero(gold_mask))

            # 2. Red mask (two ranges for Hue wrap-around)
            r_low1 = np.array(self.config.hsv_red_lower1, dtype=np.uint8)
            r_high1 = np.array(self.config.hsv_red_upper1, dtype=np.uint8)
            r_low2 = np.array(self.config.hsv_red_lower2, dtype=np.uint8)
            r_high2 = np.array(self.config.hsv_red_upper2, dtype=np.uint8)
            red_mask1 = cv2.inRange(hsv, r_low1, r_high1)
            red_mask2 = cv2.inRange(hsv, r_low2, r_high2)
            red_count = int(cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2))

            total_pixels = frame.width * frame.height
            gold_ratio = gold_count / total_pixels if total_pixels > 0 else 0.0
            red_ratio = red_count / total_pixels if total_pixels > 0 else 0.0

        except Exception:
            # Pure Python fallback
            gold_matches = frame.count_color_matches(220, 255, 180, 240, 0, 60)
            red_matches = frame.count_color_matches(180, 255, 0, 60, 0, 60)
            total = frame.width * frame.height
            gold_ratio = gold_matches / total if total > 0 else 0.0
            red_ratio = red_matches / total if total > 0 else 0.0

        has_trigger = (
            gold_ratio >= self.config.min_gold_ratio
            or red_ratio >= self.config.min_red_ratio
        )
        return has_trigger, round(gold_ratio, 4), round(red_ratio, 4)

    def run_ocr(self, frame: ROIFrame) -> list[tuple[str, float]]:
        """
        Execute OCR on in-memory frame buffer.

        Returns list of (detected_text, confidence).
        """
        if self._ocr_engine is None:
            return []

        try:
            arr = np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
                (frame.height, frame.width, 3)
            )
            results, _ = self._ocr_engine(arr)
            if not results:
                return []

            extracted: list[tuple[str, float]] = []
            for item in results:
                # RapidOCR format: [box, text, confidence]
                if len(item) >= 3:
                    text = str(item[1]).strip()
                    conf = float(item[2])
                    if text and conf >= self.config.ocr_min_confidence:
                        extracted.append((text, conf))
            return extracted
        except Exception as e:
            logger.warning(
                "OCR processing failed for frame at %.2fs: %s", frame.timestamp, e
            )
            return []

    def classify_text(self, text: str) -> tuple[str, str, int, float] | None:
        """
        Classify text against Marvel Rivals event hierarchy.

        Returns (event_type, label, kill_count, score_weight) or None.
        """
        cleaned = text.upper()
        # Common OCR substitution normalizations
        cleaned = re.sub(r"[0O]VERTIME", "OVERTIME", cleaned)
        cleaned = re.sub(r"TR[I1L]PLE", "TRIPLE", cleaned)
        cleaned = re.sub(r"D[0O]UBLE", "DOUBLE", cleaned)
        cleaned = re.sub(r"V[I1L]CT[0O]RY", "VICTORY", cleaned)

        for event_type, _label, kill_count, weight, pattern in EVENT_HIERARCHY:
            match = pattern.search(cleaned)
            if match:
                matched_label = match.group(0).upper()
                return event_type, matched_label, kill_count, weight
        return None

    def evaluate_frame(self, frame: ROIFrame) -> VisualDetectionEvent | None:
        """
        Evaluate a single ROI frame using two-phase color gating and OCR trigger matching.
        """
        has_color, gold_ratio, red_ratio = self.check_color_triggers(frame)

        if self.config.skip_ocr_without_color and not has_color:
            return None

        ocr_items = self.run_ocr(frame)
        if not ocr_items:
            return None

        combined_text = " ".join(t[0] for t in ocr_items)
        max_conf = max(t[1] for t in ocr_items)

        classification = self.classify_text(combined_text)
        if not classification:
            return None

        event_type, matched_label, kill_count, weight = classification

        return VisualDetectionEvent(
            timestamp=frame.timestamp,
            roi_name=frame.roi_name,
            event_type=event_type,
            label=matched_label,
            confidence=round(max_conf, 3),
            gold_pixel_ratio=gold_ratio,
            red_pixel_ratio=red_ratio,
            raw_text=combined_text,
            kill_count=kill_count,
            score_weight=weight,
        )

    def evaluate_window(
        self, window_rois: WindowROIExtractionResult
    ) -> WindowVisualMatchResult:
        """
        Evaluate all extracted ROI frames within a candidate action window.
        """
        events: list[VisualDetectionEvent] = []
        frames_eval = 0
        frames_passed_color = 0

        # Primary ROIs to inspect in order
        roi_order = ["center_ko", "kill_feed", "objective_banner"]

        for roi_name in roi_order:
            frames = window_rois.frames_by_roi.get(roi_name, [])
            for f in frames:
                frames_eval += 1
                has_color, _, _ = self.check_color_triggers(f)
                if has_color:
                    frames_passed_color += 1

                evt = self.evaluate_frame(f)
                if evt:
                    # Deduplicate: if same event on same ROI within 1.0s, skip duplicate frame
                    if not any(
                        prev.roi_name == evt.roi_name
                        and prev.event_type == evt.event_type
                        and abs(prev.timestamp - evt.timestamp) < 1.0
                        for prev in events
                    ):
                        events.append(evt)

        # Sort events chronologically
        events.sort(key=lambda e: e.timestamp)

        # Determine peak event type
        peak_event: str | None = None
        max_weight = 0.0
        total_kills = 0

        for e in events:
            if e.score_weight > max_weight:
                max_weight = e.score_weight
                peak_event = e.event_type
            if e.kill_count > 0:
                total_kills = max(total_kills, e.kill_count)

        return WindowVisualMatchResult(
            window_start=window_rois.window_start,
            window_end=window_rois.window_end,
            window_duration=window_rois.window_duration,
            events=events,
            peak_event_type=peak_event,
            total_kills=total_kills,
            frames_evaluated=frames_eval,
            frames_passed_color_filter=frames_passed_color,
        )

    def evaluate_batch(
        self,
        batch_rois: BatchROIExtractionResult,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> BatchVisualMatchResult:
        """
        Evaluate candidate windows in batch.
        """
        start_time = time.perf_counter()
        matched_windows: list[WindowVisualMatchResult] = []
        total_events = 0
        total_wins = len(batch_rois.windows_extracted)

        for idx, win in enumerate(batch_rois.windows_extracted, 1):
            if progress_callback and total_wins > 0:
                pct = round(((idx - 1) / total_wins) * 100.0, 1)
                progress_callback(
                    pct,
                    f"Analyzing visual HUD triggers (window {idx}/{total_wins})",
                )

            res = self.evaluate_window(win)
            matched_windows.append(res)
            total_events += len(res.events)

        if progress_callback:
            progress_callback(100.0, "Visual HUD trigger analysis completed")

        duration_sec = round(time.perf_counter() - start_time, 3)
        logger.info(
            "Visual matching complete on %s: %d events detected across %d windows in %.2fs.",
            batch_rois.file_path,
            total_events,
            total_wins,
            duration_sec,
        )

        return BatchVisualMatchResult(
            file_path=batch_rois.file_path,
            windows_matched=matched_windows,
            total_events_detected=total_events,
            processing_time_seconds=duration_sec,
        )


def evaluate_window_visuals(
    window_rois: WindowROIExtractionResult,
    config: VisualMatcherConfig | None = None,
) -> WindowVisualMatchResult:
    """Convenience function to evaluate visual triggers for a single window."""
    matcher = VisualMatcher(config=config)
    return matcher.evaluate_window(window_rois)


def evaluate_batch_visuals(
    batch_rois: BatchROIExtractionResult,
    config: VisualMatcherConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> BatchVisualMatchResult:
    """Convenience function to evaluate visual triggers for a batch of windows."""
    matcher = VisualMatcher(config=config)
    return matcher.evaluate_batch(batch_rois, progress_callback=progress_callback)
