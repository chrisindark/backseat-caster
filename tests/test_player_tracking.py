"""Tests for Milestone 4: Computer Vision Player Tracking and Dynamic Vertical Reframing."""

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.rendering.config import RenderConfig, TrackingConfig
from app.rendering.engine import RenderEngine
from app.rendering.filters import build_vertical_crop_filter
from app.rendering.tracking import (
    PlayerTracker,
    TrackingKeyframe,
    build_trajectory_expression,
)
from app.schemas.channel import ChannelProfileUpdate
from app.services.channel_profile import ChannelProfileService


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
def synthetic_moving_video(tmp_path: Path) -> Path:
    """Create a 3-second 1920x1080 synthetic video with moving content."""
    video_path = tmp_path / "synthetic_moving.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1920x1080:rate=30:duration=3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=3.0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"FFmpeg failed: {res.stderr.decode()}"
    return video_path


def test_trajectory_expression_edge_cases():
    # Empty or single keyframe returns static center crop
    assert build_trajectory_expression([]) == "(in_w-out_w)/2"
    assert (
        build_trajectory_expression([TrackingKeyframe(time=0.0, normalized_x=0.5)])
        == "(in_w-out_w)/2"
    )

    # Multi-keyframe returns bounded clamped piecewise expression
    keyframes = [
        TrackingKeyframe(time=0.0, normalized_x=0.45),
        TrackingKeyframe(time=1.5, normalized_x=0.55),
        TrackingKeyframe(time=3.0, normalized_x=0.50),
    ]
    expr = build_trajectory_expression(keyframes)
    assert expr.startswith("min(max(0,")
    assert expr.endswith("in_w-out_w)")
    assert "lte(t,1.50)" in expr
    assert "lte(t,3.00)" in expr


def test_build_vertical_crop_filter_with_tracking():
    # Default without crop_x
    filter_default = build_vertical_crop_filter(
        width=1080, height=1920, blur_padding=0.0
    )
    assert "crop=1080:1920:'(in_w-1080)/2':0" in filter_default

    # Custom trajectory crop_x
    custom_crop_x = "min(max(0,0.500*in_w-out_w/2),in_w-out_w)"
    filter_tracked = build_vertical_crop_filter(
        width=1080, height=1920, blur_padding=0.0, crop_x=custom_crop_x
    )
    assert f"crop=1080:1920:'{custom_crop_x}':0" in filter_tracked

    # Blurred crop mode with custom crop_x
    filter_blurred = build_vertical_crop_filter(
        width=1080, height=1920, blur_padding=0.3333, crop_x=custom_crop_x
    )
    assert f"crop=1080:1280:'{custom_crop_x}':0" in filter_blurred


def test_player_tracker_disabled_and_invalid_inputs(tmp_path: Path):
    tracker = PlayerTracker(TrackingConfig(enabled=False))
    res = tracker.track_clip(tmp_path / "nonexistent.mp4", 0.0, 3.0)
    assert res.enabled is False
    assert res.fallback_used is True
    assert res.crop_x_expr == "(in_w-out_w)/2"

    tracker_enabled = PlayerTracker(TrackingConfig(enabled=True))
    res2 = tracker_enabled.track_clip(tmp_path / "nonexistent.mp4", 0.0, 3.0)
    assert res2.enabled is True
    assert res2.fallback_used is True

    # Duration too short
    dummy_file = tmp_path / "dummy.mp4"
    dummy_file.write_text("dummy")
    res3 = tracker_enabled.track_clip(dummy_file, 0.0, 0.2)
    assert res3.fallback_used is True


def test_player_tracker_analyzes_synthetic_video(synthetic_moving_video: Path):
    config = TrackingConfig(
        enabled=True,
        sample_rate_hz=2.0,
        smoothness=0.3,
        max_pan_speed=0.2,
        min_confidence=0.3,
    )
    tracker = PlayerTracker(config=config)
    result = tracker.track_clip(
        synthetic_moving_video, start_seconds=0.0, duration_seconds=3.0
    )

    assert result.enabled is True
    assert result.fallback_used is False
    assert len(result.keyframes) >= 3
    # Check that keyframes stay within safe bounds [0.35, 0.65]
    for kf in result.keyframes:
        assert 0.35 <= kf.normalized_x <= 0.65
    assert result.crop_x_expr.startswith("min(max(0,")


def test_end_to_end_render_with_tracking(synthetic_moving_video: Path, tmp_path: Path):
    out_dir = tmp_path / "renders"
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset="direct_crop",
        crop_blur_padding=0.0,
        vertical_width=720,
        vertical_height=1280,
        output_directory=str(out_dir),
        tracking=TrackingConfig(enabled=True, sample_rate_hz=2.0),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_moving_video,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="test_tracking_clip",
    )

    assert result.clip_id == "test_tracking_clip"
    crop_video_path = out_dir / "vertical_crop.mp4"
    assert crop_video_path.exists()
    assert crop_video_path.stat().st_size > 0

    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "tracking" in manifest_data
    assert manifest_data["tracking"]["enabled"] is True
    assert manifest_data["tracking"]["keyframe_count"] > 0
    assert "crop_x_expr" in manifest_data["tracking"]


def test_channel_profile_tracking_defaults_and_override(in_memory_db: Session):
    # Default preset is viral_kill -> tracking_enabled is False
    tracking_cfg = ChannelProfileService.tracking_config(in_memory_db)
    assert tracking_cfg.enabled is False

    # Switch to cinematic_kill -> tracking_enabled becomes True
    ChannelProfileService.update(
        in_memory_db, ChannelProfileUpdate(presentation_preset="cinematic_kill")
    )
    tracking_cfg2 = ChannelProfileService.tracking_config(in_memory_db)
    assert tracking_cfg2.enabled is True

    # Explicit override to False
    ChannelProfileService.update(
        in_memory_db, ChannelProfileUpdate(tracking_enabled=False)
    )
    tracking_cfg3 = ChannelProfileService.tracking_config(in_memory_db)
    assert tracking_cfg3.enabled is False

    # Explicit override to True
    ChannelProfileService.update(
        in_memory_db, ChannelProfileUpdate(tracking_enabled=True)
    )
    tracking_cfg4 = ChannelProfileService.tracking_config(in_memory_db)
    assert tracking_cfg4.enabled is True
