"""Tests for Milestone 1 presentation presets and defaults."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.rendering.config import CinematicTreatmentConfig, RenderConfig
from app.rendering.engine import RenderEngine
from app.rendering.filters import (
    build_cinematic_zoom_filter,
    resolve_cinematic_target_time,
)
from app.rendering.presentation import (
    DEFAULT_PRESENTATION_PRESET,
    PRESENTATION_PRESETS,
    get_presentation_preset,
)
from app.schemas.channel import ChannelProfileUpdate
from app.services.channel_profile import ChannelProfileService

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_presentation_preset_definitions():
    """Verify all 3 deterministic presets are registered with correct specs."""
    assert "viral_kill" in PRESENTATION_PRESETS
    assert "cinematic_kill" in PRESENTATION_PRESETS
    assert "multi_kill_montage" in PRESENTATION_PRESETS

    # Default preset fallback
    assert get_presentation_preset(None).name == DEFAULT_PRESENTATION_PRESET
    assert get_presentation_preset("unknown_preset").name == DEFAULT_PRESENTATION_PRESET

    # Viral Kill (default): gameplay-first, no cards, subtle watermark, overlay CTA
    vk = get_presentation_preset("viral_kill")
    assert vk.branding_enabled is False
    assert vk.branding_intro is False
    assert vk.branding_outro is False
    assert vk.cta_enabled is True
    assert vk.cta_style == "overlay"
    assert vk.default_framing_preset == "third_person"
    assert vk.cinematic_treatment_enabled is False

    # Cinematic Kill: minimal branding, game audio focus, cinematic framing
    ck = get_presentation_preset("cinematic_kill")
    assert ck.branding_enabled is False
    assert ck.cta_enabled is False
    assert ck.default_framing_preset == "cinematic"
    assert ck.cinematic_treatment_enabled is True

    # Multi-Kill Montage: event-driven, subtle subscribe overlay
    mk = get_presentation_preset("multi_kill_montage")
    assert mk.branding_enabled is False
    assert mk.cta_enabled is True
    assert mk.kill_effects_enabled is True
    assert mk.cinematic_treatment_enabled is False


def test_list_presentation_presets_api(client: TestClient):
    """GET /api/v1/channel/presets returns all 3 presets wrapped in BaseResponse."""
    resp = client.get(f"{settings.API_PREFIX}/channel/presets")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True
    presets = body.get("response") or []
    assert len(presets) == 3

    names = {p["name"] for p in presets}
    assert names == {"viral_kill", "cinematic_kill", "multi_kill_montage"}

    # Check preset branding fields
    for p in presets:
        assert "branding_opacity" in p
        assert "branding_style" in p
        assert 0.0 <= p["branding_opacity"] <= 1.0
        assert p["branding_style"] in {"overlay", "bookend"}


def test_channel_profile_presentation_preset_lifecycle(client: TestClient, db_session):
    """Channel profile persists presentation_preset and honors overrides."""
    # Read profile: default is viral_kill
    get_res = client.get(f"{settings.API_PREFIX}/channel/profile")
    assert get_res.status_code == 200
    data = get_res.json()["response"]
    assert data["presentation_preset"] == "viral_kill"

    # Switch to cinematic_kill
    put_res = client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={"presentation_preset": "cinematic_kill"},
    )
    assert put_res.status_code == 200
    updated = put_res.json()["response"]
    assert updated["presentation_preset"] == "cinematic_kill"

    # Verify override behavior: creator explicitly turns on full-screen branding
    override_res = client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={
            "branding_enabled": True,
            "branding_intro_seconds": 1.5,
        },
    )
    assert override_res.status_code == 200
    overridden = override_res.json()["response"]
    # Profile override wins even though cinematic_kill preset defaults branding_enabled to False
    assert overridden["branding_enabled"] is True
    assert overridden["branding_intro_seconds"] == 1.5
    assert overridden["presentation_preset"] == "cinematic_kill"


def test_channel_profile_new_settings_roundtrip(client: TestClient, db_session):
    """Independent settings (watermark timing, hook, kill effects, target fps) update cleanly."""
    payload = {
        "presentation_preset": "multi_kill_montage",
        "watermark_start_seconds": 1.0,
        "watermark_end_seconds": 25.0,
        "hook_enabled": True,
        "hook_text": "CRAZY TEAM WIPE!",
        "hook_start_seconds": 0.0,
        "hook_duration_seconds": 2.0,
        "hook_position": "upper_third",
        "kill_effects_enabled": True,
        "target_fps": 60,
        "branding_opacity": 0.65,
        "branding_style": "overlay",
    }
    resp = client.put(f"{settings.API_PREFIX}/channel/profile", json=payload)
    assert resp.status_code == 200
    data = resp.json()["response"]

    assert data["presentation_preset"] == "multi_kill_montage"
    assert data["watermark_start_seconds"] == 1.0
    assert data["watermark_end_seconds"] == 25.0
    assert data["hook_enabled"] is True
    assert data["hook_text"] == "CRAZY TEAM WIPE!"
    assert data["hook_duration_seconds"] == 2.0
    assert data["hook_position"] == "upper_third"
    assert data["kill_effects_enabled"] is True
    assert data["target_fps"] == 60
    assert data["branding_opacity"] == 0.65
    assert data["branding_style"] == "overlay"


def test_cinematic_target_time_resolution():
    """Verify target time selection: explicit, elimination event, or midpoint with bounds check."""
    # Explicit target within bounds
    assert (
        resolve_cinematic_target_time(5.0, explicit_target=2.0, effect_duration=0.5)
        == 2.0
    )
    # Explicit target exceeding bounds is clamped to duration - effect_duration
    assert (
        resolve_cinematic_target_time(5.0, explicit_target=4.8, effect_duration=0.5)
        == 4.5
    )

    # Event list with elimination/kill timestamp
    events = [
        {"type": "damage", "timestamp": 0.5},
        {"event_type": "elimination", "timestamp": 2.2},
    ]
    assert resolve_cinematic_target_time(5.0, events=events, effect_duration=0.5) == 2.2

    # Events exceeding bounds are clamped
    late_events = [{"type": "kill", "time": 4.9}]
    assert (
        resolve_cinematic_target_time(5.0, events=late_events, effect_duration=0.5)
        == 4.5
    )

    # Midpoint fallback when no events or target (centered around 2.0s: 2.0 - 0.25 = 1.75)
    assert resolve_cinematic_target_time(4.0, effect_duration=0.5) == 1.75

    # Short duration fallback
    assert resolve_cinematic_target_time(0.4, effect_duration=0.5) == 0.0


def test_cinematic_zoom_filter_generation():
    """Verify build_cinematic_zoom_filter generates expected spatial crop/scale/overlay pipeline."""
    flt = build_cinematic_zoom_filter(
        input_label="[base]",
        output_label="[cine_out]",
        width=1080,
        height=1920,
        target_time=1.5,
        duration=0.5,
        scale=1.08,
        prefix="cine_test",
    )
    assert "[base]" in flt
    assert "[cine_out]" in flt
    assert "crop=" in flt
    assert "scale=1080:1920" in flt
    assert "overlay=0:0" in flt
    assert "between(t,1.500,2.000)" in flt


def test_cinematic_treatment_profile_service(db_session):
    """ChannelProfileService resolves cinematic_treatment based on preset and overrides."""
    # Default preset is viral_kill -> disabled
    cfg_vk = ChannelProfileService.cinematic_treatment_config(db_session)
    assert cfg_vk.enabled is False

    # Switch to cinematic_kill -> enabled by default
    ChannelProfileService.update(
        db_session, ChannelProfileUpdate(presentation_preset="cinematic_kill")
    )
    cfg_ck = ChannelProfileService.cinematic_treatment_config(db_session)
    assert cfg_ck.enabled is True
    assert cfg_ck.duration == 0.50
    assert cfg_ck.scale == 1.08

    # Explicit override: disable on cinematic_kill
    ChannelProfileService.update(
        db_session, ChannelProfileUpdate(cinematic_treatment_enabled=False)
    )
    cfg_ck_disabled = ChannelProfileService.cinematic_treatment_config(db_session)
    assert cfg_ck_disabled.enabled is False

    # Explicit override: enable on viral_kill
    ChannelProfileService.update(
        db_session,
        ChannelProfileUpdate(
            presentation_preset="viral_kill",
            cinematic_treatment_enabled=True,
        ),
    )
    cfg_vk_enabled = ChannelProfileService.cinematic_treatment_config(db_session)
    assert cfg_vk_enabled.enabled is True


def test_cinematic_treatment_render_integration(tmp_path: Path):
    """Render a synthetic clip with cinematic_treatment enabled and check manifest output."""
    video_path = tmp_path / "game_video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2.0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )

    out_dir = tmp_path / "renders"
    config = RenderConfig(
        modes=["vertical_crop"],
        crop_preset="cinematic",
        crop_blur_padding=0.0,
        vertical_width=720,
        vertical_height=1280,
        output_directory=str(out_dir),
        cinematic_treatment=CinematicTreatmentConfig(
            enabled=True,
            target_time=0.8,
            duration=0.5,
            scale=1.08,
        ),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=video_path,
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=2.0,
        clip_id="test_cinematic_clip",
    )

    assert result.clip_id == "test_cinematic_clip"
    out_video = out_dir / "vertical_crop.mp4"
    assert out_video.exists()
    assert out_video.stat().st_size > 0

    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert "cinematic_treatment" in manifest_data
    assert manifest_data["cinematic_treatment"]["enabled"] is True
    assert manifest_data["cinematic_treatment"]["duration"] == 0.5
    assert manifest_data["cinematic_treatment"]["scale"] == 1.08
    assert manifest_data["cinematic_treatment"]["target_time"] == 0.8
