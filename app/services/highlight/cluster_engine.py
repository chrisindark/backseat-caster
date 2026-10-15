"""Highlight Candidate Clustering, Cinematic Padding & Scoring Engine.

Assembles raw detection events and audio excitement windows into publish-ready
30-60 second YouTube Shorts candidate clips. Applies intelligent pre-roll (6-8s)
and post-roll (3-5s) padding, enforces duration retention constraints, scores
candidates using a weighted gaming event hierarchy, extracts peak action thumbnails,
and auto-generates catchy Short titles and tags.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.rendering.probe import probe_media
from app.services.highlight.audio_scanner import AudioCandidateWindow
from app.services.highlight.visual_matcher import (
    BatchVisualMatchResult,
    VisualDetectionEvent,
)

logger = logging.getLogger(__name__)


class TriggerEvent(BaseModel):
    """Specific moment of action inside a highlight clip."""

    time: float = Field(..., description="Timestamp of the event in seconds")
    label: str = Field(
        ..., description="Event label (e.g. Elimination, DOUBLE KO, TEAM WIPE)"
    )
    roi_name: str = Field(default="center_ko", description="Region where detected")
    confidence: float = Field(default=1.0, description="Detection confidence")

    model_config = ConfigDict(extra="allow")


class HighlightDetails(BaseModel):
    """Rich structured metadata describing the highlight contents."""

    kill_count: int | None = Field(
        default=None, description="Total kills scored during the highlight clip"
    )
    has_ultimate: bool | None = Field(
        default=None,
        description="True if an ultimate ability cast or shutdown was involved",
    )
    is_team_wipe: bool | None = Field(
        default=None, description="True if the clip resulted in a team wipe"
    )
    game_phase: str | None = Field(
        default="regular", description="Game state: overtime, clutch, or regular"
    )
    streak_count: int | None = Field(
        default=None,
        description="Active kill streak milestone (e.g. 5 for 5-player KO streak)",
    )
    climax_start_seconds: float | None = Field(
        default=None, description="Start timestamp of core action climax"
    )
    climax_end_seconds: float | None = Field(
        default=None, description="End timestamp of core action climax"
    )
    trigger_events: list[TriggerEvent] = Field(
        default_factory=list,
        description="Chronological event timestamps and labels",
    )

    model_config = ConfigDict(extra="allow")


class HighlightCandidate(BaseModel):
    """Publish-ready highlight candidate matching the BackseatCaster specification."""

    candidate_id: str = Field(
        ..., description="Unique highlight candidate ID (e.g. cand_mvr_91a2b)"
    )
    video_id: str = Field(..., description="Source video identifier")
    start_seconds: float = Field(..., description="Clip start timestamp in seconds")
    end_seconds: float = Field(..., description="Clip end timestamp in seconds")
    duration_seconds: float = Field(..., description="Clip duration in seconds")
    score: float = Field(..., description="Ranked quality score between 0.0 and 1.0")
    event_type: str = Field(
        ...,
        description="Primary event classification (e.g. team_wipe, triple_ko, double_ko)",
    )
    game: str = Field(default="Marvel Rivals", description="Source game name")
    details: HighlightDetails = Field(
        default_factory=HighlightDetails, description="Structured highlight details"
    )
    thumbnail_url: str | None = Field(
        default=None, description="API URL for thumbnail preview"
    )
    thumbnail_path: str | None = Field(
        default=None, description="Local filesystem path to thumbnail"
    )
    peak_timestamp: float = Field(
        default=0.0, description="Timestamp of the climax / peak action event"
    )
    suggested_title: str = Field(
        default="", description="Catchy title generated for YouTube Shorts"
    )
    suggested_tags: list[str] = Field(
        default_factory=list, description="Recommended YouTube hashtags and tags"
    )


class ClusterConfig(BaseModel):
    """Configuration for clustering, padding, and scoring highlight candidates."""

    event_merge_gap_seconds: float = Field(
        default=5.0,
        description="Merge events occurring within this interval into a single chain",
    )
    pre_roll_seconds: float = Field(
        default=10.0,
        description="Cinematic pre-roll before first action event (captures neutral zone setup/flank approach)",
    )
    post_roll_seconds: float = Field(
        default=8.0,
        description="Cinematic post-roll after last action event (captures aftermath, reaction, emote)",
    )
    min_clip_duration: float = Field(
        default=35.0,
        description="Minimum candidate clip duration (provides narrative context for LLM/Gemini trimming)",
    )
    max_clip_duration: float = Field(
        default=60.0,
        description="Maximum clip duration for YouTube Shorts (clamped ceiling)",
    )
    thumbnails_dir: str = Field(
        default="./data/highlights",
        description="Directory to store extracted thumbnail images",
    )
    generate_thumbnails: bool = Field(
        default=True,
        description="Extract high-resolution preview thumbnails via FFmpeg",
    )


def generate_suggested_title(
    event_type: str,
    kill_count: int = 1,
    game_phase: str = "regular",
    is_team_wipe: bool = False,
    character_name: str | None = None,
    streak_count: int | None = None,
) -> str:
    """Generate a catchy, high-engagement YouTube Shorts title with gaming emojis."""
    hero_prefix = f"{character_name} " if character_name else ""
    is_ot = game_phase.lower() == "overtime"

    if is_team_wipe or event_type == "team_wipe":
        if is_ot:
            return f"Insane {hero_prefix}Team Wipe in Overtime! 💥 #MarvelRivals"
        return f"Insane {hero_prefix}Team Wipe Ultimate! 💥 #MarvelRivals"

    if event_type == "penta_ko":
        return (
            f"Unreal {hero_prefix}Penta KO in Overtime! 🔥 #MarvelRivals"
            if is_ot
            else f"Unreal {hero_prefix}Penta KO Climax! 🔥 #MarvelRivals"
        )

    if event_type == "quad_ko":
        return (
            f"Crazy {hero_prefix}Quad KO in Overtime! ⚡️ #MarvelRivals"
            if is_ot
            else f"Crazy {hero_prefix}Quad KO Chain! ⚡️ #MarvelRivals"
        )

    if event_type == "shutdown":
        return f"Huge {hero_prefix}Ultimate Shutdown Denied! 🛑 #MarvelRivals"

    if event_type == "kill_streak" or streak_count:
        if streak_count == 5:
            return (
                f"Unreal {hero_prefix}5-Player KO Streak! 🔥 #MarvelRivals"
                if not is_ot
                else f"Unreal {hero_prefix}5-Player KO Streak in Overtime! 🔥 #MarvelRivals"
            )
        elif streak_count == 4:
            return (
                f"Crazy {hero_prefix}4-Player KO Streak! ⚡️ #MarvelRivals"
                if not is_ot
                else f"Crazy {hero_prefix}4-Player KO Streak in Overtime! ⚡️ #MarvelRivals"
            )
        elif streak_count == 3:
            return (
                f"Clean {hero_prefix}3-Player KO Streak! 🔥 #MarvelRivals"
                if not is_ot
                else f"Clean {hero_prefix}3-Player KO Streak in Overtime! 🔥 #MarvelRivals"
            )
        elif is_ot:
            return f"Unstoppable {hero_prefix}Kill Streak in Overtime! 🚀 #MarvelRivals"
        return f"Unstoppable {hero_prefix}Kill Streak Unleashed! 🚀 #MarvelRivals"

    if event_type == "triple_ko":
        if is_ot:
            return f"Clean {hero_prefix}Triple KO in Overtime! 🔥 #MarvelRivals"
        return f"Clean {hero_prefix}Triple KO Highlight! 🔥 #MarvelRivals"

    if event_type == "double_ko":
        if is_ot:
            return f"Fast {hero_prefix}Double KO in Overtime! ⚡️ #MarvelRivals"
        return f"Fast {hero_prefix}Double KO Highlight! ⚡️ #MarvelRivals"

    if event_type == "objective_clutch":
        return (
            f"Clutch {hero_prefix}Overtime Victory! 🏆 #MarvelRivals"
            if is_ot
            else f"Clutch {hero_prefix}Objective Defense! 🏆 #MarvelRivals"
        )

    if event_type == "double_ko":
        return (
            f"Smooth {hero_prefix}Double KO in Overtime! ⚡️ #MarvelRivals"
            if is_ot
            else f"Smooth {hero_prefix}Double KO Climax! ⚡️ #MarvelRivals"
        )

    if event_type == "single_ko":
        return f"Clean {hero_prefix}Elimination Highlight! 🎯 #MarvelRivals"

    return f"Insane {hero_prefix}Marvel Rivals Highlight! 🔥 #MarvelRivals"


def generate_suggested_tags(event_type: str, game_phase: str = "regular") -> list[str]:
    """Generate relevant YouTube hashtags for viral gaming clips."""
    tags = ["MarvelRivals", "Gaming", "Shorts", "Gameplay"]
    type_map = {
        "team_wipe": "TeamWipe",
        "penta_ko": "PentaKO",
        "quad_ko": "QuadKO",
        "triple_ko": "TripleKO",
        "double_ko": "DoubleKO",
        "shutdown": "Shutdown",
        "kill_streak": "KillStreak",
        "objective_clutch": "Clutch",
    }
    if event_type in type_map:
        tags.insert(3, type_map[event_type])
    if game_phase.lower() == "overtime":
        tags.append("Overtime")
    return tags


def extract_thumbnail_frame(
    media_path: Path | str, timestamp: float, output_path: Path | str
) -> Path:
    """Extract a high-resolution JPEG thumbnail at the specified timestamp."""
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(media_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=15)
    return out


class ClusterEngine:
    """Highlight candidate assembly and ranking engine."""

    def __init__(self, config: ClusterConfig | None = None) -> None:
        self.config = config or ClusterConfig()

    def cluster_events(
        self,
        events: list[VisualDetectionEvent],
        total_duration: float,
        video_id: str = "video_default",
        media_path: Path | str | None = None,
        audio_windows: list[AudioCandidateWindow] | None = None,
    ) -> list[HighlightCandidate]:
        """
        Cluster visual events into padded, duration-clamped highlight candidates.
        """
        if not events:
            return []

        # Sort events chronologically
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # 1. Chain events within merge gap
        clusters: list[list[VisualDetectionEvent]] = []
        current_cluster: list[VisualDetectionEvent] = [sorted_events[0]]

        for evt in sorted_events[1:]:
            prev = current_cluster[-1]
            if (evt.timestamp - prev.timestamp) <= self.config.event_merge_gap_seconds:
                current_cluster.append(evt)
            else:
                clusters.append(current_cluster)
                current_cluster = [evt]
        if current_cluster:
            clusters.append(current_cluster)

        candidates: list[HighlightCandidate] = []

        for cluster in clusters:
            first_time = cluster[0].timestamp
            last_time = cluster[-1].timestamp

            # 2. Apply cinematic padding
            raw_start = max(0.0, first_time - self.config.pre_roll_seconds)
            raw_end = min(total_duration, last_time + self.config.post_roll_seconds)
            dur = raw_end - raw_start

            # 3. Enforce YouTube Shorts duration bounds [min_clip_duration, max_clip_duration]
            if dur < self.config.min_clip_duration:
                needed = self.config.min_clip_duration - dur
                # Bias expansion toward pre-roll (60%) for context/setup
                add_pre = needed * 0.60
                add_post = needed * 0.40

                start_t = max(0.0, raw_start - add_pre)
                end_t = min(total_duration, raw_end + add_post)

                # If clamped at either boundary, expand remaining in opposite direction
                if end_t - start_t < self.config.min_clip_duration:
                    if start_t == 0.0:
                        end_t = min(total_duration, self.config.min_clip_duration)
                    elif end_t == total_duration:
                        start_t = max(
                            0.0, total_duration - self.config.min_clip_duration
                        )
                dur = end_t - start_t
            elif dur > self.config.max_clip_duration:
                # Climax centering: center around the highest-scoring event in cluster
                peak_evt = max(cluster, key=lambda e: e.score_weight)
                half_max = self.config.max_clip_duration / 2.0
                start_t = max(0.0, peak_evt.timestamp - half_max)
                end_t = min(total_duration, start_t + self.config.max_clip_duration)
                if end_t - start_t < self.config.max_clip_duration and start_t > 0:
                    start_t = max(0.0, end_t - self.config.max_clip_duration)
                dur = end_t - start_t
            else:
                start_t = raw_start
                end_t = raw_end

            # 4. Determine peak event and aggregate stats
            peak_evt = max(cluster, key=lambda e: e.score_weight)
            peak_type = peak_evt.event_type
            peak_timestamp = peak_evt.timestamp

            # Aggregate kills
            total_kills = max((e.kill_count for e in cluster), default=1)
            # If multiple distinct KO events were chained, adjust kill count
            ko_events = [
                e
                for e in cluster
                if "ko" in e.event_type or e.event_type == "team_wipe"
            ]
            if len(ko_events) > 1 and total_kills < len(ko_events):
                total_kills = len(ko_events)

            is_team_wipe = any(e.event_type == "team_wipe" for e in cluster)
            has_ultimate = any(
                "ULTIMATE" in e.label.upper()
                or "SHUTDOWN" in e.label.upper()
                or e.event_type == "shutdown"
                for e in cluster
            )

            is_overtime = any("OVERTIME" in e.label.upper() for e in cluster)
            game_phase = (
                "overtime"
                if is_overtime
                else (
                    "clutch" if peak_evt.event_type == "objective_clutch" else "regular"
                )
            )

            # 5. Calculate dynamic composite score (0.0 to 1.0)
            overlapping_audio = 0.60
            if audio_windows:
                for aw in audio_windows:
                    if not (aw.end_seconds < start_t or aw.start_seconds > end_t):
                        overlapping_audio = max(overlapping_audio, aw.score)

            # Persistence factor: corroborated across >= 2 frames or multiple chained events
            is_corroborated = (
                any(getattr(e, "frame_count", 1) >= 2 for e in cluster)
                or len(cluster) >= 2
            )
            persistence_factor = 1.0 if is_corroborated else 0.50

            ocr_conf = peak_evt.confidence
            tier_weight = peak_evt.score_weight
            chain_bonus = min(0.05, max(0, len(cluster) - 1) * 0.02)

            composite = (
                (0.45 * tier_weight)
                + (0.25 * persistence_factor)
                + (0.15 * ocr_conf)
                + (0.15 * overlapping_audio)
                + chain_bonus
            )
            final_score = round(min(1.0, max(0.50, composite)), 2)

            # Generate unique deterministic candidate ID
            cid_hash = hashlib.md5(
                f"{video_id}_{start_t:.1f}_{end_t:.1f}_{peak_type}".encode()
            ).hexdigest()[:6]
            candidate_id = f"cand_mvr_{cid_hash}"

            triggers = [
                TriggerEvent(
                    time=round(e.timestamp, 2),
                    label=e.label,
                    roi_name=e.roi_name,
                    confidence=e.confidence,
                )
                for e in cluster
            ]

            # Climax boundaries & streak milestone detection
            climax_start = round(first_time, 2)
            climax_end = round(last_time, 2)

            detected_streak = None
            for e in cluster:
                if getattr(e, "streak_count", None):
                    detected_streak = e.streak_count
                    break
                if "PLAYER KO STREAK" in e.label.upper():
                    m_st = re.search(r"(\d+)\s*PLAYER", e.label.upper())
                    if m_st:
                        detected_streak = int(m_st.group(1))
                        break

            details = HighlightDetails(
                kill_count=total_kills,
                streak_count=detected_streak,
                climax_start_seconds=climax_start,
                climax_end_seconds=climax_end,
                has_ultimate=has_ultimate,
                is_team_wipe=is_team_wipe,
                game_phase=game_phase,
                trigger_events=triggers,
            )

            # 6. Generate thumbnail if media path is available
            thumb_path_str: str | None = None
            thumb_url_str: str | None = None
            if media_path and self.config.generate_thumbnails:
                try:
                    thumb_dest = (
                        Path(self.config.thumbnails_dir) / candidate_id / "thumb.jpg"
                    )
                    extract_thumbnail_frame(media_path, peak_timestamp, thumb_dest)
                    thumb_path_str = str(thumb_dest.resolve())
                    thumb_url_str = (
                        f"/api/v1/videos/{video_id}/highlights/{candidate_id}/thumb.jpg"
                    )
                except Exception as t_err:
                    logger.warning(
                        "Could not extract thumbnail for %s: %s", candidate_id, t_err
                    )

            title = generate_suggested_title(
                event_type=peak_type,
                kill_count=total_kills,
                game_phase=game_phase,
                is_team_wipe=is_team_wipe,
                streak_count=detected_streak,
            )
            tags = generate_suggested_tags(peak_type, game_phase=game_phase)

            candidates.append(
                HighlightCandidate(
                    candidate_id=candidate_id,
                    video_id=video_id,
                    start_seconds=round(start_t, 2),
                    end_seconds=round(end_t, 2),
                    duration_seconds=round(dur, 2),
                    score=final_score,
                    event_type=peak_type,
                    game="Marvel Rivals",
                    details=details,
                    thumbnail_url=thumb_url_str,
                    thumbnail_path=thumb_path_str,
                    peak_timestamp=round(peak_timestamp, 2),
                    suggested_title=title,
                    suggested_tags=tags,
                )
            )

        # 7. Deduplicate overlapping candidate clips (retain higher score)
        return self._deduplicate_candidates(candidates)

    def _deduplicate_candidates(
        self, candidates: list[HighlightCandidate]
    ) -> list[HighlightCandidate]:
        """Merge or prune overlapping candidate clips to produce distinct highlights."""
        if len(candidates) <= 1:
            return candidates

        # Sort by start timestamp
        candidates.sort(key=lambda c: c.start_seconds)
        deduped: list[HighlightCandidate] = []

        for cand in candidates:
            if not deduped:
                deduped.append(cand)
                continue

            prev = deduped[-1]
            overlap_duration = prev.end_seconds - cand.start_seconds
            # If overlapping by more than 40% of either clip
            if overlap_duration > 0 and (
                overlap_duration / prev.duration_seconds > 0.40
                or overlap_duration / cand.duration_seconds > 0.40
            ):
                # Keep the one with the higher score and richer kill count
                if cand.score > prev.score or (
                    cand.score == prev.score
                    and cand.details.kill_count > prev.details.kill_count
                ):
                    deduped[-1] = cand
            else:
                deduped.append(cand)

        # Sort final output by score descending (highest-impact highlights first)
        deduped.sort(key=lambda c: c.score, reverse=True)
        return deduped

    def assemble_candidates(
        self,
        video_id: str,
        media_path: Path | str,
        visual_matches: BatchVisualMatchResult | None = None,
        audio_windows: list[AudioCandidateWindow] | None = None,
        total_duration: float | None = None,
    ) -> list[HighlightCandidate]:
        """
        Assemble final ranked highlight candidates combining visual events and audio cues.
        """
        path = Path(media_path).resolve()
        if total_duration is None:
            probe = probe_media(path)
            total_duration = probe.duration

        all_visual_events: list[VisualDetectionEvent] = []
        if visual_matches:
            for w in visual_matches.windows_matched:
                all_visual_events.extend(w.events)

        # Primary: Cluster visual events
        candidates = self.cluster_events(
            events=all_visual_events,
            total_duration=total_duration,
            video_id=video_id,
            media_path=path,
            audio_windows=audio_windows,
        )

        # Secondary: If audio candidate windows exist with no visual overlap, include top action windows
        if audio_windows:
            for aw in audio_windows:
                # Check if audio window overlaps with an existing visual candidate
                overlaps = any(
                    not (
                        aw.end_seconds < c.start_seconds
                        or aw.start_seconds > c.end_seconds
                    )
                    for c in candidates
                )
                if not overlaps and aw.score >= 0.75:
                    # Synthesize an audio excitement candidate
                    raw_start = max(
                        0.0, aw.start_seconds - self.config.pre_roll_seconds
                    )
                    raw_end = min(
                        total_duration, aw.end_seconds + self.config.post_roll_seconds
                    )
                    dur = raw_end - raw_start

                    if dur < self.config.min_clip_duration:
                        needed = self.config.min_clip_duration - dur
                        raw_start = max(0.0, raw_start - needed * 0.5)
                        raw_end = min(
                            total_duration, raw_start + self.config.min_clip_duration
                        )
                        dur = raw_end - raw_start

                    cid_hash = hashlib.md5(
                        f"{video_id}_{raw_start:.1f}_audio".encode()
                    ).hexdigest()[:6]
                    cid = f"cand_mvr_{cid_hash}"
                    peak_t = round((aw.start_seconds + aw.end_seconds) / 2.0, 2)

                    thumb_path_str: str | None = None
                    thumb_url_str: str | None = None
                    if self.config.generate_thumbnails:
                        try:
                            thumb_dest = (
                                Path(self.config.thumbnails_dir) / cid / "thumb.jpg"
                            )
                            extract_thumbnail_frame(path, peak_t, thumb_dest)
                            thumb_path_str = str(thumb_dest.resolve())
                            thumb_url_str = (
                                f"/api/v1/videos/{video_id}/highlights/{cid}/thumb.jpg"
                            )
                        except Exception:
                            pass

                    candidates.append(
                        HighlightCandidate(
                            candidate_id=cid,
                            video_id=video_id,
                            start_seconds=round(raw_start, 2),
                            end_seconds=round(raw_end, 2),
                            duration_seconds=round(dur, 2),
                            score=round(aw.score * 0.75, 2),
                            event_type="high_energy_action",
                            game="Marvel Rivals",
                            details=HighlightDetails(
                                kill_count=1,
                                has_ultimate=False,
                                is_team_wipe=False,
                                game_phase="regular",
                                trigger_events=[
                                    TriggerEvent(
                                        time=peak_t,
                                        label="High Energy Team Fight",
                                        roi_name="audio",
                                    )
                                ],
                            ),
                            thumbnail_url=thumb_url_str,
                            thumbnail_path=thumb_path_str,
                            peak_timestamp=peak_t,
                            suggested_title="Intense Team Fight Action! 🔥 #MarvelRivals",
                            suggested_tags=[
                                "MarvelRivals",
                                "Gaming",
                                "Shorts",
                                "TeamFight",
                                "Gameplay",
                            ],
                        )
                    )

        # Sort all candidates by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates


def cluster_highlight_candidates(
    video_id: str,
    media_path: Path | str,
    visual_matches: BatchVisualMatchResult | None = None,
    audio_windows: list[AudioCandidateWindow] | None = None,
    total_duration: float | None = None,
    config: ClusterConfig | None = None,
) -> list[HighlightCandidate]:
    """Convenience function to assemble and rank highlight candidates."""
    engine = ClusterEngine(config=config)
    return engine.assemble_candidates(
        video_id=video_id,
        media_path=media_path,
        visual_matches=visual_matches,
        audio_windows=audio_windows,
        total_duration=total_duration,
    )
