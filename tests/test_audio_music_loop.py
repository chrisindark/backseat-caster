"""Tests for Milestone 5: Optional Audio and Loop Tools."""

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.rendering.audio import build_audio_filter_graph
from app.rendering.config import LoopConfig, MusicConfig, RenderConfig
from app.rendering.engine import RenderEngine
from app.rendering.loop import analyze_loop_continuity
from app.rendering.probe import probe_media
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
def synthetic_video_with_audio(tmp_path: Path) -> Path:
    """Create a 3-second 1920x1080 synthetic video with a 440 Hz sine audio tone."""
    video_path = tmp_path / "game_video.mp4"
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


@pytest.fixture
def synthetic_bg_music(tmp_path: Path) -> Path:
    """Create a 5-second 880 Hz background music audio file."""
    music_path = tmp_path / "bg_music.mp3"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:duration=5.0",
        "-c:a",
        "libmp3lame",
        str(music_path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"FFmpeg failed: {res.stderr.decode()}"
    return music_path


def test_build_audio_filter_graph_pure_game_audio():
    # Pure game audio without music or loop
    graph, label = build_audio_filter_graph(
        start_seconds=1.0,
        duration_seconds=5.0,
        has_source_audio=True,
        has_narration=False,
        has_music=False,
        loop_optimization=False,
    )
    assert label == "[a_out]"
    assert "[0:a]atrim=start=1.000:duration=5.000" in graph
    assert "loudnorm" in graph
    assert "amix" not in graph


def test_build_audio_filter_graph_with_music_ducking():
    # Game audio + music
    graph, label = build_audio_filter_graph(
        start_seconds=0.0,
        duration_seconds=4.0,
        has_source_audio=True,
        has_narration=False,
        has_music=True,
        music_input_label="1:a",
        music_gain=0.25,
        loop_optimization=False,
    )
    assert label == "[a_out]"
    assert "asplit=2[a_fg_key][a_fg_mix]" in graph
    assert "[1:a]atrim=duration=4.000" in graph
    assert "volume=0.25" in graph
    assert "sidechaincompress=" in graph
    assert "amix=" in graph
    assert "alimiter=" in graph


def test_build_audio_filter_graph_with_loop_micro_fade():
    # Game audio + loop smoothing
    graph, label = build_audio_filter_graph(
        start_seconds=0.0,
        duration_seconds=4.0,
        has_source_audio=True,
        has_narration=False,
        has_music=False,
        loop_optimization=True,
        loop_fade_seconds=0.10,
    )
    assert label == "[a_out]"
    assert "afade=t=in:ss=0:d=0.100" in graph
    assert "afade=t=out:st=3.900:d=0.100" in graph


def test_build_audio_filter_graph_all_combined():
    # Game audio + narration + music + loop optimization
    graph, label = build_audio_filter_graph(
        start_seconds=0.0,
        duration_seconds=6.0,
        has_source_audio=True,
        has_narration=True,
        narration_start_seconds=3.0,
        has_music=True,
        music_input_label="2:a",
        music_gain=0.30,
        loop_optimization=True,
        loop_fade_seconds=0.12,
    )
    assert label == "[a_out]"
    assert "[1:a]" in graph  # narration
    assert "[2:a]" in graph  # music
    assert "afade=t=in:ss=0:d=0.120" in graph
    assert "afade=t=out:st=5.880:d=0.120" in graph


def test_analyze_loop_continuity(synthetic_video_with_audio: Path, tmp_path: Path):
    # Valid synthetic video
    res = analyze_loop_continuity(
        synthetic_video_with_audio, start_seconds=0.0, duration_seconds=3.0
    )
    assert res.enabled is True
    assert 0.0 <= res.visual_similarity <= 1.0
    assert res.audio_seam_smoothed is True

    # Invalid video fallback
    res_invalid = analyze_loop_continuity(
        tmp_path / "nonexistent.mp4", start_seconds=0.0, duration_seconds=3.0
    )
    assert res_invalid.enabled is True
    assert res_invalid.visual_similarity == 0.0


def test_end_to_end_render_with_music_and_loop(
    synthetic_video_with_audio: Path,
    synthetic_bg_music: Path,
    tmp_path: Path,
):
    out_dir = tmp_path / "renders"
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset="direct_crop",
        crop_blur_padding=0.0,
        vertical_width=720,
        vertical_height=1280,
        output_directory=str(out_dir),
        music=MusicConfig(enabled=True, path=str(synthetic_bg_music), volume=0.20),
        loop=LoopConfig(enabled=True, fade_seconds=0.10),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_video_with_audio,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="test_music_loop_clip",
    )

    assert result.clip_id == "test_music_loop_clip"
    out_video = out_dir / "vertical_crop.mp4"
    assert out_video.exists()
    assert out_video.stat().st_size > 0

    # Probe rendered video to ensure audio stream is present and valid
    probe = probe_media(out_video)
    assert probe.has_audio is True
    assert probe.audio_codec in ("aac", "mp4a")

    # Verify manifest
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert "music" in manifest_data
    assert manifest_data["music"]["enabled"] is True
    assert manifest_data["music"]["has_path"] is True
    assert manifest_data["music"]["volume"] == 0.20

    assert "loop" in manifest_data
    assert manifest_data["loop"]["enabled"] is True
    assert manifest_data["loop"]["audio_seam_smoothed"] is True
    assert "visual_similarity" in manifest_data["loop"]


def test_channel_profile_music_and_loop_service(
    in_memory_db: Session,
    synthetic_bg_music: Path,
):
    # Default: music disabled (no path), loop_optimization is False
    music_cfg = ChannelProfileService.music_config(in_memory_db)
    loop_cfg = ChannelProfileService.loop_config(in_memory_db)
    assert music_cfg.enabled is False
    assert loop_cfg.enabled is False

    # Update profile with music and loop
    ChannelProfileService.update(
        in_memory_db,
        ChannelProfileUpdate(
            bg_music_path=str(synthetic_bg_music),
            bg_music_volume=0.35,
            loop_optimization=True,
        ),
    )
    music_cfg2 = ChannelProfileService.music_config(in_memory_db)
    loop_cfg2 = ChannelProfileService.loop_config(in_memory_db)
    assert music_cfg2.enabled is True
    assert music_cfg2.volume == 0.35
    assert loop_cfg2.enabled is True
