"""Tests for Milestone 3: Event-aware payoff and kill effects.

Tests:
1. Deterministic event extraction from highlight candidate metadata
2. Kill notification badge rasterisation (lower-third, upper-third, combo multipliers)
3. Punch-in zoom filter builder & multi-window activation
4. End-to-end synthetic render with punch-in and kill notifications
5. Frame extraction and inspection at event timestamps
6. Graceful degradation when detection events are absent
"""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.rendering.branding import render_kill_notification_png
from app.rendering.config import KillEffectsConfig, RenderConfig
from app.rendering.engine import RenderEngine
from app.rendering.filters import build_punch_in_filter
from app.services.channel_profile import extract_candidate_events


def test_extract_candidate_events():
    """Extracts deterministic relative event moments and chains combo multipliers."""
    details = {
        "trigger_events": [
            {"time": 10.5, "label": "Elimination", "confidence": 0.9},
            {"time": 13.0, "label": "TRIPLE KO", "confidence": 0.95},
        ],
        "killfeed_chain": {
            "rows": [
                {"timestamp": 10.6, "action": "elimination", "confidence": 0.85},
                {"timestamp": 11.8, "action": "elimination", "confidence": 0.88},
            ]
        },
    }

    # Clip window: 10.0s to 15.0s (5.0s total)
    events = extract_candidate_events(details, clip_start=10.0, clip_end=15.0)

    # 10.5 & 10.6 are deduplicated within 0.35s
    # Events should be: ~0.5s (combo 1), 1.8s (combo 2), 3.0s (combo 3)
    assert len(events) == 3
    assert events[0]["time"] == 0.5
    assert events[0]["combo"] == 1
    assert events[0]["label"] == "Elimination"

    assert events[1]["time"] == 1.8
    assert events[1]["combo"] == 2
    assert events[1]["label"] == "DOUBLE KO"

    assert events[2]["time"] == 3.0
    assert events[2]["combo"] == 3
    assert events[2]["label"] == "TRIPLE KO"


def test_extract_candidate_events_empty():
    """Returns empty list cleanly when candidate has no detection metadata."""
    assert extract_candidate_events({}, 0.0, 10.0) == []
    assert extract_candidate_events({"trigger_events": []}, 0.0, 10.0) == []


def test_render_kill_notification_badge(tmp_path: Path):
    """Notification badge produces an RGBA PNG placed in the lower-third, leaving reticle clear."""
    out_path = tmp_path / "kbadge_lower.png"
    result = render_kill_notification_png(
        out_path,
        size=(1080, 1920),
        label="DOUBLE KO",
        combo=2,
        position="lower_third",
    )
    assert result.exists()
    with Image.open(result) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
        bbox = img.getbbox()
        assert bbox is not None
        y0, y1 = bbox[1], bbox[3]
        # In 1920h: lower-third is around y=1380
        # Must be well below crosshair (y=960) and leave bottom margin clear
        assert y0 >= 1300
        assert y1 <= 1650


def test_render_kill_notification_badge_upper_third(tmp_path: Path):
    """Notification badge in upper-third is placed between header and crosshair."""
    out_path = tmp_path / "kbadge_upper.png"
    result = render_kill_notification_png(
        out_path,
        size=(1080, 1920),
        label="TEAM WIPE",
        combo=5,
        position="upper_third",
    )
    assert result.exists()
    with Image.open(result) as img:
        bbox = img.getbbox()
        assert bbox is not None
        y0, y1 = bbox[1], bbox[3]
        assert y0 >= 350
        assert y1 <= 700


def test_build_punch_in_filter():
    """Punch-in filter constructs valid crop and scale filtergraph with multi-window timing."""
    f_punch = build_punch_in_filter(
        input_label="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
        event_times=[1.5, 4.0],
        duration=0.30,
        scale=1.06,
    )
    assert "split=2" in f_punch
    assert "crop=" in f_punch
    assert "scale=1080:1920" in f_punch
    assert "between(t,1.500,1.800)+between(t,4.000,4.300)" in f_punch

    # Empty event times degrades cleanly to copy
    f_empty = build_punch_in_filter(
        input_label="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
        event_times=[],
    )
    assert "copy" in f_empty


@pytest.fixture
def synthetic_video_milestone3(tmp_path: Path) -> Path:
    """Generate an 8s synthetic 1280x720 video with test tone."""
    video_path = tmp_path / "gameplay_m3.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=8",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=8",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(video_path),
    ]
    subprocess.run(
        cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return video_path


def test_end_to_end_render_with_kill_effects(
    synthetic_video_milestone3: Path, tmp_path: Path
):
    """End-to-end clip render with punch-in zoom and kill notification badges."""
    out_dir = tmp_path / "renders" / "clip_m3_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    test_events = [
        {"time": 2.0, "label": "Elimination", "combo": 1},
        {"time": 5.0, "label": "DOUBLE KO", "combo": 2},
    ]

    config = RenderConfig(
        preferred_encoder="libx264",
        quality_preset="high",
        kill_effects=KillEffectsConfig(
            enabled=True,
            punch_in=True,
            punch_in_scale=1.06,
            punch_in_duration=0.30,
            kill_notification=True,
            kill_notification_duration=1.2,
            combo_counter=True,
            position="lower_third",
            events=test_events,
        ),
    )

    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_video_milestone3,
        start_seconds=0.0,
        duration_seconds=8.0,
        output_dir=out_dir,
        clip_id="test_m3_123",
        modes=["vertical_blur", "landscape"],
    )

    assert result.clip_id == "test_m3_123"
    assert "vertical_blur" in result.outputs

    # Verify manifest
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["kill_effects"]["enabled"] is True
    assert manifest["kill_effects"]["punch_in"] is True
    assert manifest["kill_effects"]["event_count"] == 2
    assert manifest["kill_effects"]["events"] == test_events

    # Frame inspection at t=2.1s (first kill active), t=3.5s (clean), t=5.1s (second kill active)
    vert_video = out_dir / "vertical_blur.mp4"
    assert vert_video.exists()

    f_ev1 = tmp_path / "frame_ev1.png"
    f_clean = tmp_path / "frame_clean.png"
    f_ev2 = tmp_path / "frame_ev2.png"

    for t_sec, f_path in [(2.1, f_ev1), (3.5, f_clean), (5.1, f_ev2)]:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t_sec:.1f}",
            "-i",
            str(vert_video),
            "-vframes",
            "1",
            str(f_path),
        ]
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        assert f_path.exists()
        with Image.open(f_path) as img:
            assert img.size == (1080, 1920)


def test_kill_effects_graceful_degradation_when_no_events(
    synthetic_video_milestone3: Path, tmp_path: Path
):
    """When kill_effects is enabled but events list is empty, render finishes cleanly without effects."""
    out_dir = tmp_path / "renders" / "clip_m3_no_events"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = RenderConfig(
        preferred_encoder="libx264",
        quality_preset="high",
        kill_effects=KillEffectsConfig(
            enabled=True,
            punch_in=True,
            kill_notification=True,
            events=[],  # No detected events
        ),
    )

    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_video_milestone3,
        start_seconds=0.0,
        duration_seconds=4.0,
        output_dir=out_dir,
        clip_id="test_m3_empty",
        modes=["vertical_blur"],
    )

    assert result.clip_id == "test_m3_empty"
    vert_video = out_dir / "vertical_blur.mp4"
    assert vert_video.exists()

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["kill_effects"]["enabled"] is False
    assert manifest["kill_effects"]["event_count"] == 0
