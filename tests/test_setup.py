"""Unit tests for the first-run setup wizard, in-app settings, and demo seeding."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.settings_manager import SettingsManager

client = TestClient(app)


def test_setup_status_returns_expected_checks():
    response = client.get("/api/v1/setup/status")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    resp = data["response"]
    assert "ready" in resp
    assert "checks" in resp
    # 4 core checks plus the optional zero-click ingest check
    assert len(resp["checks"]) == 5

    check_names = [c["name"] for c in resp["checks"]]
    assert "ffmpeg" in check_names
    assert "disk_space" in check_names
    assert "ai_key" in check_names
    assert "youtube" in check_names
    assert "watch_folder" in check_names

    # Check required flags
    ffmpeg_check = next(c for c in resp["checks"] if c["name"] == "ffmpeg")
    assert ffmpeg_check["required"] is True

    disk_check = next(c for c in resp["checks"] if c["name"] == "disk_space")
    assert disk_check["required"] is True

    ai_check = next(c for c in resp["checks"] if c["name"] == "ai_key")
    assert ai_check["required"] is False

    watch_check = next(c for c in resp["checks"] if c["name"] == "watch_folder")
    assert watch_check["required"] is False

    yt_check = next(c for c in resp["checks"] if c["name"] == "youtube")
    assert yt_check["required"] is False


def test_get_and_patch_runtime_settings(tmp_path, monkeypatch):
    test_settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsManager, "get_persisted_settings_path", lambda: test_settings_file
    )

    # 1. Get current settings
    res = client.get("/api/v1/setup/settings")
    assert res.status_code == 200
    initial = res.json()["response"]
    assert "llm_enabled" in initial
    assert "default_clipping_mode" in initial

    # 2. Update settings via PATCH
    update_payload = {
        "llm_enabled": True,
        "llm_model": "test-model-4b",
        "llm_base_url": "http://127.0.0.1:11434/v1",
        "default_clipping_mode": "cinematic",
        "auto_stage_top_n": 5,
    }
    patch_res = client.patch("/api/v1/setup/settings", json=update_payload)
    assert patch_res.status_code == 200
    updated = patch_res.json()["response"]
    assert updated["llm_enabled"] is True
    assert updated["llm_model"] == "test-model-4b"
    assert updated["llm_base_url"] == "http://127.0.0.1:11434/v1"
    assert updated["default_clipping_mode"] == "cinematic"
    assert updated["auto_stage_top_n"] == 5

    # Verify persisted on disk
    assert test_settings_file.exists()


def test_branding_settings_round_trip(tmp_path, monkeypatch):
    """Branded bookends are editable at runtime and feed the render defaults."""
    from app.config import settings
    from app.rendering.config import default_branding_config

    test_settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsManager, "get_persisted_settings_path", lambda: test_settings_file
    )
    # Keep the shared settings object clean for any test that runs afterwards.
    for attr in (
        "BRANDING_ENABLED",
        "BRANDING_CHANNEL_NAME",
        "BRANDING_INTRO_ENABLED",
        "BRANDING_OUTRO_ENABLED",
        "BRANDING_INTRO_SECONDS",
        "BRANDING_OUTRO_SECONDS",
        "BRANDING_ACCENT_COLOR",
    ):
        monkeypatch.setattr(settings, attr, getattr(settings, attr))

    initial = client.get("/api/v1/setup/settings").json()["response"]
    assert initial["branding_enabled"] is False
    assert initial["branding_outro_title"] == "SUBSCRIBE"

    patch_res = client.patch(
        "/api/v1/setup/settings",
        json={
            "branding_enabled": True,
            "branding_channel_name": "@BackseatCaster",
            "branding_intro_enabled": False,
            "branding_outro_seconds": 2.5,
            "branding_accent_color": "#22D3EE",
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()["response"]
    assert updated["branding_enabled"] is True
    assert updated["branding_channel_name"] == "@BackseatCaster"
    assert updated["branding_intro_enabled"] is False
    assert updated["branding_outro_seconds"] == 2.5

    branding = default_branding_config()
    assert branding.enabled is True
    assert branding.has_intro is False
    assert branding.has_outro is True
    assert branding.outro_seconds == 2.5
    assert branding.accent_color == "#22D3EE"
    assert branding.resolved_outro_subtitle() == "@BackseatCaster"


def test_load_sample_demo_project_creates_video_and_candidates(monkeypatch, tmp_path):
    # Mock ffmpeg generation so test runs in 100ms
    mock_demo_file = tmp_path / "demo_test.mp4"
    mock_demo_file.write_bytes(b"dummy video data" * 1000)

    from app.services.setup import SetupService

    monkeypatch.setattr(
        SetupService, "generate_demo_video_file", lambda: mock_demo_file
    )

    # Post demo project request with auto_render=False to test seeding
    res = client.post(
        "/api/v1/setup/demo",
        json={"auto_render": False, "sync": False},
    )
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["success"] is True
    assert data["video_id"] == "demo_marvel_rivals_60s"
    assert data["candidates_count"] == 3
