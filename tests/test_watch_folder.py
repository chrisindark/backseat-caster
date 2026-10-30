"""Tests for the OBS watch folder zero-click ingest (Phase 10, Tier 2)."""

import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.video import Video
from app.models.watch_ingest import WatchIngest
from app.services.watch_folder import WatchFolderService

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


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


@pytest.fixture
def watch_env(tmp_path, monkeypatch):
    """Configure a watch folder, temp storage, and instant-stable files."""
    watch_dir = tmp_path / "obs"
    watch_dir.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    monkeypatch.setattr(settings, "WATCH_DIR", str(watch_dir))
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(downloads))
    monkeypatch.setattr(settings, "WATCH_STABILITY_SECONDS", 0)
    monkeypatch.setattr(settings, "WATCH_MIN_FILE_MB", 0.0)
    monkeypatch.setattr(settings, "WATCH_DELETE_AFTER_INGEST", False)
    monkeypatch.setattr(settings, "AUTO_MINE_ON_INGEST", False)
    return watch_dir


def _record(path: Path, duration: int = 1) -> Path:
    """Write a tiny deterministic recording via FFmpeg."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration}:size=320x240:rate=15",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


# --------------------------------------------------------------- scanning


def test_scan_disabled_when_unconfigured(db_session, monkeypatch):
    monkeypatch.setattr(settings, "WATCH_DIR", None)

    result = WatchFolderService.scan(db_session)

    assert result["enabled"] is False
    assert result["ingested"] == 0
    assert "not configured" in result["message"]


def test_scan_reports_missing_directory(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WATCH_DIR", str(tmp_path / "does_not_exist"))

    result = WatchFolderService.scan(db_session)

    assert result["enabled"] is True
    assert result["exists"] is False if "exists" in result else True
    assert "does not exist" in result["message"]


def test_scan_ingests_finished_recording(db_session, watch_env):
    recording = _record(watch_env / "Ranked_win.mp4")

    result = WatchFolderService.scan(db_session)

    assert result["ingested"] == 1
    assert result["discovered"] == 1

    video = db_session.query(Video).one()
    assert video.id.startswith("watch_")
    assert video.title == "Ranked Win"
    assert video.download_status == "completed"
    assert video.channel_name == "OBS Watch Folder"
    assert Path(video.local_file_path).exists()
    # copied, not moved, by default
    assert recording.exists()

    ledger = db_session.query(WatchIngest).one()
    assert ledger.status == "ingested"
    assert ledger.video_id == video.id


def test_scan_is_idempotent_for_same_take(db_session, watch_env):
    _record(watch_env / "take_one.mp4")

    first = WatchFolderService.scan(db_session)
    second = WatchFolderService.scan(db_session)

    assert first["ingested"] == 1
    assert second["ingested"] == 0
    assert second["skipped"] == 1
    assert db_session.query(Video).count() == 1
    assert db_session.query(WatchIngest).count() == 1


def test_scan_reingests_rewritten_recording(db_session, watch_env):
    path = watch_env / "overwrite.mp4"
    _record(path, duration=1)

    WatchFolderService.scan(db_session)

    # OBS overwrites the same filename with a longer take
    time.sleep(0.01)
    _record(path, duration=2)

    result = WatchFolderService.scan(db_session)

    assert result["ingested"] == 1
    assert db_session.query(Video).count() == 2


def test_scan_skips_file_still_being_written(db_session, watch_env, monkeypatch):
    monkeypatch.setattr(settings, "WATCH_STABILITY_SECONDS", 3600)
    _record(watch_env / "recording.mp4")

    result = WatchFolderService.scan(db_session)

    assert result["discovered"] == 0
    assert result["ingested"] == 0
    assert db_session.query(Video).count() == 0


def test_scan_ignores_unsupported_and_small_files(db_session, watch_env, monkeypatch):
    monkeypatch.setattr(settings, "WATCH_MIN_FILE_MB", 1.0)
    (watch_env / "notes.txt").write_text("not a video")
    (watch_env / "tiny.mp4").write_bytes(b"0" * 100)

    result = WatchFolderService.scan(db_session)

    assert result["ingested"] == 0
    assert db_session.query(Video).count() == 0


def test_dry_run_does_not_ingest(db_session, watch_env):
    _record(watch_env / "dry.mp4")

    result = WatchFolderService.scan(db_session, ingest=False)

    assert result["ingested"] == 0
    assert result["items"][0]["status"] == "would_ingest"
    assert db_session.query(Video).count() == 0


def test_delete_after_ingest_moves_source(db_session, watch_env, monkeypatch):
    monkeypatch.setattr(settings, "WATCH_DELETE_AFTER_INGEST", True)
    source = _record(watch_env / "move_me.mp4")

    result = WatchFolderService.scan(db_session)

    assert result["ingested"] == 1
    assert not source.exists()
    video = db_session.query(Video).one()
    assert Path(video.local_file_path).exists()


def test_scan_triggers_auto_mine(db_session, watch_env, monkeypatch):
    calls: list[str] = []

    from app.services import auto_mine as auto_mine_module

    monkeypatch.setattr(
        auto_mine_module.AutoMineService,
        "trigger_after_ingest",
        classmethod(
            lambda cls, db, video_id, background_tasks=None: calls.append(video_id)
            or {"triggered": True, "video_id": video_id}
        ),
    )
    _record(watch_env / "mine_me.mp4")

    WatchFolderService.scan(db_session)

    assert len(calls) == 1
    assert calls[0].startswith("watch_")


def test_failed_ingest_is_recorded(db_session, watch_env):
    # A file that looks like a video but cannot be probed
    (watch_env / "corrupt.mp4").write_bytes(b"not really an mp4" * 100_000)

    result = WatchFolderService.scan(db_session)

    assert result["failed"] == 1
    ledger = db_session.query(WatchIngest).one()
    assert ledger.status == "failed"
    assert ledger.error_message


def test_status_reports_configuration(db_session, watch_env):
    _record(watch_env / "pending.mp4")

    status = WatchFolderService.status(db_session)

    assert status["enabled"] is True
    assert status["exists"] is True
    assert status["pending_files"] == 1
    assert ".mp4" in status["supported_extensions"]
    assert status["recent_ingests"] == []


# ------------------------------------------------------------------- API


def test_watch_status_endpoint(client, watch_env):
    response = client.get(f"{settings.API_PREFIX}/videos/watch/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["response"]["enabled"] is True
    assert body["response"]["watch_dir"] == str(watch_env.resolve())


def test_watch_scan_endpoint(client, watch_env):
    _record(watch_env / "via_api.mp4")

    response = client.post(f"{settings.API_PREFIX}/videos/watch/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["response"]["ingested"] == 1
    assert body["response"]["items"][0]["status"] == "ingested"


def test_watch_scan_endpoint_dry_run(client, watch_env):
    _record(watch_env / "preview.mp4")

    response = client.post(f"{settings.API_PREFIX}/videos/watch/scan?dry_run=true")

    assert response.status_code == 200
    assert response.json()["response"]["ingested"] == 0
