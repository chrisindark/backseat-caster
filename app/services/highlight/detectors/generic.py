"""Generic highlight candidate detector for single-player games and general VODs."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

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

logger = logging.getLogger(__name__)


class GenericHighlightDetector(BaseHighlightDetector):
    """
    Detector for single-player games and general gameplay.
    Operates without game-specific HUD OCR or visual template matching.
    Pipeline:
    1. Audio Energy Scanner: Detects loudness excitement spikes and intense moments.
    2. Window Merging & Cinematic Padding (6s pre-roll, 4s post-roll, clamped 18-45s).
    3. Peak Climax Thumbnail Extraction.
    4. Quality Scoring & Dynamic Catchy Title Generation.
    """

    def __init__(self, game_name: str = "Generic"):
        self.game_name = game_name.strip() or "Generic"
        self.game_id = (
            re.sub(r"[^a-zA-Z0-9_]", "_", self.game_name.lower()) or "generic"
        )
        self.game_display_name = self.game_name

    def detect(
        self,
        video_id: str,
        media_path: Path,
        min_score: float = 0.5,
        progress_callback: Callable[[float, str], None] | None = None,
        metrics: DetectionMetrics | None = None,
    ) -> list[HighlightCandidate]:
        """Detect generic highlight candidates based on high-energy audio excitement."""
        import app.services.highlight.service as s

        # Stage 1: Audio Energy Scan
        if progress_callback:
            progress_callback(15.0, "Scanning audio excitement & pruning silence...")

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
            "Generic audio scan completed for %s: found %d action windows across %.1fs (scanned in %.2fs)",
            video_id,
            len(windows),
            total_duration,
            audio_duration,
        )

        if not windows:
            if progress_callback:
                progress_callback(100.0, "Scan complete: No high-energy moments found.")
            return []

        # Stage 2: Merge nearby action windows & apply cinematic padding
        t_cluster = time.perf_counter()
        if progress_callback:
            progress_callback(
                50.0,
                f"Clustering {len(windows)} high-energy action windows with cinematic padding...",
            )

        merged_segments = self._merge_audio_windows(windows, gap_threshold=4.0)

        # Stage 3: Build candidates & thumbnails
        if progress_callback:
            progress_callback(
                80.0,
                "Extracting climax thumbnails and generating highlight metadata...",
            )

        candidates: list[HighlightCandidate] = []
        pre_roll = 6.0
        post_roll = 4.0
        min_dur = 18.0
        max_dur = 45.0

        for seg in merged_segments:
            seg_start = seg["start_seconds"]
            seg_end = seg["end_seconds"]
            seg_score = seg["score"]
            peak_timestamp = seg["peak_timestamp"]

            # Pad with cinematic pre-roll and post-roll
            raw_start = max(0.0, seg_start - pre_roll)
            raw_end = min(total_duration, seg_end + post_roll)
            dur = raw_end - raw_start

            # Enforce duration constraints
            if dur < min_dur:
                needed = min_dur - dur
                raw_start = max(0.0, raw_start - needed * 0.5)
                raw_end = min(total_duration, raw_start + min_dur)
                dur = raw_end - raw_start

            if dur > max_dur:
                half_max = max_dur / 2.0
                raw_start = max(0.0, peak_timestamp - half_max)
                raw_end = min(total_duration, raw_start + max_dur)
                dur = raw_end - raw_start

            final_score = round(min(1.0, max(0.0, seg_score)), 2)
            if final_score < min_score:
                continue

            # Event type & title generation
            if final_score >= 0.85:
                event_type = "epic_climax"
            elif final_score >= 0.70:
                event_type = "intense_action"
            else:
                event_type = "gameplay_highlight"

            title, tags = self._generate_title_and_tags(event_type, final_score)

            cid_hash = hashlib.md5(
                f"{video_id}_{raw_start:.1f}_{raw_end:.1f}_{self.game_id}".encode()
            ).hexdigest()[:6]
            candidate_id = f"cand_gen_{cid_hash}"

            # Extract climax preview thumbnail
            thumb_path_str: str | None = None
            thumb_url_str: str | None = None
            try:
                thumb_dest = settings.highlights_path / candidate_id / "thumb.jpg"
                extract_thumbnail_frame(media_path, peak_timestamp, thumb_dest)
                thumb_path_str = str(thumb_dest.resolve())
                thumb_url_str = (
                    f"/api/v1/videos/{video_id}/highlights/{candidate_id}/thumb.jpg"
                )
            except Exception as thumb_err:
                logger.warning(
                    "Thumbnail extraction failed for candidate %s: %s",
                    candidate_id,
                    thumb_err,
                )

            details = HighlightDetails(
                kill_count=None,
                has_ultimate=None,
                is_team_wipe=None,
                game_phase="regular",
                trigger_events=[
                    TriggerEvent(
                        time=round(peak_timestamp, 2),
                        label="Peak Energy Moment",
                        roi_name="audio_energy",
                        confidence=final_score,
                    )
                ],
            )

            candidates.append(
                HighlightCandidate(
                    candidate_id=candidate_id,
                    video_id=video_id,
                    start_seconds=round(raw_start, 2),
                    end_seconds=round(raw_end, 2),
                    duration_seconds=round(dur, 2),
                    score=final_score,
                    event_type=event_type,
                    game=self.game_display_name,
                    details=details,
                    thumbnail_url=thumb_url_str,
                    thumbnail_path=thumb_path_str,
                    peak_timestamp=round(peak_timestamp, 2),
                    suggested_title=title,
                    suggested_tags=tags,
                )
            )

        deduped = self._deduplicate_candidates(candidates)
        deduped.sort(key=lambda c: c.score, reverse=True)

        if metrics is not None:
            metrics.cluster_duration_seconds = round(time.perf_counter() - t_cluster, 3)

        return deduped

    def _merge_audio_windows(
        self,
        windows: list[AudioCandidateWindow],
        gap_threshold: float = 4.0,
    ) -> list[dict]:
        """Merge adjacent audio action windows occurring within gap_threshold seconds."""
        if not windows:
            return []

        sorted_wins = sorted(windows, key=lambda w: w.start_seconds)
        merged: list[dict] = []

        cur = {
            "start_seconds": sorted_wins[0].start_seconds,
            "end_seconds": sorted_wins[0].end_seconds,
            "score": sorted_wins[0].score,
            "peak_timestamp": (
                sorted_wins[0].start_seconds + sorted_wins[0].end_seconds
            )
            / 2.0,
            "peak_lufs": sorted_wins[0].peak_lufs,
        }

        for nxt in sorted_wins[1:]:
            if nxt.start_seconds - cur["end_seconds"] <= gap_threshold:
                # Merge
                cur["end_seconds"] = max(cur["end_seconds"], nxt.end_seconds)
                cur["score"] = max(cur["score"], nxt.score)
                if nxt.peak_lufs > cur["peak_lufs"]:
                    cur["peak_lufs"] = nxt.peak_lufs
                    cur["peak_timestamp"] = (nxt.start_seconds + nxt.end_seconds) / 2.0
            else:
                merged.append(cur)
                cur = {
                    "start_seconds": nxt.start_seconds,
                    "end_seconds": nxt.end_seconds,
                    "score": nxt.score,
                    "peak_timestamp": (nxt.start_seconds + nxt.end_seconds) / 2.0,
                    "peak_lufs": nxt.peak_lufs,
                }

        merged.append(cur)
        return merged

    def _deduplicate_candidates(
        self, candidates: list[HighlightCandidate]
    ) -> list[HighlightCandidate]:
        """Deduplicate overlapping candidate clips."""
        if len(candidates) <= 1:
            return candidates

        candidates.sort(key=lambda c: c.start_seconds)
        deduped: list[HighlightCandidate] = []

        for cand in candidates:
            if not deduped:
                deduped.append(cand)
                continue

            prev = deduped[-1]
            overlap = prev.end_seconds - cand.start_seconds
            if overlap > 0 and (
                overlap / prev.duration_seconds > 0.40
                or overlap / cand.duration_seconds > 0.40
            ):
                if cand.score > prev.score:
                    deduped[-1] = cand
            else:
                deduped.append(cand)

        return deduped

    def _generate_title_and_tags(
        self, event_type: str, score: float
    ) -> tuple[str, list[str]]:
        """Generate catchy YouTube Shorts titles and hashtags."""
        clean_tag = re.sub(r"[^a-zA-Z0-9]", "", self.game_display_name)
        game_label = (
            f" #{clean_tag}" if clean_tag and clean_tag.lower() != "generic" else ""
        )

        if event_type == "epic_climax":
            title = f"Unbelievable Gaming Moment! 🔥{game_label} #Gaming #Shorts"
        elif event_type == "intense_action":
            title = f"Insane Intense Gameplay! ⚡{game_label} #Shorts #Gaming"
        else:
            title = f"Epic Gaming Highlight! 🎮{game_label} #Shorts #Clips"

        tags = ["Gaming", "Shorts", "Gameplay", "Clips", "Highlight"]
        if clean_tag and clean_tag.lower() != "generic":
            tags.insert(0, clean_tag)

        return title, tags
