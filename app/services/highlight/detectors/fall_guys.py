"""Fall Guys specialized highlight candidate detector.

Combines Center/Upper banner OCR trigger matching (Crown Victory, Qualified,
Final Round, Eliminated) with high-energy audio excitement scanning and
natural dialogue boundary snapping for broadcast-quality YouTube Shorts.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import settings
from app.rendering.probe import probe_media
from app.services.highlight.audio_scanner import AudioCandidateWindow
from app.services.highlight.cluster_engine import (
    HighlightCandidate,
    HighlightDetails,
    TriggerEvent,
    extract_thumbnail_frame,
)
from app.services.highlight.detectors.base import (
    BaseHighlightDetector,
    DetectionMetrics,
)
from app.services.highlight.ocr import OCRReader
from app.services.highlight.roi_extractor import BatchROIExtractionResult
from app.services.highlight.speech_mining import snap_to_speech_boundaries

logger = logging.getLogger(__name__)

# Fall Guys event classification definitions: (event_type, label, score, pattern)
FALL_GUYS_EVENT_DEFINITIONS: list[tuple[str, str, float, re.Pattern[str]]] = [
    (
        "crown_victory",
        "Crown Victory",
        1.00,
        re.compile(r"\b(WINNER!?|CROWN|VICTORY|CHAMPION)\b", re.IGNORECASE),
    ),
    (
        "round_qualified",
        "Round Qualified",
        0.92,
        re.compile(r"\b(QUALIFIED!?|QUALIFY)\b", re.IGNORECASE),
    ),
    (
        "final_round",
        "Final Round",
        0.88,
        re.compile(r"\b(FINAL\s*ROUND)\b", re.IGNORECASE),
    ),
    (
        "round_over",
        "Round Over",
        0.82,
        re.compile(r"\b(ROUND\s*OVER)\b", re.IGNORECASE),
    ),
    (
        "eliminated",
        "Eliminated",
        0.78,
        re.compile(r"\b(ELIMINATED!?)\b", re.IGNORECASE),
    ),
]


class FallGuysDetector(BaseHighlightDetector):
    """
    Fall Guys highlight detector.
    Pipeline:
    1. Audio Energy Scanner (~100-400x realtime audio loudness peaks & crowd excitement)
    2. HUD ROI Extraction (1.0 FPS at center and upper banner regions)
    3. RapidOCR Banner Trigger Matching (Crown, Qualified, Final Round, Eliminated)
    4. Speech Boundary Snapping (snaps clip edges to natural dialogue pauses)
    5. Cinematic Padding, Thumbnail Extraction & YouTube Shorts Copy Generation
    """

    game_id: str = "fall_guys"
    game_display_name: str = "Fall Guys"

    def __init__(self, ocr_min_confidence: float = 0.35) -> None:
        self.ocr_reader = OCRReader(min_confidence=ocr_min_confidence)

    def detect(
        self,
        video_id: str,
        media_path: Path,
        min_score: float = 0.5,
        progress_callback: Callable[[float, str], None] | None = None,
        metrics: DetectionMetrics | None = None,
    ) -> list[HighlightCandidate]:
        """Execute end-to-end Fall Guys highlight detection."""
        import app.services.highlight.service as s

        # Stage 1: Audio Energy Scan
        if progress_callback:
            progress_callback(15.0, "Scanning audio excitement & crowd horns...")

        t0 = time.perf_counter()
        audio_scan = s.scan_audio_energy(media_path=media_path)
        audio_duration = time.perf_counter() - t0

        windows = audio_scan.candidate_windows
        total_duration = audio_scan.duration_seconds

        if total_duration <= 0.0:
            try:
                probe = probe_media(media_path)
                total_duration = probe.duration
            except Exception:
                total_duration = 0.0

        if metrics is not None:
            metrics.audio_scan_duration_seconds = round(audio_duration, 3)
            metrics.audio_windows_count = len(windows)
            metrics.video_duration_seconds = round(total_duration, 2)

        logger.info(
            "Fall Guys audio scan completed for %s: found %d candidate windows across %.1fs (scanned in %.2fs)",
            video_id,
            len(windows),
            total_duration,
            audio_duration,
        )

        if not windows:
            if progress_callback:
                progress_callback(100.0, "Scan complete: No action windows detected.")
            return []

        # Stage 2: HUD ROI Extraction across candidate windows
        if progress_callback:
            progress_callback(
                40.0,
                f"Extracting banner HUD ROIs across {len(windows)} action windows...",
            )

        t_roi = time.perf_counter()
        roi_results = s.extract_candidate_windows_rois(
            media_path=media_path,
            windows=windows,
            roi_names=["center_banner", "upper_banner"],
        )
        roi_duration = time.perf_counter() - t_roi

        if metrics is not None:
            metrics.roi_extract_duration_seconds = round(roi_duration, 3)
            metrics.frames_analyzed_count = getattr(roi_results, "total_frames", 0)

        # Stage 3: OCR Banner Trigger Matching
        if progress_callback:
            progress_callback(
                65.0, "Running RapidOCR on Fall Guys qualification & crown banners..."
            )

        t_vis = time.perf_counter()
        window_events = self._match_banner_events(roi_results)
        vis_duration = time.perf_counter() - t_vis

        total_detected_events = sum(len(evs) for evs in window_events.values())
        if metrics is not None:
            metrics.visual_match_duration_seconds = round(vis_duration, 3)
            metrics.visual_events_count = total_detected_events

        logger.info(
            "Fall Guys OCR matcher completed for %s: found %d banner events across %d windows (in %.2fs)",
            video_id,
            total_detected_events,
            len(window_events),
            vis_duration,
        )

        # Stage 4: Candidate assembly with speech boundary snapping
        if progress_callback:
            progress_callback(
                85.0, "Snapping clip boundaries to natural pauses and speech..."
            )

        t_cluster = time.perf_counter()
        raw_candidates = self._assemble_candidates(
            video_id=video_id,
            media_path=media_path,
            total_duration=total_duration,
            windows=windows,
            window_events=window_events,
            min_score=min_score,
        )
        cluster_duration = time.perf_counter() - t_cluster

        if metrics is not None:
            metrics.cluster_duration_seconds = round(cluster_duration, 3)

        # Deduplicate overlapping candidate windows
        deduped = self._deduplicate_candidates(raw_candidates)

        # Stage 5: Thumbnail extraction
        if progress_callback:
            progress_callback(95.0, "Extracting climax preview thumbnails and copy...")

        for cand in deduped:
            try:
                thumb_dest = settings.highlights_path / cand.candidate_id / "thumb.jpg"
                extract_thumbnail_frame(media_path, cand.peak_timestamp, thumb_dest)
                cand.thumbnail_path = str(thumb_dest.resolve())
                cand.thumbnail_url = f"/api/v1/videos/{video_id}/highlights/{cand.candidate_id}/thumb.jpg"
            except Exception as thumb_err:
                logger.warning(
                    "Thumbnail extraction failed for candidate %s at %.2fs: %s",
                    cand.candidate_id,
                    cand.peak_timestamp,
                    thumb_err,
                )

        logger.info(
            "Fall Guys highlight detection finished for %s: assembled %d clips (score >= %.2f)",
            video_id,
            len(deduped),
            min_score,
        )
        return deduped

    def _match_banner_events(
        self, roi_results: BatchROIExtractionResult | None
    ) -> dict[int, list[dict[str, Any]]]:
        """Run OCR on extracted banner frames and identify qualification/victory banners."""
        if not roi_results or not roi_results.windows_extracted:
            return {}

        events_by_window: dict[int, list[dict[str, Any]]] = {}

        for w_idx, win in enumerate(roi_results.windows_extracted):
            win_events: list[dict[str, Any]] = []

            # Check frames in center_banner (primary) and upper_banner
            banner_frames = win.frames_by_roi.get(
                "center_banner", []
            ) + win.frames_by_roi.get("upper_banner", [])

            for frame in banner_frames:
                tokens = self.ocr_reader.read(frame)
                if not tokens:
                    continue

                full_text = " ".join(t.text for t in tokens)
                for ev_type, label, score, pattern in FALL_GUYS_EVENT_DEFINITIONS:
                    if pattern.search(full_text):
                        win_events.append(
                            {
                                "time": round(frame.timestamp, 2),
                                "event_type": ev_type,
                                "label": label,
                                "score": score,
                                "confidence": max(t.confidence for t in tokens),
                                "roi_name": frame.roi_name,
                                "matched_text": full_text,
                            }
                        )
                        break

            if win_events:
                # Sort events chronologically within window
                win_events.sort(key=lambda x: x["time"])
                events_by_window[w_idx] = win_events

        return events_by_window

    def _assemble_candidates(
        self,
        video_id: str,
        media_path: Path,
        total_duration: float,
        windows: list[AudioCandidateWindow],
        window_events: dict[int, list[dict[str, Any]]],
        min_score: float,
    ) -> list[HighlightCandidate]:
        """Assemble highlight candidates with speech-to-pause boundary snapping."""
        candidates: list[HighlightCandidate] = []

        for idx, win in enumerate(windows):
            events = window_events.get(idx, [])

            if events:
                # Rank events by score priority
                best_event = max(events, key=lambda x: x["score"])
                event_type = best_event["event_type"]
                event_score = best_event["score"]
                peak_time = best_event["time"]
                pre_roll = 12.0  # obstacle gauntlet / finish line sprint
                post_roll = 4.0  # qualification animation / celebration
            else:
                # Fallback to high-energy audio excitement moment
                audio_score = win.score
                if audio_score >= 0.85:
                    event_type = "epic_climax"
                    event_score = 0.75
                elif audio_score >= 0.70:
                    event_type = "intense_action"
                    event_score = 0.70
                else:
                    event_type = "gameplay_highlight"
                    event_score = 0.60

                peak_time = (win.start_seconds + win.end_seconds) / 2.0
                pre_roll = 8.0
                post_roll = 4.0

            if event_score < min_score:
                continue

            raw_start = max(0.0, peak_time - pre_roll)
            raw_end = min(total_duration, peak_time + post_roll)

            # Snap boundaries to natural speech/audio pauses
            snapped_start, snapped_end, dur = snap_to_speech_boundaries(
                media_path=media_path,
                start_seconds=raw_start,
                end_seconds=raw_end,
                min_duration=18.0,
                max_duration=45.0,
            )

            # Title & tags generation
            title, tags = self._generate_title_and_tags(event_type, event_score)

            cid_hash = hashlib.md5(
                f"{video_id}_{snapped_start:.1f}_{snapped_end:.1f}_{event_type}".encode()
            ).hexdigest()[:6]
            candidate_id = f"cand_fg_{cid_hash}"

            trigger_events_list = [
                TriggerEvent(
                    time=ev["time"],
                    label=ev["label"],
                    roi_name=ev["roi_name"],
                    confidence=ev["confidence"],
                )
                for ev in events
            ]
            if not trigger_events_list:
                trigger_events_list = [
                    TriggerEvent(
                        time=round(peak_time, 2),
                        label="Audio Energy Climax",
                        roi_name="audio_energy",
                        confidence=event_score,
                    )
                ]

            details = HighlightDetails(
                game_phase="regular",
                climax_start_seconds=round(max(0.0, peak_time - 3.0), 2),
                climax_end_seconds=round(min(total_duration, peak_time + 3.0), 2),
                trigger_events=trigger_events_list,
            )

            candidates.append(
                HighlightCandidate(
                    candidate_id=candidate_id,
                    video_id=video_id,
                    start_seconds=round(snapped_start, 2),
                    end_seconds=round(snapped_end, 2),
                    duration_seconds=round(dur, 2),
                    score=round(event_score, 2),
                    event_type=event_type,
                    game=self.game_display_name,
                    details=details,
                    peak_timestamp=round(peak_time, 2),
                    suggested_title=title,
                    suggested_tags=tags,
                )
            )

        return candidates

    def _deduplicate_candidates(
        self, candidates: list[HighlightCandidate]
    ) -> list[HighlightCandidate]:
        """Deduplicate overlapping candidates, retaining the highest scoring clip."""
        if not candidates:
            return []

        # Sort descending by score
        sorted_cands = sorted(candidates, key=lambda c: c.score, reverse=True)
        retained: list[HighlightCandidate] = []

        for cand in sorted_cands:
            overlap = False
            for r in retained:
                # If clips overlap by more than 8 seconds or start within 8 seconds
                intersection = max(
                    0.0,
                    min(cand.end_seconds, r.end_seconds)
                    - max(cand.start_seconds, r.start_seconds),
                )
                if (
                    intersection > 8.0
                    or abs(cand.start_seconds - r.start_seconds) < 8.0
                ):
                    overlap = True
                    break
            if not overlap:
                retained.append(cand)

        # Return sorted by score
        retained.sort(key=lambda c: c.score, reverse=True)
        return retained

    def _generate_title_and_tags(
        self, event_type: str, score: float
    ) -> tuple[str, list[str]]:
        """Generate high-CTR YouTube Shorts titles and tags for Fall Guys."""
        base_tags = ["Fall Guys", "FallGuysGame", "Gaming", "Shorts", "Viral"]

        if event_type == "crown_victory":
            title = "UNREAL FALL GUYS CROWN VICTORY! 👑 #FallGuys #Shorts"
            tags = ["Crown", "Winner", "Champion", "Clutch"] + base_tags
        elif event_type == "round_qualified":
            title = "INSANE Fall Guys Round Qualification! ⚡ #FallGuys #Shorts"
            tags = ["Qualified", "Speedrun", "ObstacleCourse"] + base_tags
        elif event_type == "final_round":
            title = "FALL GUYS FINAL ROUND INTENSITY! 🔥 #FallGuys #Shorts"
            tags = ["FinalRound", "Crown", "HexAGone"] + base_tags
        elif event_type == "eliminated":
            title = "Heartbreaking Fall Guys Elimination! 💀 #FallGuys #Shorts"
            tags = ["Eliminated", "Fail", "SlimeClimb", "Funny"] + base_tags
        elif event_type == "round_over":
            title = "Fall Guys Chaos & Clutch Highlights! 🏃 #FallGuys #Shorts"
            tags = ["RoundOver", "Highlights", "Chaos"] + base_tags
        else:
            title = "Unbelievable Fall Guys Physics Chaos! 🏃 #FallGuys #Shorts"
            tags = ["Chaos", "FunnyMoments", "Clutch"] + base_tags

        return title, tags
