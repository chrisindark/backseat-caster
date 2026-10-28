"""Speech-to-Text (STT) and natural dialogue boundary snapping for highlight mining.

Ensures candidate clip boundaries snap to natural pauses in speech or audio rather
than cutting off mid-sentence or mid-word, providing broadcast-quality pacing
for short-form video formats.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Regular expressions for parsing FFmpeg silencedetect output
_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9\.]+)")
_SILENCE_END_RE = re.compile(
    r"silence_end:\s*([0-9\.]+)\s*\|\s*silence_duration:\s*([0-9\.]+)"
)

# Common viral/excitement dialogue keywords for gaming & conversational highlights
GAMING_SPEECH_KEYWORDS: dict[str, float] = {
    "crown": 0.25,
    "winner": 0.25,
    "win": 0.15,
    "qualified": 0.20,
    "qualify": 0.15,
    "clutch": 0.20,
    "first place": 0.20,
    "let's go": 0.15,
    "lets go": 0.15,
    "no way": 0.15,
    "oh my god": 0.15,
    "insane": 0.15,
    "what": 0.10,
    "grief": 0.15,
    "fall off": 0.15,
    "slime": 0.15,
    "penta": 0.25,
    "team wipe": 0.25,
}


def detect_silence_intervals(
    media_path: Path,
    start_seconds: float,
    duration_seconds: float,
    noise_db: float = -30.0,
    min_silence_duration: float = 0.20,
) -> list[tuple[float, float]]:
    """Detect intervals of silence within an audio window using FFmpeg silencedetect.

    Args:
        media_path: Path to the audio/video file.
        start_seconds: Window seek start time.
        duration_seconds: Duration of window to inspect.
        noise_db: Noise floor threshold in dB (default -30dB).
        min_silence_duration: Minimum silence length in seconds to count as pause.

    Returns:
        List of (silence_start, silence_end) absolute timestamps relative to media start.
    """
    if duration_seconds <= 0.0 or not media_path.exists():
        return []

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        f"{max(0.0, start_seconds):.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(media_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
        "-f",
        "null",
        "-",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=8.0,
        )
        stderr = proc.stderr or ""
    except Exception as e:
        logger.debug("Failed running silencedetect on %s: %s", media_path, e)
        return []

    offset = max(0.0, start_seconds)
    intervals: list[tuple[float, float]] = []
    current_start: float | None = None

    for line in stderr.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            current_start = offset + float(start_match.group(1))
            continue

        end_match = _SILENCE_END_RE.search(line)
        if end_match:
            end_val = offset + float(end_match.group(1))
            start_val = (
                current_start
                if current_start is not None
                else end_val - float(end_match.group(2))
            )
            intervals.append((start_val, end_val))
            current_start = None

    return intervals


def snap_to_speech_boundaries(
    media_path: Path,
    start_seconds: float,
    end_seconds: float,
    min_duration: float = 18.0,
    max_duration: float = 55.0,
    search_window: float = 3.5,
) -> tuple[float, float, float]:
    """Snap candidate start and end points to natural sentence/speech pauses.

    Looks for silence valleys immediately preceding the raw start and immediately
    following the raw end, ensuring clips do not start or terminate mid-utterance.

    Returns:
        (snapped_start, snapped_end, snapped_duration)
    """
    raw_dur = end_seconds - start_seconds
    if raw_dur <= 0.0 or not media_path.exists():
        return start_seconds, end_seconds, max(0.0, raw_dur)

    # 1. Inspect window around start
    start_search_start = max(0.0, start_seconds - search_window)
    start_search_dur = search_window * 2.0
    start_silences = detect_silence_intervals(
        media_path=media_path,
        start_seconds=start_search_start,
        duration_seconds=start_search_dur,
    )

    snapped_start = start_seconds
    if start_silences:
        # Find silence interval whose end is closest to raw start (speech beginning)
        best_diff = float("inf")
        for _s_start, s_end in start_silences:
            # We prefer snapping to the end of silence where speech/reaction begins
            diff = abs(s_end - start_seconds)
            if diff < best_diff and s_end <= start_seconds + 1.5:
                best_diff = diff
                snapped_start = s_end

    # 2. Inspect window around end
    end_search_start = max(0.0, end_seconds - search_window)
    end_search_dur = search_window * 2.0
    end_silences = detect_silence_intervals(
        media_path=media_path,
        start_seconds=end_search_start,
        duration_seconds=end_search_dur,
    )

    snapped_end = end_seconds
    if end_silences:
        # Find silence interval whose start is closest to raw end (speech ending)
        best_diff = float("inf")
        for s_start, _s_end in end_silences:
            diff = abs(s_start - end_seconds)
            if diff < best_diff and s_start >= end_seconds - 1.5:
                best_diff = diff
                snapped_end = s_start

    # 3. Enforce duration constraints
    dur = snapped_end - snapped_start
    if dur < min_duration:
        needed = min_duration - dur
        snapped_start = max(0.0, snapped_start - needed * 0.5)
        snapped_end = snapped_start + min_duration
        dur = min_duration

    if dur > max_duration:
        snapped_end = snapped_start + max_duration
        dur = max_duration

    return round(snapped_start, 2), round(snapped_end, 2), round(dur, 2)
