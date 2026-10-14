"""Marvel Rivals specialized highlight candidate detector."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from app.config import settings
from app.services.highlight.cluster_engine import ClusterConfig, HighlightCandidate
from app.services.highlight.detectors.base import (
    BaseHighlightDetector,
    DetectionMetrics,
)

logger = logging.getLogger(__name__)


class MarvelRivalsDetector(BaseHighlightDetector):
    """
    Marvel Rivals highlight detector.
    Pipeline:
    1. Audio Energy Scanner (~100-400x realtime)
    2. HUD ROI Extraction (1.5 FPS at center_ko and kill_feed)
    3. HSV Color Masking & OCR Trigger Matching
    4. Window Clustering, Cinematic Padding & Scoring Hierarchy
    """

    game_id: str = "marvel_rivals"
    game_display_name: str = "Marvel Rivals"

    def detect(
        self,
        video_id: str,
        media_path: Path,
        min_score: float = 0.5,
        progress_callback: Callable[[float, str], None] | None = None,
        metrics: DetectionMetrics | None = None,
    ) -> list[HighlightCandidate]:
        """Execute end-to-end Marvel Rivals highlight detection."""
        # Late import from service to support runtime monkeypatching in test fixtures
        import app.services.highlight.service as s

        # Stage 1: Audio Scan
        if progress_callback:
            progress_callback(15.0, "Scanning audio excitement & pruning silence...")

        t0 = time.perf_counter()
        audio_scan = s.scan_audio_energy(media_path=media_path)
        audio_duration = time.perf_counter() - t0

        candidate_windows = audio_scan.candidate_windows
        if metrics is not None:
            metrics.audio_scan_duration_seconds = round(audio_duration, 3)
            metrics.audio_windows_count = len(candidate_windows)
            metrics.video_duration_seconds = round(audio_scan.duration_seconds, 2)

        logger.info(
            "Marvel Rivals audio scan completed for %s: found %d candidate windows in %.1fs (scanned in %.2fs)",
            video_id,
            len(candidate_windows),
            audio_scan.duration_seconds,
            audio_duration,
        )

        visual_matches = None

        if candidate_windows:
            # Stage 2: ROI Extraction
            if progress_callback:
                progress_callback(
                    40.0,
                    f"Extracting HUD ROIs across {len(candidate_windows)} action windows...",
                )

            t_roi = time.perf_counter()
            roi_results = s.extract_candidate_windows_rois(
                media_path=media_path,
                windows=candidate_windows,
            )
            roi_duration = time.perf_counter() - t_roi
            if metrics is not None:
                metrics.roi_extract_duration_seconds = round(roi_duration, 3)
                metrics.frames_analyzed_count = getattr(roi_results, "total_frames", 0)

            # Stage 3: Visual Color & OCR Matcher
            if progress_callback:
                progress_callback(
                    65.0,
                    "Running HSV color gating & OCR event trigger matching...",
                )

            t_vis = time.perf_counter()
            visual_matches = s.evaluate_batch_visuals(roi_results)
            vis_duration = time.perf_counter() - t_vis
            if metrics is not None:
                metrics.visual_match_duration_seconds = round(vis_duration, 3)
                metrics.visual_events_count = getattr(
                    visual_matches, "total_events_detected", 0
                )

            logger.info(
                "Marvel Rivals visual matcher completed for %s: evaluated %d windows, %d triggered events (in %.2fs)",
                video_id,
                len(visual_matches.windows_matched),
                visual_matches.total_events_detected,
                vis_duration,
            )

        # Stage 4: Clustering & Thumbnail Extraction
        if progress_callback:
            progress_callback(
                85.0, "Clustering event chains and generating thumbnails..."
            )

        t_cluster = time.perf_counter()
        cluster_engine = s.ClusterEngine(
            config=ClusterConfig(thumbnails_dir=str(settings.highlights_path))
        )
        candidates = cluster_engine.assemble_candidates(
            video_id=video_id,
            media_path=media_path,
            visual_matches=visual_matches,
            audio_windows=candidate_windows,
            total_duration=audio_scan.duration_seconds,
        )
        cluster_duration = time.perf_counter() - t_cluster
        if metrics is not None:
            metrics.cluster_duration_seconds = round(cluster_duration, 3)

        filtered = [c for c in candidates if c.score >= min_score]
        logger.info(
            "Marvel Rivals clustering completed for %s: assembled %d candidate clips (score >= %.2f)",
            video_id,
            len(filtered),
            min_score,
        )
        return filtered
