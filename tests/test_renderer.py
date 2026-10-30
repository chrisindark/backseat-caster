"""Unit and integration tests for BackseatCaster rendering engine."""

import json
import subprocess
from pathlib import Path

import pytest

from app.rendering.audio import build_audio_filter_graph
from app.rendering.config import RenderConfig, WatermarkConfig
from app.rendering.engine import RenderEngine
from app.rendering.filters import (
    build_landscape_filter,
    build_vertical_blur_filter,
    build_vertical_crop_filter,
    build_watermark_filter,
)
from app.rendering.probe import probe_media
from app.rendering.validator import ValidationError, validate_render_parameters


@pytest.fixture(scope="session")
def synthetic_assets(tmp_path_factory) -> dict:
    """Generate lightweight 3s synthetic video and 2s narration audio using FFmpeg."""
    temp_dir = tmp_path_factory.mktemp("synthetic_assets")
    video_path = temp_dir / "test_gameplay.mp4"
    silent_video_path = temp_dir / "test_silent.mp4"
    narration_path = temp_dir / "test_voiceover.wav"

    # 1. 3-second 1280x720 30fps video with 1000Hz sine audio
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=3:size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video_path),
        ],
        capture_output=True,
        check=True,
    )

    # 2. 3-second video WITHOUT audio stream
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=3:size=1280x720:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(silent_video_path),
        ],
        capture_output=True,
        check=True,
    )

    # 3. 2-second 440Hz narration audio
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:a",
            "pcm_s16le",
            str(narration_path),
        ],
        capture_output=True,
        check=True,
    )

    return {
        "video": video_path,
        "silent_video": silent_video_path,
        "narration": narration_path,
    }


def test_watermark_filter_positions():
    """The overlay builder scales relative to output and respects position."""
    filter_str = build_watermark_filter(
        watermark_input="3:v",
        main_input="v_out_0",
        output_label="v_wm_0",
        width=1080,
        height=1920,
        position="top_right",
        opacity=0.7,
        scale=0.2,
        margin=0.04,
    )
    assert "scale=216:-2" in filter_str
    assert "colorchannelmixer=aa=0.700" in filter_str
    assert "overlay=W-w-43:43" in filter_str


def test_watermark_overlay_renders(synthetic_assets, tmp_path):
    """A configured logo is composited into every requested output."""
    logo = tmp_path / "logo.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:d=1",
            "-frames:v",
            "1",
            str(logo),
        ],
        capture_output=True,
        check=True,
    )

    engine = RenderEngine(
        RenderConfig(
            watermark=WatermarkConfig(
                enabled=True,
                path=str(logo),
                position="bottom_right",
                opacity=0.8,
                scale=0.15,
            )
        )
    )
    out_dir = tmp_path / "wm_render"
    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=2.0,
        output_dir=out_dir,
        clip_id="wm_render",
        crop_preset="third_person",
        modes=["third_person", "landscape"],
    )

    assert result.watermark_applied is True
    assert (out_dir / "third_person.mp4").exists()
    assert (out_dir / "landscape.mp4").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["watermark"]["enabled"] is True


def test_probe_media(synthetic_assets):
    """Test ffprobe inspects duration, resolution, fps and audio correctly."""
    probe = probe_media(synthetic_assets["video"])
    assert probe.width == 1280
    assert probe.height == 720
    assert probe.fps == 30.0
    assert 2.9 <= probe.duration <= 3.1
    assert probe.has_audio is True
    assert probe.file_size_bytes > 0


def test_validation_bounds(synthetic_assets, tmp_path):
    """Test validation constraints on time range and bounds."""
    probe = probe_media(synthetic_assets["video"])

    # Valid parameters
    validate_render_parameters(
        probe, start_seconds=0.5, duration_seconds=1.5, output_dir=tmp_path
    )

    # Negative start
    with pytest.raises(ValidationError, match="Invalid start time"):
        validate_render_parameters(
            probe, start_seconds=-1.0, duration_seconds=1.0, output_dir=tmp_path
        )

    # Zero duration
    with pytest.raises(ValidationError, match="Invalid duration"):
        validate_render_parameters(
            probe, start_seconds=0.0, duration_seconds=0.0, output_dir=tmp_path
        )

    # Exceeds total duration
    with pytest.raises(ValidationError, match="exceeds source video duration"):
        validate_render_parameters(
            probe, start_seconds=2.0, duration_seconds=2.5, output_dir=tmp_path
        )


