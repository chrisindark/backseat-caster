"""Tests for channel background music upload, preview, and deletion (Milestone 7.3)."""

from __future__ import annotations

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
from app.rendering.config import RenderConfig
from app.rendering.engine import RenderEngine
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


@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory) -> bytes:
    """Generate 1-second synthetic 440 Hz WAV audio."""
    temp_dir = tmp_path_factory.mktemp("audio_assets")
    wav_path = temp_dir / "test_track.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        capture_output=True,
        check=True,
    )
    return wav_path.read_bytes()


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory) -> Path:
    """Generate 2-second 640x360 synthetic MP4 clip."""
    temp_dir = tmp_path_factory.mktemp("video_assets")
    mp4_path = temp_dir / "gameplay.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(mp4_path),
        ],
        capture_output=True,
        check=True,
    )
    return mp4_path


def test_music_upload_preview_and_delete(client, sample_wav):
    # 1. Initial state has no music
    initial = client.get(f"{settings.API_PREFIX}/channel/profile").json()["response"]
    assert initial.get("has_music") is False

    # 2. Upload WAV background music
    res = client.post(
        f"{settings.API_PREFIX}/channel/music",
        files={"file": ("battle_theme.wav", sample_wav, "audio/wav")},
    )
    assert res.status_code == 200
    payload = res.json()["response"]
    assert payload["profile"]["has_music"] is True
    assert payload["profile"]["music_url"] == "/api/v1/channel/music"
    assert "bg_music.wav" in payload["filename"]

    # 3. Stream / preview audio
    preview = client.get(f"{settings.API_PREFIX}/channel/music")
    assert preview.status_code == 200
    assert "audio/wav" in preview.headers["content-type"]
    assert len(preview.content) == len(sample_wav)

    # 4. Profile endpoint reports has_music=True
    updated_profile = client.get(f"{settings.API_PREFIX}/channel/profile").json()[
        "response"
    ]
    assert updated_profile["has_music"] is True
    assert updated_profile["bg_music_path"] is not None

    # 5. Delete music track
    delete_res = client.delete(f"{settings.API_PREFIX}/channel/music")
    assert delete_res.status_code == 200
    after_del = delete_res.json()["response"]
    assert after_del["has_music"] is False
    assert after_del["bg_music_path"] is None

    # 6. Stream after delete returns 404
    not_found = client.get(f"{settings.API_PREFIX}/channel/music")
    assert not_found.status_code == 404


def test_music_upload_validation(client):
    # Reject unsupported format (e.g., .txt)
    bad_ext = client.post(
        f"{settings.API_PREFIX}/channel/music",
        files={"file": ("track.txt", b"plain text", "text/plain")},
    )
    assert bad_ext.status_code == 400
    err_body = bad_ext.json().get("error_message") or bad_ext.json().get("detail", "")
    assert "Unsupported audio format" in err_body

    # Reject empty file
    empty_file = client.post(
        f"{settings.API_PREFIX}/channel/music",
        files={"file": ("track.mp3", b"", "audio/mpeg")},
    )
    assert empty_file.status_code == 400
    err_empty = empty_file.json().get("error_message") or empty_file.json().get(
        "detail", ""
    )
    assert "empty" in err_empty

    # Reject corrupted/fake audio
    corrupted = client.post(
        f"{settings.API_PREFIX}/channel/music",
        files={"file": ("track.mp3", b"this is not real audio content", "audio/mpeg")},
    )
    assert corrupted.status_code == 400
    err_corrupt = corrupted.json().get("error_message") or corrupted.json().get(
        "detail", ""
    )
    assert "audio" in err_corrupt.lower() or "ffprobe" in err_corrupt.lower()


def test_uploaded_music_used_in_rendering_and_recorded_in_manifest(
    client, db_session, sample_wav, sample_mp4, tmp_path
):
    import json

    # Upload music
    client.post(
        f"{settings.API_PREFIX}/channel/music",
        files={"file": ("bg_track.wav", sample_wav, "audio/wav")},
    )

    music_cfg = ChannelProfileService.music_config(db_session)
    assert music_cfg.enabled is True
    assert music_cfg.path is not None
    assert Path(music_cfg.path).exists()

    # Render a clip with music
    output_dir = tmp_path / "music_render_clip"
    config = RenderConfig(
        modes=["vertical_blur"],
        music=music_cfg,
    )
    engine = RenderEngine(config)
    result = engine.render_clip(
        source_path=sample_mp4,
        output_dir=output_dir,
        start_seconds=0.0,
        duration_seconds=1.5,
        clip_id="test_music_manifest",
    )
    assert result.clip_id == "test_music_manifest"

    # Verify manifest records music config
    manifest_file = output_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data.get("music", {}).get("enabled") is True
    assert manifest_data.get("music", {}).get("has_path") is True
    assert manifest_data.get("music", {}).get("volume") == music_cfg.volume

    # Clean up music
    client.delete(f"{settings.API_PREFIX}/channel/music")
    music_after = ChannelProfileService.music_config(db_session)
    assert music_after.enabled is False
    assert music_after.path is None
