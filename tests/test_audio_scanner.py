"""Automated tests for Rapid Audio Excitement & Silence Scanner (ebur128 + Peak Energy)."""

import json
import subprocess
from pathlib import Path

import pytest

from app.services.highlight.audio_scanner import (
    AudioEnergyScanner,
    AudioScannerConfig,
    AudioScanResult,
    calculate_percentile,
    scan_audio_energy,
)


@pytest.fixture(scope="session")
def audio_test_assets(tmp_path_factory) -> dict[str, Path]:
    """Generate synthetic audio and video test assets using FFmpeg."""
    temp_dir = tmp_path_factory.mktemp("audio_scanner_assets")

    # 1. Uniform 3s sine tone (440Hz, -18 dBFS)
    pure_sine_path = temp_dir / "pure_sine.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:a",
            "pcm_s16le",
            str(pure_sine_path),
        ],
        check=True,
        capture_output=True,
    )

    # 2. 10s audio with burst: 2s silence, 5s loud tone (2s-7s), 3s silence
    burst_audio_path = temp_dir / "burst_action.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc=exprs=if(between(t\,2\,7)\,0.5*sin(2*PI*1000*t)\,0):d=10",
            "-c:a",
            "pcm_s16le",
            str(burst_audio_path),
        ],
        check=True,
        capture_output=True,
    )

    # 3. 16s audio with two distinct bursts: (2s-5s) and (11s-14s)
    two_bursts_path = temp_dir / "two_bursts.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc=exprs=if(between(t\,2\,5)+between(t\,11\,14)\,0.5*sin(2*PI*1000*t)\,0):d=16",
            "-c:a",
            "pcm_s16le",
            str(two_bursts_path),
        ],
        check=True,
        capture_output=True,
    )

    # 4. 9s audio with two bursts close together: (1s-3s) and (4s-6s) [1s gap]
    close_bursts_path = temp_dir / "close_bursts.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc=exprs=if(between(t\,1\,3)+between(t\,4\,6)\,0.5*sin(2*PI*1000*t)\,0):d=9",
            "-c:a",
            "pcm_s16le",
            str(close_bursts_path),
        ],
        check=True,
        capture_output=True,
    )

    # 5. Completely silent 3s audio
    silent_audio_path = temp_dir / "pure_silence.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0:d=3",
            "-c:a",
            "pcm_s16le",
            str(silent_audio_path),
        ],
        check=True,
        capture_output=True,
    )

    # 6. Video file with NO audio stream
    no_audio_video_path = temp_dir / "no_audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=2:size=320x240:rate=25",
            "-c:v",
            "libx264",
            "-an",
            str(no_audio_video_path),
        ],
        check=True,
        capture_output=True,
    )

    # 7. Complete MP4 video with video and audio streams
    video_with_audio_path = temp_dir / "video_with_audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=4:size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800:duration=4",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(video_with_audio_path),
        ],
        check=True,
        capture_output=True,
    )

    return {
        "pure_sine": pure_sine_path,
        "burst_audio": burst_audio_path,
        "two_bursts": two_bursts_path,
        "close_bursts": close_bursts_path,
        "pure_silence": silent_audio_path,
        "no_audio_video": no_audio_video_path,
        "video_with_audio": video_with_audio_path,
    }


def test_calculate_percentile_helper():
    """Verify linear percentile interpolation handles edge cases correctly."""
    assert calculate_percentile([], 50.0) == 0.0
    assert calculate_percentile([10.0], 50.0) == 10.0
    assert calculate_percentile([10.0, 20.0, 30.0], 50.0) == 20.0
    assert calculate_percentile([0.0, 100.0], 25.0) == 25.0
    assert calculate_percentile([0.0, 100.0], 75.0) == 75.0


def test_audio_scanner_pure_sine(audio_test_assets):
    """Test scanning a uniform sine wave audio file."""
    result = scan_audio_energy(audio_test_assets["pure_sine"])

    assert isinstance(result, AudioScanResult)
    assert result.has_audio is True
    assert result.duration_seconds >= 2.8
    assert result.total_buckets >= 5
    assert result.silent_buckets_count == 0
    assert result.processing_speed_ratio > 30.0
    assert len(result.candidate_windows) >= 1
    assert result.candidate_windows[0].score >= 0.35
    assert result.candidate_windows[0].peak_lufs > -30.0


