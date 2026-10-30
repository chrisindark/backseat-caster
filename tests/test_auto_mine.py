"""Tests for the zero-input auto-mine pipeline (Phase 10, Tier 2)."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.video import Video
from app.services import auto_mine as auto_mine_module
from app.services.auto_mine import AutoMineService
from app.services.videos import VideoService

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
def auto_mine_off(monkeypatch):
    """Default state: auto-mine disabled."""
    monkeypatch.setattr(settings, "AUTO_MINE_ON_INGEST", False)
    return monkeypatch


def _make_clip(path: Path, duration: int = 1) -> Path:
    """Render a tiny deterministic test video with FFmpeg."""
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


def _make_video(db, tmp_path, video_id: str = "vid_auto_mine") -> Video:
    clip = _make_clip(tmp_path / f"{video_id}.mp4")
    video = Video(
        id=video_id,
        title="Marvel Rivals Ranked Clutch",
        webpage_url=f"https://youtube.com/watch?v={video_id}",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(clip),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


# --------------------------------------------------------------- guards


def test_auto_mine_disabled_by_default(db_session, tmp_path, auto_mine_off):
    video = _make_video(db_session, tmp_path)

    result = AutoMineService.trigger_after_ingest(db_session, video.id)

    assert result["triggered"] is False
    assert "disabled" in result["reason"]
    db_session.refresh(video)
    assert video.highlight_status == "idle"


def test_should_mine_rejects_missing_video(db_session, auto_mine_off):
    auto_mine_off.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    ok, reason = AutoMineService.should_mine(None)
    assert ok is False
    assert "not found" in reason


def test_should_mine_rejects_already_scanned(db_session, tmp_path, auto_mine_off):
    auto_mine_off.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    video = _make_video(db_session, tmp_path)
    video.highlight_status = "completed"
    db_session.commit()

    ok, reason = AutoMineService.should_mine(video)
    assert ok is False
    assert "already" in reason


def test_should_mine_rejects_missing_file(db_session, tmp_path, auto_mine_off):
    auto_mine_off.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    video = _make_video(db_session, tmp_path)
    Path(video.local_file_path).unlink()

    ok, reason = AutoMineService.should_mine(video)
    assert ok is False
    assert "missing" in reason


# ------------------------------------------------------------- top-n rules


def test_resolve_top_n_uses_auto_stage_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_AUTO_RENDER_TOP_N", None)
    monkeypatch.setattr(settings, "AUTO_STAGE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_STAGE_TOP_N", 4)

    assert AutoMineService.resolve_top_n() == 4


def test_resolve_top_n_zero_when_staging_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_AUTO_RENDER_TOP_N", None)
    monkeypatch.setattr(settings, "AUTO_STAGE_ENABLED", False)

    assert AutoMineService.resolve_top_n() == 0


def test_resolve_top_n_explicit_override(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_AUTO_RENDER_TOP_N", 7)
    monkeypatch.setattr(settings, "AUTO_STAGE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_STAGE_TOP_N", 2)

    assert AutoMineService.resolve_top_n() == 7


def test_resolve_game_prefers_explicit_setting(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_GAME", "fall_guys")
    video = Video(id="x", title="Whatever")

    assert AutoMineService.resolve_game(video) == "fall_guys"


def test_resolve_game_defers_to_registry_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_GAME", None)
    video = Video(id="x", title="Marvel Rivals ranked")

    # None means "let the detector registry auto-detect from metadata"
    assert AutoMineService.resolve_game(video) is None


# ----------------------------------------------------------- dispatch


def test_trigger_dispatches_detection_when_enabled(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    monkeypatch.setattr(settings, "AUTO_MINE_AUTO_RENDER_TOP_N", 3)
    monkeypatch.setattr(settings, "AUTO_MINE_MIN_SCORE", 0.55)
    video = _make_video(db_session, tmp_path)

    captured: dict = {}

    def fake_detect_highlights(db, video_id, request=None, background_tasks=None):
        captured["video_id"] = video_id
        captured["request"] = request

        class _Resp:
            status = "pending"
            run_id = "hrun_test"
            task_id = "task_test"

        return _Resp()

    import app.services.highlight.service as hl_service

    monkeypatch.setattr(
        hl_service.HighlightService, "detect_highlights", fake_detect_highlights
    )

    result = AutoMineService.trigger_after_ingest(db_session, video.id)

    assert result["triggered"] is True
    assert result["run_id"] == "hrun_test"
    assert result["auto_render_top_n"] == 3
    assert captured["video_id"] == video.id
    assert captured["request"].min_score == 0.55
    assert captured["request"].auto_render_top_n == 3


def test_trigger_never_raises_on_detection_failure(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    video = _make_video(db_session, tmp_path)

    import app.services.highlight.service as hl_service

    def boom(*args, **kwargs):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(hl_service.HighlightService, "detect_highlights", boom)

    result = AutoMineService.trigger_after_ingest(db_session, video.id)

    assert result["triggered"] is False
    assert "exploded" in result["reason"]


# ------------------------------------------------- download job chain


def test_download_job_triggers_auto_mine(db_session, tmp_path, monkeypatch):
    """A finished download must hand off to auto-mine without extra clicks."""
    monkeypatch.setattr(settings, "AUTO_MINE_ON_INGEST", True)
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(tmp_path / "downloads"))

    video = Video(
        id="vid_dl",
        title="Marvel Rivals VOD",
        webpage_url="https://youtube.com/watch?v=vid_dl",
    )
    db_session.add(video)
    db_session.commit()

    downloaded = tmp_path / "vid_dl.mp4"
    _make_clip(downloaded)

    monkeypatch.setattr(
        auto_mine_module.AutoMineService,
        "trigger_after_ingest",
        classmethod(
            lambda cls, db, video_id, background_tasks=None: {
                "triggered": True,
                "video_id": video_id,
            }
        ),
    )

    import app.services.youtube as yt_module

    monkeypatch.setattr(
        yt_module.YtdlpService,
        "download_video",
        staticmethod(
            lambda video_id, quality=None, progress_callback=None: {
                "local_file_path": str(downloaded),
                "file_size_bytes": downloaded.stat().st_size,
            }
        ),
    )

    result = VideoService.execute_download_job(video_id="vid_dl", db_session=db_session)

    assert result["status"] == "completed"
    db_session.refresh(video)
    assert video.download_status == "completed"
