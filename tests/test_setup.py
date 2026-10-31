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


def test_setup_settings_do_not_own_branding(tmp_path, monkeypatch):
    """Branded bookends live in the channel profile, not the setup settings."""
    import json as jsonlib

    test_settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsManager, "get_persisted_settings_path", lambda: test_settings_file
    )

    initial = client.get("/api/v1/setup/settings").json()["response"]
    assert not any(key.startswith("branding_") for key in initial)

    # Even if a stale settings.json still carries branding keys, the setup API
    # must not expose them as writable configuration.
    test_settings_file.write_text(
        jsonlib.dumps({"branding_enabled": True}), encoding="utf-8"
    )
    assert not any(
        key.startswith("branding_")
        for key in client.get("/api/v1/setup/settings").json()["response"]
    )


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
