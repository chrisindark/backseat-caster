"""Marvel Rivals specialized highlight candidate detector."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from app.config import settings
from app.services.highlight.cluster_engine import ClusterConfig, HighlightCandidate
from app.services.highlight.deep_visuals import (
    DeepVisualConfig,
    evaluate_deep_visuals,
)
from app.services.highlight.detectors.base import (
    BaseHighlightDetector,
    DetectionMetrics,
)
from app.services.highlight.roi_extractor import ROIExtractorConfig

logger = logging.getLogger(__name__)


class MarvelRivalsDetector(BaseHighlightDetector):
    """
    Marvel Rivals highlight detector.
    Pipeline:
    1. Audio Energy Scanner (~100-400x realtime)
    2. HUD ROI Extraction (1.5 FPS at banners, killfeed, ultimate and hero ROIs)
    3. HSV Color Masking & OCR Trigger Matching
    4. Phase 3 Deep Visual Extraction (killfeed chains, ultimate casts, hero)
    5. Window Clustering, Cinematic Padding & Scoring Hierarchy
    """

    game_id: str = "marvel_rivals"
    game_display_name: str = "Marvel Rivals"

    def __init__(
        self,
        deep_visual_config: DeepVisualConfig | None = None,
        enable_deep_visuals: bool = True,
    ) -> None:
        self.deep_visual_config = deep_visual_config or DeepVisualConfig()
        self.enable_deep_visuals = enable_deep_visuals

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

            roi_config = ROIExtractorConfig()
            roi_names = list(roi_config.primary_rois)
            if self.enable_deep_visuals:
                roi_names.extend(roi_config.phase3_rois)

            t_roi = time.perf_counter()
            roi_results = s.extract_candidate_windows_rois(
                media_path=media_path,
                windows=candidate_windows,
                roi_names=roi_names,
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

        # Phase 3: Deep visual extraction (killfeed, ultimate, hero, abilities)
        deep_result = None
        if self.enable_deep_visuals and candidate_windows:
            if progress_callback:
                progress_callback(
                    75.0,
                    "Extracting killfeed chains, ultimate tracking & hero identity...",
                )

            t_deep = time.perf_counter()
            deep_result = evaluate_deep_visuals(
                roi_results, config=self.deep_visual_config
            )
            deep_duration = time.perf_counter() - t_deep
            if metrics is not None:
                metrics.deep_visual_duration_seconds = round(deep_duration, 3)
                metrics.killfeed_sequences_count = len(deep_result.killfeed.windows)
                metrics.ultimate_casts_count = len(deep_result.ultimate.casts)
                metrics.ability_activations_count = len(deep_result.abilities)

            logger.info(
                "Marvel Rivals deep visual extraction completed for %s: %d killfeed sequences, %d ultimate casts, hero=%s (in %.2fs)",
                video_id,
                len(deep_result.killfeed.windows),
                len(deep_result.ultimate.casts),
                deep_result.hero.hero if deep_result.hero else "unknown",
                deep_duration,
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
            killfeed_sequences=(deep_result.killfeed.windows if deep_result else None),
            ultimate_casts=(deep_result.ultimate.casts if deep_result else None),
            hero_name=(
                deep_result.hero.hero if deep_result and deep_result.hero else None
            ),
            abilities_used=(
                [activation.ability for activation in deep_result.abilities]
                if deep_result
                else None
            ),
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
