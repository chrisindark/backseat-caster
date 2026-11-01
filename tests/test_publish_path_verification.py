"""Tests for Milestone 6: Output Quality and Publish-Path Verification."""

import json
import subprocess
from pathlib import Path

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
