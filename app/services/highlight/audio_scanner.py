"""Rapid Audio Excitement & Silence Scanner using FFmpeg ebur128 and peak energy.

Scans multi-hour gameplay VODs at high speed (~100-400x realtime) without decoding
video streams. Extracts 0.5-second loudness and peak energy buckets, computes
percentile excitement thresholds, prunes menu/loading/respawn silence, and
produces high-energy candidate action windows for downstream HUD analysis.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AudioBucket(BaseModel):
    """0.5-second time bucket representing audio energy and loudness."""

    timestamp: float = Field(..., description="Bucket start timestamp in seconds")
    duration: float = Field(default=0.5, description="Bucket duration in seconds")
    momentary_lufs: float = Field(
        ..., description="Power-averaged momentary loudness in LUFS"
    )
    peak_lufs: float = Field(..., description="Peak momentary loudness in LUFS")
    true_peak_db: float = Field(..., description="Peak true peak amplitude in dBFS")
    is_silent: bool = Field(
        default=False, description="True if energy is below silence threshold"
    )
    is_exciting: bool = Field(
        default=False, description="True if energy meets excitement threshold"
    )


class AudioCandidateWindow(BaseModel):
    """Candidate high-energy time window for further visual HUD analysis."""

    start_seconds: float = Field(..., description="Window start timestamp in seconds")
    end_seconds: float = Field(..., description="Window end timestamp in seconds")
    duration_seconds: float = Field(..., description="Window duration in seconds")
    mean_lufs: float = Field(..., description="Mean loudness across window in LUFS")
    peak_lufs: float = Field(..., description="Peak loudness across window in LUFS")
    peak_true_peak_db: float = Field(
        ..., description="Highest true peak amplitude in dBFS"
    )
    score: float = Field(
        ..., description="Normalized energy excitement score between 0.0 and 1.0"
    )
    bucket_count: int = Field(
        default=0, description="Number of audio buckets within window"
    )


class AudioScannerConfig(BaseModel):
    """Configuration for audio energy scanning and action window detection."""

    bucket_size_seconds: float = Field(
        default=0.5, description="Bucket interval in seconds (default 0.5s)"
    )
    silence_threshold_lufs: float = Field(
        default=-30.0,
        description="Loudness below this LUFS is considered silence (pruned)",
    )
    excitement_percentile: float = Field(
        default=75.0,
        description="Percentile threshold among active gameplay buckets (top 25%)",
    )
    min_excitement_lufs: float = Field(
        default=-26.0,
        description="Minimum floor for excitement threshold to prevent quiet hum detection",
    )
    min_window_duration: float = Field(
        default=3.0,
        description="Minimum duration in seconds for a candidate action window",
    )
    merge_gap_seconds: float = Field(
        default=3.0,
        description="Merge action segments separated by less than this interval",
    )
    max_window_duration: float = Field(
        default=180.0,
        description="Maximum raw candidate window duration before downstream clustering",
    )
    expand_short_windows: bool = Field(
        default=True,
        description="If True, expands high-energy spikes shorter than min_window_duration",
    )
    audio_stream_index: int = Field(
        default=0, description="Audio stream index to analyze (default 0)"
    )


class AudioScanResult(BaseModel):
    """Complete results from rapid audio excitement pass."""

    file_path: str = Field(..., description="Analyzed media file path")
    duration_seconds: float = Field(..., description="Total media duration in seconds")
    has_audio: bool = Field(
        ..., description="True if a valid audio stream was detected and analyzed"
    )
    silence_threshold_lufs: float = Field(
        ..., description="Applied silence threshold in LUFS"
    )
    excitement_threshold_lufs: float = Field(
        ..., description="Computed dynamic excitement threshold in LUFS"
    )
    total_buckets: int = Field(default=0, description="Total buckets analyzed")
    silent_buckets_count: int = Field(
        default=0, description="Number of silent buckets pruned"
    )
    exciting_buckets_count: int = Field(
        default=0, description="Number of buckets exceeding excitement threshold"
    )
    candidate_windows: list[AudioCandidateWindow] = Field(
        default_factory=list,
        description="Detected high-energy action candidate windows",
    )
    timeline: list[AudioBucket] = Field(
        default_factory=list, description="Chronological audio bucket timeline"
    )
    scan_duration_seconds: float = Field(
        default=0.0, description="Wall-clock time taken to perform scan in seconds"
    )
    processing_speed_ratio: float = Field(
        default=0.0, description="Scan speed multiple relative to real-time (e.g. 150x)"
    )


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile using linear interpolation without external dependencies."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    floor_k = math.floor(k)
    ceil_k = math.ceil(k)
    if floor_k == ceil_k:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(floor_k)] * (ceil_k - k)
    d1 = sorted_vals[int(ceil_k)] * (k - floor_k)
    return d0 + d1


def probe_audio_stream(media_path: Path) -> tuple[bool, float]:
    """Inspect media file for audio streams and duration via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_type,codec_name",
        "-of",
        "json",
        str(media_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        format_info = data.get("format", {})
        duration = float(format_info.get("duration") or 0.0)
        streams = data.get("streams", [])
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        return has_audio, duration
    except Exception as e:
        logger.warning("ffprobe audio inspection failed on %s: %s", media_path, e)
        return False, 0.0


class AudioEnergyScanner:
    """High-speed audio energy and excitement scanner."""

    def __init__(self, config: AudioScannerConfig | None = None) -> None:
        self.config = config or AudioScannerConfig()

    def scan(
        self,
        media_path: Path | str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> AudioScanResult:
        """
        Scan media file for audio loudness and peak energy timeline.

        Returns an AudioScanResult containing 0.5s buckets and candidate action windows.
        """
        path = Path(media_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        start_time = time.perf_counter()

        # Step 1: Probe for audio stream and total duration
        has_audio, probed_duration = probe_audio_stream(path)
        if not has_audio:
            logger.info("Media file %s contains no audio streams; skipping scan.", path)
            return AudioScanResult(
                file_path=str(path),
                duration_seconds=round(probed_duration, 2),
                has_audio=False,
                silence_threshold_lufs=self.config.silence_threshold_lufs,
                excitement_threshold_lufs=self.config.min_excitement_lufs,
                total_buckets=0,
                silent_buckets_count=0,
                exciting_buckets_count=0,
                candidate_windows=[],
                timeline=[],
                scan_duration_seconds=round(time.perf_counter() - start_time, 3),
                processing_speed_ratio=0.0,
            )

        # Step 2: Build FFmpeg command for metadata extraction
        # -vn skips video decoding entirely, achieving 100x+ speeds
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            f"0:a:{self.config.audio_stream_index}",
            "-vn",
            "-filter:a",
            "ebur128=metadata=1:peak=true,ametadata=print:file=-",
            "-f",
            "null",
            "-",
        ]

        logger.debug("Executing audio scanner: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stderr_output: list[str] = []

        def _drain_stderr() -> None:
            if proc.stderr:
                stderr_output.append(proc.stderr.read())

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        bucket_size = self.config.bucket_size_seconds
        # Mapping: bucket_index -> list of (momentary_lufs, true_peak_linear)
        bucket_samples: dict[int, list[tuple[float, float]]] = defaultdict(list)

        current_time: float | None = None
        current_m: float | None = None
        current_tp: float = 0.0
        max_time_observed: float = 0.0
        last_progress_pct = 0.0

        try:
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue

                    if "pts_time:" in line:
                        # Flush previous sample if valid
                        if current_time is not None and current_m is not None:
                            b_idx = int(current_time // bucket_size)
                            bucket_samples[b_idx].append((current_m, current_tp))
                            current_m = None
                            current_tp = 0.0

                        try:
                            time_token = (
                                line.split("pts_time:", 1)[1].strip().split()[0]
                            )
                            current_time = float(time_token)
                            if current_time > max_time_observed:
                                max_time_observed = current_time

                            if (
                                progress_callback
                                and probed_duration > 0
                                and current_time - last_progress_pct
                                >= probed_duration * 0.10
                            ):
                                pct = min(
                                    95.0,
                                    round((current_time / probed_duration) * 100.0, 1),
                                )
                                progress_callback(
                                    pct, f"Scanning audio excitement ({int(pct)}%)"
                                )
                                last_progress_pct = current_time
                        except ValueError, IndexError:
                            current_time = None

                    elif line.startswith("lavfi.r128.M="):
                        try:
                            val = float(line.split("=", 1)[1].strip())
                            if math.isinf(val) or val < -120.0 or math.isnan(val):
                                val = -120.0
                            current_m = val
                        except ValueError:
                            current_m = -120.0

                    elif line.startswith("lavfi.r128.true_peak="):
                        try:
                            tp_val = float(line.split("=", 1)[1].strip())
                            current_tp = (
                                max(0.0, tp_val) if not math.isnan(tp_val) else 0.0
                            )
                        except ValueError:
                            current_tp = 0.0

                # Flush trailing sample
                if current_time is not None and current_m is not None:
                    b_idx = int(current_time // bucket_size)
                    bucket_samples[b_idx].append((current_m, current_tp))

            proc.wait()
        except BaseException:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
                    proc.wait()
            raise
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass
            err_thread.join(timeout=2.0)

        err_msg = "".join(stderr_output).strip()
        if proc.returncode != 0:
            logger.error("FFmpeg audio scanner failed on %s: %s", path, err_msg)
            raise RuntimeError(f"FFmpeg audio scanning failed on {path}:\n{err_msg}")

        effective_duration = max(probed_duration, max_time_observed)
        if effective_duration <= 0.0 and bucket_samples:
            effective_duration = (max(bucket_samples.keys()) + 1) * bucket_size

        # Step 3: Compute aggregated buckets
        num_buckets = (
            max(1, math.ceil(effective_duration / bucket_size))
            if effective_duration > 0
            else 0
        )
        timeline: list[AudioBucket] = []

        for b_idx in range(num_buckets):
            b_start = round(b_idx * bucket_size, 3)
            samples = bucket_samples.get(b_idx, [])

            if samples:
                m_vals = [s[0] for s in samples]
                tp_vals = [s[1] for s in samples]

                # Acoustic power-averaged LUFS: 10 * log10(mean(10^(m/10)))
                powers = [10.0 ** (m / 10.0) for m in m_vals if m > -120.0]
                if powers:
                    mean_power = sum(powers) / len(m_vals)
                    mean_lufs = round(10.0 * math.log10(max(mean_power, 1e-12)), 2)
                else:
                    mean_lufs = -120.0

                peak_lufs = round(max(m_vals), 2)

                peak_tp_linear = max(tp_vals) if tp_vals else 0.0
                if peak_tp_linear > 0.0:
                    tp_db = round(20.0 * math.log10(peak_tp_linear), 2)
                    tp_db = max(-120.0, min(0.0, tp_db))
                else:
                    tp_db = -120.0
            else:
                mean_lufs = -120.0
                peak_lufs = -120.0
                tp_db = -120.0

            is_silent = mean_lufs < self.config.silence_threshold_lufs

            timeline.append(
                AudioBucket(
                    timestamp=b_start,
                    duration=bucket_size,
                    momentary_lufs=mean_lufs,
                    peak_lufs=peak_lufs,
                    true_peak_db=tp_db,
                    is_silent=is_silent,
                    is_exciting=False,  # Updated after calculating dynamic threshold
                )
            )

        # Step 4: Calculate dynamic excitement threshold
        active_buckets = [b for b in timeline if not b.is_silent]
        if active_buckets:
            active_lufs = [b.momentary_lufs for b in active_buckets]
            percentile_thresh = calculate_percentile(
                active_lufs, self.config.excitement_percentile
            )
            excitement_threshold_lufs = round(
                max(self.config.min_excitement_lufs, percentile_thresh), 2
            )
        else:
            excitement_threshold_lufs = self.config.min_excitement_lufs

        # Step 5: Mark exciting buckets
        silent_count = 0
        exciting_count = 0
        for b in timeline:
            if b.is_silent:
                silent_count += 1
            else:
                if b.momentary_lufs >= excitement_threshold_lufs:
                    b.is_exciting = True
                    exciting_count += 1

        # Step 6: Cluster contiguous exciting buckets into candidate windows
        candidate_spans: list[tuple[float, float, list[AudioBucket]]] = []
        current_span: list[AudioBucket] = []

        for b in timeline:
            if b.is_exciting:
                current_span.append(b)
            else:
                if current_span:
                    s_t = current_span[0].timestamp
                    e_t = current_span[-1].timestamp + current_span[-1].duration
                    candidate_spans.append((s_t, e_t, current_span))
                    current_span = []

        if current_span:
            s_t = current_span[0].timestamp
            e_t = current_span[-1].timestamp + current_span[-1].duration
            candidate_spans.append((s_t, e_t, current_span))

        # Merge segments separated by <= merge_gap_seconds
        merged_spans: list[tuple[float, float, list[AudioBucket]]] = []
        for s_t, e_t, span_b in candidate_spans:
            if not merged_spans:
                merged_spans.append((s_t, e_t, span_b))
                continue

            prev_s, prev_e, prev_b = merged_spans[-1]
            gap = s_t - prev_e
            if gap <= self.config.merge_gap_seconds:
                merged_spans[-1] = (prev_s, e_t, prev_b + span_b)
            else:
                merged_spans.append((s_t, e_t, span_b))

        # Filter by duration and assemble final candidate windows
        candidate_windows: list[AudioCandidateWindow] = []
        for s_t, e_t, span_b in merged_spans:
            dur = e_t - s_t
            if dur < self.config.min_window_duration:
                if self.config.expand_short_windows:
                    needed = self.config.min_window_duration - dur
                    s_t = max(0.0, s_t - needed / 2.0)
                    e_t = min(effective_duration, s_t + self.config.min_window_duration)
                    dur = e_t - s_t
                else:
                    continue

            if dur > self.config.max_window_duration:
                e_t = s_t + self.config.max_window_duration
                dur = self.config.max_window_duration

            # Find all buckets intersecting [s_t, e_t]
            win_buckets = [
                b
                for b in timeline
                if b.timestamp >= (s_t - 0.01)
                and (b.timestamp + b.duration) <= (e_t + 0.01)
            ]
            if not win_buckets:
                win_buckets = span_b

            peak_l = max(b.peak_lufs for b in win_buckets)
            powers = [
                10.0 ** (b.momentary_lufs / 10.0)
                for b in win_buckets
                if b.momentary_lufs > -120.0
            ]
            mean_p = sum(powers) / len(powers) if powers else 0.0
            mean_l = (
                round(10.0 * math.log10(max(mean_p, 1e-12)), 2)
                if mean_p > 0
                else -120.0
            )
            peak_tp = max(b.true_peak_db for b in win_buckets)

            # Normalized score: relative excitement above silence threshold
            # Range: silence (-30) -> high intensity (-10)
            rel_mean = max(
                0.0,
                min(
                    1.0,
                    (mean_l - self.config.silence_threshold_lufs)
                    / (-12.0 - self.config.silence_threshold_lufs),
                ),
            )
            rel_peak = max(
                0.0,
                min(
                    1.0,
                    (peak_l - self.config.silence_threshold_lufs)
                    / (-6.0 - self.config.silence_threshold_lufs),
                ),
            )
            score = round(max(0.10, min(1.0, (0.4 * rel_mean) + (0.6 * rel_peak))), 3)

            candidate_windows.append(
                AudioCandidateWindow(
                    start_seconds=round(s_t, 3),
                    end_seconds=round(e_t, 3),
                    duration_seconds=round(dur, 3),
                    mean_lufs=mean_l,
                    peak_lufs=peak_l,
                    peak_true_peak_db=peak_tp,
                    score=score,
                    bucket_count=len(win_buckets),
                )
            )

        # Merge any windows that overlap following expansion
        final_windows: list[AudioCandidateWindow] = []
        for cw in candidate_windows:
            if not final_windows:
                final_windows.append(cw)
                continue
            prev = final_windows[-1]
            if cw.start_seconds <= prev.end_seconds:
                new_start = prev.start_seconds
                new_end = max(prev.end_seconds, cw.end_seconds)
                new_dur = round(new_end - new_start, 3)
                new_peak_lufs = max(prev.peak_lufs, cw.peak_lufs)
                new_mean_lufs = round(max(prev.mean_lufs, cw.mean_lufs), 2)
                new_tp_db = max(prev.peak_true_peak_db, cw.peak_true_peak_db)
                new_score = round(max(prev.score, cw.score), 3)
                final_windows[-1] = AudioCandidateWindow(
                    start_seconds=new_start,
                    end_seconds=new_end,
                    duration_seconds=new_dur,
                    mean_lufs=new_mean_lufs,
                    peak_lufs=new_peak_lufs,
                    peak_true_peak_db=new_tp_db,
                    score=new_score,
                    bucket_count=prev.bucket_count + cw.bucket_count,
                )
            else:
                final_windows.append(cw)

        total_scan_time = round(time.perf_counter() - start_time, 3)
        speed_ratio = (
            round(effective_duration / total_scan_time, 1)
            if total_scan_time > 0
            else 0.0
        )

        if progress_callback:
            progress_callback(100.0, "Audio energy scan completed")

        logger.info(
            "Audio energy scan completed on %s: duration=%.1fs, scan_time=%.2fs (%.1fx realtime), %d candidate windows detected.",
            path.name,
            effective_duration,
            total_scan_time,
            speed_ratio,
            len(final_windows),
        )

        return AudioScanResult(
            file_path=str(path),
            duration_seconds=round(effective_duration, 2),
            has_audio=True,
            silence_threshold_lufs=self.config.silence_threshold_lufs,
            excitement_threshold_lufs=excitement_threshold_lufs,
            total_buckets=len(timeline),
            silent_buckets_count=silent_count,
            exciting_buckets_count=exciting_count,
            candidate_windows=final_windows,
            timeline=timeline,
            scan_duration_seconds=total_scan_time,
            processing_speed_ratio=speed_ratio,
        )


def scan_audio_energy(
    media_path: Path | str,
    config: AudioScannerConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> AudioScanResult:
    """Convenience function to scan a media file for audio energy."""
    scanner = AudioEnergyScanner(config=config)
    return scanner.scan(media_path=media_path, progress_callback=progress_callback)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m app.services.highlight.audio_scanner <video_or_audio_path>"
        )
        sys.exit(1)

    target_path = Path(sys.argv[1])
    print(f"Scanning audio excitement on {target_path}...")
    res = scan_audio_energy(target_path)
    print("\n--- Scan Summary ---")
    print(
        f"Duration: {res.duration_seconds}s | Scan Time: {res.scan_duration_seconds}s ({res.processing_speed_ratio}x speed)"
    )
    print(
        f"Silence Threshold: {res.silence_threshold_lufs} LUFS | Excitement Threshold: {res.excitement_threshold_lufs} LUFS"
    )
    print(
        f"Buckets: {res.total_buckets} total, {res.silent_buckets_count} silent, {res.exciting_buckets_count} exciting"
    )
    print(f"\nCandidate Action Windows ({len(res.candidate_windows)} found):")
    for i, w in enumerate(res.candidate_windows, 1):
        print(
            f"  [{i}] {w.start_seconds:6.1f}s -> {w.end_seconds:6.1f}s "
            f"(dur: {w.duration_seconds:4.1f}s, mean: {w.mean_lufs:5.1f} LUFS, "
            f"peak: {w.peak_lufs:5.1f} LUFS, score: {w.score:.2f})"
        )