def test_validation_clamping(synthetic_assets, tmp_path):
    """Test that clamp_duration clamps duration to source video bounds safely."""
    probe = probe_media(synthetic_assets["video"])
    assert probe.duration == pytest.approx(3.0, abs=0.1)

    # Clamping from 1.0s with duration 100s -> effective 2.0s
    clamped_dur = validate_render_parameters(
        probe,
        start_seconds=1.0,
        duration_seconds=100.0,
        output_dir=tmp_path,
        clamp_duration=True,
    )
    assert clamped_dur == pytest.approx(2.0, abs=0.1)

    # Start time at or exceeding duration must still raise ValidationError
    with pytest.raises(ValidationError, match="exceeds source video duration"):
        validate_render_parameters(
            probe,
            start_seconds=3.5,
            duration_seconds=1.0,
            output_dir=tmp_path,
            clamp_duration=True,
        )

    # Remaining duration below min_duration threshold must raise ValidationError
    with pytest.raises(ValidationError, match="shorter than minimum allowable"):
        validate_render_parameters(
            probe,
            start_seconds=2.8,
            duration_seconds=1.0,
            output_dir=tmp_path,
            clamp_duration=True,
            min_duration=0.5,
        )


def test_validation_overwrite_protection(synthetic_assets, tmp_path):
    """Test that existing files prevent silent overwrite unless explicit flag is passed."""
    probe = probe_media(synthetic_assets["video"])
    out_dir = tmp_path / "test_clip"
    out_dir.mkdir()
    (out_dir / "landscape.mp4").write_text("existing")

    with pytest.raises(ValidationError, match="already contains rendered files"):
        validate_render_parameters(
            probe,
            start_seconds=0,
            duration_seconds=1,
            output_dir=out_dir,
            overwrite=False,
        )

    # Should succeed with overwrite=True
    validate_render_parameters(
        probe, start_seconds=0, duration_seconds=1, output_dir=out_dir, overwrite=True
    )

    # Test custom modes overwrite isolation:
    # out_dir has landscape.mp4, but we only request ["vertical_blur", "direct_crop"]
    validate_render_parameters(
        probe,
        start_seconds=0,
        duration_seconds=1,
        output_dir=out_dir,
        overwrite=False,
        modes=["vertical_blur", "direct_crop"],
    )

    # If requested modes include the existing "landscape", it should raise
    with pytest.raises(ValidationError, match="already contains rendered files"):
        validate_render_parameters(
            probe,
            start_seconds=0,
            duration_seconds=1,
            output_dir=out_dir,
            overwrite=False,
            modes=["landscape", "direct_crop"],
        )


def test_filters_generation():
    """Test filtergraph strings for landscape, vertical-blur, and vertical-crop."""
    land_f = build_landscape_filter(1920, 1080)
    assert "scale=1920:1080" in land_f
    assert "flags=lanczos" in land_f
    assert "pad=1920:1080" in land_f

    blur_f = build_vertical_blur_filter(1080, 1920, blur_sigma=25)
    assert "boxblur=25:5" in blur_f
    assert "split=2" in blur_f
    assert "overlay=" in blur_f

    # Third-person padded crop (33% blur padding -> 1280px foreground)
    crop_f_third_person = build_vertical_crop_filter(1080, 1920, blur_padding=0.3333)
    assert "crop=1080:1280" in crop_f_third_person
    assert "boxblur=25:5" in crop_f_third_person
    assert "overlay=" in crop_f_third_person

    # Direct 100% full-height center crop (0% blur)
    crop_f_direct = build_vertical_crop_filter(1080, 1920, blur_padding=0.0)
    assert "crop=1080:1920" in crop_f_direct
    assert "flags=lanczos" in crop_f_direct


def test_audio_filters_unducked_vs_ducked():
    """Verify pure game audio has no ducking, and narration mix has ducking + limiter."""
    # Mode 1: No narration -> No ducking, with loudnorm
    unducked_graph, label = build_audio_filter_graph(
        start_seconds=0,
        duration_seconds=5,
        has_source_audio=True,
        has_narration=False,
        normalize_audio=True,
    )
    assert "atrim=" in unducked_graph
    assert "volume=" not in unducked_graph  # Zero volume attenuation!
    assert "alimiter" not in unducked_graph
    assert "loudnorm=I=-14.0:TP=-1.5:LRA=11.0" in unducked_graph

    # Mode 2: With narration -> Ducking + Limiter + loudnorm
    ducked_graph, label = build_audio_filter_graph(
        start_seconds=0,
        duration_seconds=5,
        has_source_audio=True,
        has_narration=True,
        ducked_game_gain=0.30,
        narration_gain=1.0,
        normalize_audio=True,
    )
    assert "volume=0.30" in ducked_graph
    assert "amix=" in ducked_graph
    assert "alimiter=" in ducked_graph
    assert "loudnorm=I=-14.0:TP=-1.5:LRA=11.0" in ducked_graph