def test_audio_scanner_silence_pruning(audio_test_assets):
    """Test that silence before and after an action burst is pruned."""
    result = scan_audio_energy(audio_test_assets["burst_audio"])

    assert result.has_audio is True
    assert result.duration_seconds >= 9.8
    # Silence at 0-2s and 7-10s should yield silent buckets
    assert result.silent_buckets_count >= 8
    assert len(result.candidate_windows) == 1

    window = result.candidate_windows[0]
    # Burst was from 2.0s to 7.0s
    assert 1.5 <= window.start_seconds <= 2.5
    assert 6.5 <= window.end_seconds <= 7.5
    assert 4.0 <= window.duration_seconds <= 5.5
    assert window.score >= 0.80


def test_audio_scanner_multiple_windows(audio_test_assets):
    """Test detecting two distinct separated action windows."""
    config = AudioScannerConfig(
        merge_gap_seconds=3.0,
        min_window_duration=2.5,
    )
    result = scan_audio_energy(audio_test_assets["two_bursts"], config=config)

    assert result.has_audio is True
    assert len(result.candidate_windows) == 2

    w1, w2 = result.candidate_windows
    # First burst around 2s - 5s
    assert 1.5 <= w1.start_seconds <= 2.5
    assert 4.5 <= w1.end_seconds <= 5.5
    # Second burst around 11s - 14s
    assert 10.5 <= w2.start_seconds <= 11.5
    assert 13.5 <= w2.end_seconds <= 14.5


def test_audio_scanner_merge_gap(audio_test_assets):
    """Test merging two bursts separated by a short lull (1s)."""
    # merge_gap_seconds = 3.0 should bridge the 1s lull
    config = AudioScannerConfig(
        merge_gap_seconds=3.0,
        min_window_duration=3.0,
    )
    result = scan_audio_energy(audio_test_assets["close_bursts"], config=config)

    assert result.has_audio is True
    # Two bursts (1-3s and 4-6s) should merge into a single continuous window
    assert len(result.candidate_windows) == 1
    w = result.candidate_windows[0]
    assert 0.5 <= w.start_seconds <= 1.5
    assert 5.5 <= w.end_seconds <= 6.5


def test_audio_scanner_pure_silence(audio_test_assets):
    """Test scanning a completely silent audio track produces 0 candidate windows."""
    result = scan_audio_energy(audio_test_assets["pure_silence"])

    assert result.has_audio is True
    assert result.duration_seconds >= 2.8
    assert result.silent_buckets_count == result.total_buckets
    assert result.exciting_buckets_count == 0
    assert result.candidate_windows == []


def test_audio_scanner_no_audio_stream(audio_test_assets):
    """Test scanning a video file without any audio track handles gracefully."""
    result = scan_audio_energy(audio_test_assets["no_audio_video"])

    assert result.has_audio is False
    assert result.candidate_windows == []
    assert result.timeline == []
    assert result.total_buckets == 0


def test_audio_scanner_mp4_container(audio_test_assets):
    """Test scanning an MP4 container file without decoding video."""
    result = scan_audio_energy(audio_test_assets["video_with_audio"])

    assert result.has_audio is True
    assert result.duration_seconds >= 3.8
    assert len(result.timeline) >= 7
    assert result.processing_speed_ratio > 30.0


def test_audio_scanner_nonexistent_file(tmp_path):
    """Test scanner raises FileNotFoundError for missing path."""
    scanner = AudioEnergyScanner()
    missing_file = tmp_path / "does_not_exist.mp4"
    with pytest.raises(FileNotFoundError):
        scanner.scan(missing_file)


def test_audio_scanner_progress_callback(audio_test_assets):
    """Test progress callback receives updates up to 100%."""
    progress_updates: list[tuple[float, str]] = []

    def on_progress(pct: float, msg: str) -> None:
        progress_updates.append((pct, msg))

    result = scan_audio_energy(
        audio_test_assets["burst_audio"], progress_callback=on_progress
    )

    assert result.has_audio is True
    assert len(progress_updates) >= 1
    assert progress_updates[-1][0] == 100.0


def test_audio_scanner_pydantic_serialization(audio_test_assets):
    """Test Pydantic JSON dump and load for scan results."""
    result = scan_audio_energy(audio_test_assets["burst_audio"])

    data = result.model_dump()
    assert isinstance(data, dict)
    assert data["has_audio"] is True
    assert "candidate_windows" in data
    assert "timeline" in data

    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["has_audio"] is True
    assert len(parsed["candidate_windows"]) == len(result.candidate_windows)
