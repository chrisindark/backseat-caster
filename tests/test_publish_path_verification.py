"""Tests for Milestone 6: Output Quality and Publish-Path Verification."""

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.rendering.config import (
    QUALITY_PRESETS,
    BrandingConfig,
    CtaConfig,
    DurationBudget,
    HookConfig,
    KillEffectsConfig,
    RenderConfig,
    WatermarkConfig,
)
from app.rendering.engine import RenderEngine, select_encoder
from app.rendering.presentation import PRESENTATION_PRESETS
from app.rendering.probe import probe_media


@pytest.fixture
def in_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def synthetic_source_video(tmp_path: Path) -> Path:
    """Create a 4-second 1920x1080 30fps source video with stereo sine audio."""
    video_path = tmp_path / "source_1080p.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1920x1080:rate=30:duration=4",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=520:duration=4.0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"FFmpeg failed: {res.stderr.decode()}"
    return video_path


def test_quality_presets_bitrates():
    assert QUALITY_PRESETS["high"]["videotoolbox_bitrate"] == "12M"
    assert QUALITY_PRESETS["compact"]["videotoolbox_bitrate"] == "5M"
    assert QUALITY_PRESETS["archive"]["videotoolbox_bitrate"] == "20M"


def test_select_encoder_target_fps():
    cfg_30 = RenderConfig(preferred_encoder="libx264", target_fps=None)
    _, flags_30 = select_encoder(cfg_30)
    assert "-r" not in flags_30

    cfg_60 = RenderConfig(preferred_encoder="libx264", target_fps=60)
    _, flags_60 = select_encoder(cfg_60)
    assert "-r" in flags_60
    assert "60" in flags_60


def test_target_60fps_render_and_probe(synthetic_source_video: Path, tmp_path: Path):
    out_dir = tmp_path / "renders_60fps"
    config = RenderConfig(
        modes=["vertical_blur"],
        vertical_width=1080,
        vertical_height=1920,
        preferred_encoder="libx264",
        libx264_preset="ultrafast",
        target_fps=60,
        output_directory=str(out_dir),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="clip_60fps",
    )
    assert result.clip_id == "clip_60fps"
    out_file = out_dir / "vertical_blur.mp4"
    assert out_file.exists()

    probe = probe_media(out_file)
    assert probe.width == 1080
    assert probe.height == 1920
    assert probe.fps == 60.0
    assert probe.has_audio is True
    assert probe.audio_sample_rate == 48000


def test_preset_viral_kill_render_verification(
    synthetic_source_video: Path, tmp_path: Path
):
    """Viral Kill preset: gameplay from frame 1, subtle watermark, lower-third CTA pill, 0 intro/outro."""
    preset = PRESENTATION_PRESETS["viral_kill"]
    out_dir = tmp_path / "render_viral_kill"
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset=preset.default_framing_preset,
        vertical_width=720,
        vertical_height=1280,
        preferred_encoder="libx264",
        libx264_preset="ultrafast",
        output_directory=str(out_dir),
        branding=BrandingConfig(enabled=False),
        watermark=WatermarkConfig(
            enabled=True, channel_name="TestStreamer", opacity=0.70
        ),
        cta=CtaConfig(enabled=True, style="overlay", seconds=1.0, headline="SUB NOW"),
        hook=HookConfig(enabled=False),
        kill_effects=KillEffectsConfig(enabled=False),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=1.0,
        duration_seconds=2.0,
        clip_id="viral_kill_clip",
    )
    assert result.clip_id == "viral_kill_clip"
    manifest_data = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    # Assert gameplay begins immediately with zero card bookends
    assert manifest_data["branding"]["enabled"] is False
    assert manifest_data["branding"]["intro_seconds"] == 0.0
    assert manifest_data["branding"]["outro_seconds"] == 0.0
    assert manifest_data["watermark"]["enabled"] is True
    assert manifest_data["cta"]["enabled"] is True
    assert manifest_data["cta"]["style"] == "overlay"


def test_preset_multi_kill_montage_render_verification(
    synthetic_source_video: Path, tmp_path: Path
):
    """Multi-kill montage: kill effects enabled with punch-in zoom and combo badges."""
    out_dir = tmp_path / "render_multi_kill"
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset="third_person",
        vertical_width=720,
        vertical_height=1280,
        preferred_encoder="libx264",
        libx264_preset="ultrafast",
        output_directory=str(out_dir),
        kill_effects=KillEffectsConfig(
            enabled=True,
            punch_in=True,
            kill_notification=True,
            events=[
                {"time": 0.5, "label": "DOUBLE KO", "combo": 2},
                {"time": 1.2, "label": "TRIPLE KO", "combo": 3},
            ],
        ),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="multi_kill_clip",
    )
    assert result.clip_id == "multi_kill_clip"
    manifest_data = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["kill_effects"]["enabled"] is True
    assert manifest_data["kill_effects"]["event_count"] == 2


