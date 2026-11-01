"""Tests for Milestone 1 presentation presets and defaults."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.rendering.presentation import (
    DEFAULT_PRESENTATION_PRESET,
    PRESENTATION_PRESETS,
    get_presentation_preset,
)

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

    # Cinematic Kill: minimal branding, game audio focus, cinematic framing
    ck = get_presentation_preset("cinematic_kill")
    assert ck.branding_enabled is False
    assert ck.cta_enabled is False
    assert ck.default_framing_preset == "cinematic"

    # Multi-Kill Montage: event-driven, subtle subscribe overlay
    mk = get_presentation_preset("multi_kill_montage")
    assert mk.branding_enabled is False
    assert mk.cta_enabled is True
    assert mk.kill_effects_enabled is True


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