def test_audio_normalization_ebu_r128():
    """Verify EBU R128 loudness normalization toggles and custom LUFS targets."""
    # Disabled normalization
    off_graph, _ = build_audio_filter_graph(
        start_seconds=0,
        duration_seconds=5,
        has_source_audio=True,
        has_narration=False,
        normalize_audio=False,
    )
    assert "loudnorm" not in off_graph

    # Custom LUFS target (-16 LUFS podcast standard)
    custom_graph, _ = build_audio_filter_graph(
        start_seconds=0,
        duration_seconds=5,
        has_source_audio=True,
        has_narration=True,
        normalize_audio=True,
        target_lufs=-16.0,
        loudnorm_true_peak=-1.0,
    )
    assert "loudnorm=I=-16.0:TP=-1.0:LRA=11.0" in custom_graph


def test_render_clip_integration(synthetic_assets, tmp_path):
    """Integration test rendering all 3 target formats (landscape, vertical_blur, vertical_crop)."""
    config = RenderConfig(
        preferred_encoder="libx264",  # Use software x264 for deterministic test environment
        libx264_crf=20,
        libx264_preset="ultrafast",  # Fast test execution
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_001"

    # Render 1.5s clip with pure gameplay audio (no voiceover)
    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.5,
        duration_seconds=1.5,
        output_dir=output_dir,
        narration_path=None,
        modes=["landscape", "vertical_blur", "third_person"],
        overwrite=True,
    )

    # Verify all 3 video files and manifest were created locally
    assert Path(result.local_landscape_path).exists()
    assert Path(result.local_vertical_blur_path).exists()
    assert Path(result.local_vertical_crop_path).exists()
    assert Path(result.local_manifest_path).exists()

    # Verify streamable paths
    assert result.landscape_path.endswith(f"/renders/{result.clip_id}/stream/landscape")
    assert result.vertical_blur_path.endswith(
        f"/renders/{result.clip_id}/stream/vertical_blur"
    )
    assert result.vertical_crop_path.endswith(
        f"/renders/{result.clip_id}/stream/vertical_crop"
    )
    assert result.manifest_path.endswith(f"/renders/{result.clip_id}/stream/manifest")

    # Inspect landscape dimensions
    probe_land = probe_media(result.local_landscape_path)
    assert probe_land.width == 1920
    assert probe_land.height == 1080
    assert 1.4 <= probe_land.duration <= 1.6
    assert probe_land.has_audio is True

    # Inspect vertical blur dimensions
    probe_blur = probe_media(result.local_vertical_blur_path)
    assert probe_blur.width == 1080
    assert probe_blur.height == 1920
    assert 1.4 <= probe_blur.duration <= 1.6
    assert probe_blur.has_audio is True

    # Inspect vertical crop dimensions
    probe_crop = probe_media(result.local_vertical_crop_path)
    assert probe_crop.width == 1080
    assert probe_crop.height == 1920
    assert 1.4 <= probe_crop.duration <= 1.6
    assert probe_crop.has_audio is True

    # Inspect manifest.json
    with open(result.local_manifest_path) as f:
        manifest = json.load(f)
    assert manifest["request"]["duration_seconds"] == 1.5
    assert manifest["request"]["has_narration"] is False
    assert "landscape" in manifest["outputs"]
    assert "vertical_blur" in manifest["outputs"]
    assert "vertical_crop" in manifest["outputs"]
    assert manifest["outputs"]["landscape"]["path"].endswith(
        f"/renders/{result.clip_id}/stream/landscape"
    )
    assert manifest["landscape_path"].endswith(
        f"/renders/{result.clip_id}/stream/landscape"
    )


def test_render_with_narration_mixing(synthetic_assets, tmp_path):
    """Integration test rendering with voiceover narration mixing and ducking."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_with_narr"

    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.5,
        duration_seconds=1.5,
        output_dir=output_dir,
        narration_path=synthetic_assets["narration"],
        modes=["landscape", "vertical_blur", "third_person"],
        overwrite=True,
    )

    probe_land = probe_media(result.local_landscape_path)
    assert probe_land.has_audio is True
    assert 1.4 <= probe_land.duration <= 1.6

    with open(result.local_manifest_path) as f:
        manifest = json.load(f)
    assert manifest["request"]["has_narration"] is True


def test_render_with_direct_crop_preset(synthetic_assets, tmp_path):
    """Test single-pass rendering with direct 100% full-height center crop (no blur padding)."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_direct_crop"

    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        crop_preset="direct_crop",
        crop_blur_padding=0.0,
        overwrite=True,
    )

    probe_crop = probe_media(result.local_vertical_crop_path)
    assert probe_crop.width == 1080
    assert probe_crop.height == 1920

    with open(result.local_manifest_path) as f:
        manifest = json.load(f)
    assert manifest["request"]["crop_preset"] == "direct_crop"
    assert manifest["request"]["crop_blur_padding"] == 0.0