def test_full_screen_branded_cards_render_verification(
    synthetic_source_video: Path, tmp_path: Path
):
    """Optional full-screen intro and outro cards."""
    out_dir = tmp_path / "render_cards"
    config = RenderConfig(
        modes=["vertical_blur"],
        vertical_width=720,
        vertical_height=1280,
        preferred_encoder="libx264",
        libx264_preset="ultrafast",
        output_directory=str(out_dir),
        branding=BrandingConfig(
            enabled=True,
            intro=True,
            outro=True,
            intro_seconds=1.0,
            outro_seconds=1.0,
            intro_title="MATCH HIGHLIGHTS",
            outro_title="SUBSCRIBE",
        ),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="cards_clip",
    )
    assert result.clip_id == "cards_clip"
    out_file = out_dir / "vertical_blur.mp4"
    probe = probe_media(out_file)
    # Total duration = 2.0s gameplay + 1.0s intro + 1.0s outro = ~4.0s
    assert 3.8 <= probe.duration <= 4.2


def test_duration_budget_and_staging_compliance():
    budget = DurationBudget(max_seconds=90.0, bookend_seconds=3.0)

    # 15s kill highlight fits comfortably in 'shorts'
    assert budget.fits(15.0) is True
    assert budget.tier(15.0) == "shorts"

    # 25s multi-kill highlight fits in 'shorts'
    assert budget.fits(25.0) is True
    assert budget.tier(25.0) == "shorts"

    # 70s extended highlight fits in 'extended'
    assert budget.fits(70.0) is True
    assert budget.tier(70.0) in ("extended", "long")

    # Over 90s ceiling
    assert budget.fits(95.0) is False
    assert budget.tier(95.0) == "over_ceiling"
    assert budget.clamp(95.0) == 87.0  # 90.0 - 3.0


def probe_stream_durations(file_path: Path | str) -> tuple[float, float]:
    """Inspect and return (video_stream_duration, audio_stream_duration) via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,duration",
        "-of",
        "json",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    v_dur = next(
        float(s["duration"])
        for s in data.get("streams", [])
        if s.get("codec_type") == "video"
    )
    a_dur = next(
        float(s["duration"])
        for s in data.get("streams", [])
        if s.get("codec_type") == "audio"
    )
    return v_dur, a_dur


def verify_av_sync(
    file_path: Path | str, tolerance_seconds: float = 0.05
) -> tuple[float, float]:
    """Assert audio and video streams exist and durations match within tolerance."""
    v_dur, a_dur = probe_stream_durations(file_path)
    diff = abs(v_dur - a_dur)
    if diff > tolerance_seconds:
        raise AssertionError(
            f"A/V sync mismatch in {file_path}: video={v_dur:.3f}s, audio={a_dur:.3f}s, diff={diff:.3f}s > {tolerance_seconds:.3f}s"
        )
    return v_dur, a_dur


def verify_elimination_payoff_intact(
    rendered_duration: float,
    events: list[dict],
    payoff_duration: float = 0.50,
) -> float:
    """Verify that the final elimination and its payoff window are not truncated."""
    elim_times = [
        float(ev.get("time") if ev.get("time") is not None else ev.get("timestamp"))
        for ev in events
        if any(
            k
            in str(
                ev.get("action")
                or ev.get("label")
                or ev.get("type")
                or ev.get("event_type")
                or ""
            ).lower()
            for k in ("elim", "kill", "knock", "ko", "wipe")
        )
    ]
    if not elim_times:
        return rendered_duration
    final_elim_time = max(elim_times)
    required_end_time = final_elim_time + payoff_duration
    if rendered_duration < required_end_time:
        raise AssertionError(
            f"Elimination payoff truncated! Final elimination at {final_elim_time:.3f}s with {payoff_duration:.3f}s payoff "
            f"requires at least {required_end_time:.3f}s, but rendered duration is only {rendered_duration:.3f}s."
        )
    return final_elim_time


def test_av_stream_duration_sync_across_render_configurations(
    synthetic_source_video: Path, tmp_path: Path
):
    """Step 7.6: Assert audio and video stream durations agree within 50ms across all 4 bookend configurations."""
    configs = {
        "overlay-only": RenderConfig(
            modes=["landscape"],
            output_directory=str(tmp_path / "overlay_only"),
            branding=BrandingConfig(enabled=False),
            watermark=WatermarkConfig(enabled=True, channel_name="TestStreamer"),
            cta=CtaConfig(enabled=True, style="overlay", seconds=1.0, headline="SUB"),
        ),
        "intro-only": RenderConfig(
            modes=["landscape"],
            output_directory=str(tmp_path / "intro_only"),
            branding=BrandingConfig(
                enabled=True,
                intro=True,
                outro=False,
                intro_seconds=1.0,
                intro_title="MATCH HIGHLIGHTS",
            ),
        ),
        "outro-only": RenderConfig(
            modes=["landscape"],
            output_directory=str(tmp_path / "outro_only"),
            branding=BrandingConfig(
                enabled=True,
                intro=False,
                outro=True,
                outro_seconds=1.0,
                outro_title="SUBSCRIBE",
            ),
        ),
        "gameplay-first": RenderConfig(
            modes=["landscape"],
            output_directory=str(tmp_path / "gameplay_first"),
            branding=BrandingConfig(enabled=False),
        ),
    }

    for name, cfg in configs.items():
        out_dir = tmp_path / name
        engine = RenderEngine(config=cfg)
        result = engine.render_clip(
            source_path=synthetic_source_video,
            output_dir=out_dir,
            start_seconds=0.0,
            duration_seconds=2.0,
            clip_id=name,
        )
        assert result.clip_id == name
        out_file = out_dir / "landscape.mp4"
        assert out_file.exists()

        v_dur, a_dur = verify_av_sync(out_file, tolerance_seconds=0.05)
        # Expected duration: 2.0s gameplay + 1.0s if intro or outro
        expected_dur = 3.0 if "only" in name and name != "overlay-only" else 2.0
        assert abs(v_dur - expected_dur) < 0.15
        assert abs(a_dur - expected_dur) < 0.15


def test_overlay_frame_sampling_and_lifecycle(
    synthetic_source_video: Path, tmp_path: Path
):
    """Step 7.6: Sample frames at expected timestamps to verify overlay presence during window and absence afterwards."""
    out_dir = tmp_path / "overlay_lifecycle"
    config = RenderConfig(
        modes=["landscape"],
        landscape_width=1920,
        landscape_height=1080,
        output_directory=str(out_dir),
        hook=HookConfig(
            enabled=True,
            text="HEADSHOT",
            start_seconds=0.0,
            duration_seconds=1.0,
            position="upper_third",
        ),
    )
    engine = RenderEngine(config=config)
    engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.5,
        clip_id="hook_lifecycle",
    )
    rendered_file = out_dir / "landscape.mp4"

    cap_src = cv2.VideoCapture(str(synthetic_source_video))
    cap_out = cv2.VideoCapture(str(rendered_file))

    def compute_upper_third_diff(t_ms: float) -> float:
        cap_src.set(cv2.CAP_PROP_POS_MSEC, t_ms)
        cap_out.set(cv2.CAP_PROP_POS_MSEC, t_ms)
        ret1, f_src = cap_src.read()
        ret2, f_out = cap_out.read()
        assert ret1 and ret2, f"Failed to read frames at {t_ms}ms"
        # Upper third region where Hook banner is drawn: y in [60, 260], x in [300, 1620]
        r_src = f_src[60:260, 300:1620]
        r_out = f_out[60:260, 300:1620]
        return float(np.mean(np.abs(r_src.astype(float) - r_out.astype(float))))

    # At t=0.50s (inside the 0.0-1.0s window): overlay is active
    diff_active = compute_upper_third_diff(500.0)
    # At t=1.80s (well after window ended at 1.0s): overlay is completely absent
    diff_after = compute_upper_third_diff(1800.0)

    cap_src.release()
    cap_out.release()

    # Overlay badge creates noticeable pixel difference compared to bare source
    assert diff_active > 5.0, (
        f"Overlay was not detected during active window (diff={diff_active})"
    )
    # After overlay window expires, frame matches source
    assert diff_after < 1.0, (
        f"Overlay persisted unexpectedly after window ended (diff={diff_after})"
    )


def test_elimination_payoff_window_integrity(
    synthetic_source_video: Path, tmp_path: Path
):
    """Step 7.6: Verify that the final elimination window survives into the rendered file without truncation."""
    out_dir = tmp_path / "payoff_integrity"
    events = [
        {"time": 0.5, "label": "DOUBLE KO", "combo": 2},
        {"time": 1.7, "label": "TRIPLE KO", "combo": 3},
    ]
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset="third_person",
        vertical_width=720,
        vertical_height=1280,
        output_directory=str(out_dir),
        kill_effects=KillEffectsConfig(
            enabled=True,
            punch_in=True,
            kill_notification=True,
            events=events,
        ),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_source_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.5,
        clip_id="payoff_clip",
    )
    assert result.clip_id == "payoff_clip"
    out_video = out_dir / "vertical_crop.mp4"
    probe = probe_media(out_video)

    # Verification passes: 2.5s clip accommodates final elimination at 1.7s + 0.5s payoff = 2.2s
    final_time = verify_elimination_payoff_intact(
        probe.duration, events, payoff_duration=0.50
    )
    assert final_time == 1.7

    manifest_data = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["kill_effects"]["event_count"] == 2


def test_av_sync_and_payoff_verification_catches_defects(tmp_path: Path):
    """Step 7.6: Acceptance verification - prove that checks fail on deliberately offset or clipped renders."""
    # 1. Deliberately desynced video (video duration = 2.0s, audio duration = 3.0s)
    desync_file = tmp_path / "desynced.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3.0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(desync_file),
        ],
        check=True,
        capture_output=True,
    )

    with pytest.raises(AssertionError, match="A/V sync mismatch"):
        verify_av_sync(desync_file, tolerance_seconds=0.05)

    # 2. Deliberately clipped elimination payoff window
    late_events = [{"time": 1.7, "label": "TRIPLE KO"}]
    # A 1.8s render cuts off the 0.50s payoff window (which needs at least 2.2s)
    with pytest.raises(AssertionError, match="Elimination payoff truncated"):
        verify_elimination_payoff_intact(1.8, late_events, payoff_duration=0.50)