def test_render_progress_callback(synthetic_assets, tmp_path):
    """Verify progress callback is invoked with monotonically increasing percentages."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_progress"

    progress_events = []

    def on_prog(pct, stage):
        progress_events.append((pct, stage))

    engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        progress_callback=on_prog,
        overwrite=True,
    )

    assert len(progress_events) >= 3
    # Check start and completion
    assert progress_events[0][0] == 5.0
    assert progress_events[-1][0] == 100.0


def test_render_silent_video(synthetic_assets, tmp_path):
    """Verify single-pass multi-target render works when source video has no audio track."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_silent"

    result = engine.render_clip(
        source_path=synthetic_assets["silent_video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        modes=["landscape", "vertical_blur", "third_person"],
        overwrite=True,
    )

    for p in [
        result.local_landscape_path,
        result.local_vertical_blur_path,
        result.local_vertical_crop_path,
    ]:
        assert Path(p).exists()
        probe = probe_media(p)
        assert probe.has_audio is True


def test_render_single_mode_selection(synthetic_assets, tmp_path):
    """Verify rendering a single selected mode (e.g. only landscape)."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_single_mode"

    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        modes=["landscape"],
        overwrite=True,
    )

    assert result.modes == ["landscape"]
    assert Path(result.local_landscape_path).exists()
    assert (output_dir / "landscape.mp4").exists()
    assert not (output_dir / "vertical_blur.mp4").exists()


def test_render_clip_default_single_mode(synthetic_assets, tmp_path):
    """Verify that omitting modes defaults to the single third_person mode."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_default_single_mode"

    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        overwrite=True,
    )

    assert result.modes == ["third_person"]
    assert Path(result.local_vertical_crop_path).exists()
    assert result.local_landscape_path == ""
    assert result.local_vertical_blur_path == ""


def test_render_all_six_modes(synthetic_assets, tmp_path):
    """Verify rendering all 6 clipping modes simultaneously in a single pass."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_six_modes"

    all_modes = [
        "landscape",
        "vertical_blur",
        "third_person",
        "direct_crop",
        "cinematic",
        "custom",
    ]

    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=1.0,
        output_dir=output_dir,
        modes=all_modes,
        crop_blur_padding=0.15,
        overwrite=True,
    )

    assert result.modes == all_modes
    for m in all_modes:
        file_path = output_dir / f"{m}.mp4"
        assert file_path.exists(), f"Expected {m}.mp4 to exist"
        assert file_path.stat().st_size > 0

    # Also verify manifest recorded all 6 modes
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    import json

    with open(manifest_path) as f:
        manifest_data = json.load(f)
    assert manifest_data["modes"] == all_modes
    for m in all_modes:
        assert m in manifest_data["outputs"]


def test_render_clip_clamping_integration(synthetic_assets, tmp_path):
    """Verify that requesting a clip longer than source video duration auto-clamps safely."""
    config = RenderConfig(
        preferred_encoder="libx264",
        libx264_crf=20,
        libx264_preset="ultrafast",
        clamp_to_duration=True,
    )
    engine = RenderEngine(config=config)
    output_dir = tmp_path / "clip_clamped"

    # Synthetic asset is ~3.0s. Request 100s from 0.0s.
    result = engine.render_clip(
        source_path=synthetic_assets["video"],
        start_seconds=0.0,
        duration_seconds=100.0,
        output_dir=output_dir,
        modes=["landscape"],
        overwrite=True,
    )

    assert result.clamped is True
    assert result.requested_duration_seconds == 100.0
    assert result.effective_duration_seconds == pytest.approx(3.0, abs=0.1)
    assert (output_dir / "landscape.mp4").exists()

    manifest_path = output_dir / "manifest.json"
    import json

    with open(manifest_path) as f:
        manifest_data = json.load(f)

    assert manifest_data["request"]["clamped"] is True
    assert manifest_data["request"]["requested_duration_seconds"] == 100.0
    assert manifest_data["request"]["duration_seconds"] == pytest.approx(3.0, abs=0.1)
