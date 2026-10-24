"""Tests for Phase 8 automation: auto-stage, LLM metadata, quota and publishing schedules."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.highlight_candidate import HighlightCandidate
from app.models.render_job import RenderJob
from app.models.video import Video
from app.models.youtube_quota import YouTubeQuotaUsage
from app.schemas.youtube import YouTubeAuthStatusResponse
from app.services.auto_stage import AutoStageService
from app.services.llm_metadata import LLMMetadataService
from app.services.renders import RenderService
from app.services.youtube_quota import QuotaExceededError, YouTubeQuotaService
from app.services.youtube_uploader import YouTubeUploaderService

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


def _video(db, video_id="vid_phase8"):
    video = Video(
        id=video_id,
        title="Marvel Rivals Ranked Grind",
        channel_name="Chris Gaming",
        webpage_url=f"https://youtube.com/watch?v={video_id}",
        is_downloaded=True,
        download_status="completed",
    )
    db.add(video)
    db.commit()
    return video


def _candidate(db, video, candidate_id, score, start=100.0):
    candidate = HighlightCandidate(
        id=candidate_id,
        video_id=video.id,
        start_seconds=start,
        end_seconds=start + 20.0,
        duration_seconds=20.0,
        score=score,
        event_type="team_wipe",
        game="marvel_rivals",
        details_json=json.dumps(
            {
                "kill_count": 4,
                "multi_kill_chain": 4,
                "hero_name": "luna_snow",
                "has_ultimate": True,
                "game_phase": "regular",
                "trigger_events": [{"time": start, "label": "QUAD KO"}],
            }
        ),
        peak_timestamp=start + 5.0,
    )
    db.add(candidate)
    db.commit()
    return candidate


# -----------------------------------------------------------------------------
# LLM metadata
# -----------------------------------------------------------------------------


def test_llm_metadata_falls_back_without_api_key(db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", True)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    video = _video(db_session)
    metadata = LLMMetadataService.generate_clip_metadata(
        video=video,
        clip_id="clip_fallback",
        preferred_format="vertical_blur",
    )

    assert metadata["metadata_source"] == "fallback"
    assert metadata["title"]
    assert "Shorts" in metadata["tags"]


def test_llm_metadata_uses_gemini_output(db_session, monkeypatch):
    video = _video(db_session)
    monkeypatch.setattr(LLMMetadataService, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(
        LLMMetadataService,
        "_call_gemini",
        staticmethod(
            lambda prompt: {
                "title": '"Luna Snow Quad Kill Freeze"',
                "description": "Four frozen in one ult.",
                "tags": ["#LunaSnow", "MarvelRivals", "MarvelRivals"],
            }
        ),
    )

    metadata = LLMMetadataService.generate_clip_metadata(
        video=video,
        clip_id="clip_llm",
        preferred_format="vertical_blur",
    )

    assert metadata["metadata_source"] == "llm"
    assert metadata["title"] == "Luna Snow Quad Kill Freeze"
    assert metadata["tags"].count("MarvelRivals") == 1
    assert "Shorts" in metadata["tags"]
    assert "#" in metadata["description"]


def test_llm_metadata_falls_back_when_gemini_fails(db_session, monkeypatch):
    video = _video(db_session)
    monkeypatch.setattr(LLMMetadataService, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(
        LLMMetadataService, "_call_gemini", staticmethod(lambda prompt: None)
    )

    metadata = LLMMetadataService.generate_clip_metadata(
        video=video, clip_id="clip_fail", preferred_format="vertical_blur"
    )
    assert metadata["metadata_source"] == "fallback"


# -----------------------------------------------------------------------------
# Quota accounting
# -----------------------------------------------------------------------------


def test_quota_reserves_six_uploads_then_blocks(db_session):
    summary = YouTubeQuotaService.get_summary(db_session)
    assert summary["daily_limit_units"] == 10_000
    assert summary["uploads_remaining"] == 6
    assert summary["can_upload"] is True

    for index in range(6):
        YouTubeQuotaService.reserve_upload(db_session)
        expected = 5 - index
        assert (
            YouTubeQuotaService.get_summary(db_session)["uploads_remaining"]
            == expected
        )

    summary = YouTubeQuotaService.get_summary(db_session)
    assert summary["units_used"] == 9_600
    assert summary["can_upload"] is False

    with pytest.raises(QuotaExceededError):
        YouTubeQuotaService.reserve_upload(db_session)


def test_quota_reset_day_rolls_over(db_session):
    first_day = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    second_day = first_day + timedelta(days=1)
    YouTubeQuotaService.reserve_upload(db_session)

    assert YouTubeQuotaService.quota_day(first_day) != YouTubeQuotaService.quota_day(
        second_day
    )
    today = YouTubeQuotaService.quota_day()
    assert db_session.query(YouTubeQuotaUsage).filter_by(day=today).count() == 1


def test_quota_endpoint(client, db_session):
    YouTubeQuotaService.reserve_upload(db_session)
    res = client.get(f"{settings.API_PREFIX}/youtube/quota")
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["units_used"] == 1_600
    assert body["uploads_remaining"] == 5
    assert body["resets_at"]


# -----------------------------------------------------------------------------
# Auto-stage
# -----------------------------------------------------------------------------


def test_auto_stage_creates_staggered_jobs(client, db_session, monkeypatch):
    video = _video(db_session)
    low = _candidate(db_session, video, "cand_low", 0.55)
    high = _candidate(db_session, video, "cand_high", 0.95, start=200.0)

    def fake_create_render(db, request, background_tasks=None):
        job = RenderJob(
            id=f"job_{request.clip_id}",
            clip_id=request.clip_id,
            video_id=request.video_id,
            status="completed",
            progress=100.0,
            start_seconds=request.start_seconds,
            duration_seconds=request.duration_seconds,
            modes=",".join(request.modes or []),
            selected_format=(request.modes or ["third_person"])[0],
        )
        db.add(job)
        db.commit()

        class Rendered:
            job_id = job.id

        return Rendered()

    monkeypatch.setattr(
        RenderService, "create_render", staticmethod(fake_create_render)
    )
    monkeypatch.setattr(
        LLMMetadataService,
        "generate_clip_metadata",
        staticmethod(
            lambda **kwargs: {
                "title": "Auto Staged Clip",
                "description": "Auto copy",
                "tags": ["Gaming"],
                "preferred_format": "third_person",
                "privacy": "public",
                "metadata_source": "llm",
            }
        ),
    )

    result = AutoStageService.stage_top_candidates(
        db_session,
        video.id,
        top_n=2,
        min_score=0.6,
        clipping_mode="third_person",
        schedule=True,
    )

    assert result["staged_count"] == 1
    assert result["clips"][0]["candidate_id"] == high.id
    assert low.id not in {c["candidate_id"] for c in result["clips"]}

    job = db_session.query(RenderJob).filter_by(clip_id=f"auto_{high.id}").one()
    assert job.auto_staged is True
    assert job.highlight_candidate_id == high.id
    assert job.scheduled_publish_at is not None
    assert job.is_selected_for_upload is True

    scheduled = job.scheduled_publish_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=UTC)
    assert scheduled > datetime.now(UTC)

    metadata = json.loads(job.upload_metadata)
    assert metadata["metadata_source"] == "llm"
    assert metadata["scheduled_publish_at"] is not None


def test_auto_stage_is_idempotent(client, db_session, monkeypatch):
    video = _video(db_session, "vid_idem")
    candidate = _candidate(db_session, video, "cand_idem", 0.9)

    def fake_create_render(db, request, background_tasks=None):
        job = RenderJob(
            id=f"job_{request.clip_id}",
            clip_id=request.clip_id,
            video_id=request.video_id,
            status="completed",
            progress=100.0,
            start_seconds=request.start_seconds,
            duration_seconds=request.duration_seconds,
        )
        db.add(job)
        db.commit()

        class Rendered:
            job_id = job.id

        return Rendered()

    monkeypatch.setattr(
        RenderService, "create_render", staticmethod(fake_create_render)
    )
    monkeypatch.setattr(
        LLMMetadataService,
        "generate_clip_metadata",
        staticmethod(
            lambda **kwargs: {
                "title": "Idem",
                "description": "Idem",
                "tags": [],
                "preferred_format": "third_person",
                "privacy": "public",
                "metadata_source": "fallback",
            }
        ),
    )

    first = AutoStageService.stage_top_candidates(
        db_session, video.id, top_n=5, min_score=0.1, schedule=False
    )
    second = AutoStageService.stage_top_candidates(
        db_session, video.id, top_n=5, min_score=0.1, schedule=False
    )

    assert first["staged_count"] == 1
    assert second["staged_count"] == 0
    assert db_session.query(RenderJob).count() == 1
    assert candidate.id


def test_auto_stage_endpoint_and_staging_list(client, db_session, monkeypatch):
    video = _video(db_session, "vid_api_stage")
    _candidate(db_session, video, "cand_api_stage", 0.88)

    def fake_create_render(db, request, background_tasks=None):
        job = RenderJob(
            id=f"job_{request.clip_id}",
            clip_id=request.clip_id,
            video_id=request.video_id,
            status="completed",
            progress=100.0,
            start_seconds=request.start_seconds,
            duration_seconds=request.duration_seconds,
        )
        db.add(job)
        db.commit()

        class Rendered:
            job_id = job.id

        return Rendered()

    monkeypatch.setattr(
        RenderService, "create_render", staticmethod(fake_create_render)
    )
    monkeypatch.setattr(
        LLMMetadataService,
        "generate_clip_metadata",
        staticmethod(
            lambda **kwargs: {
                "title": "API Staged",
                "description": "API",
                "tags": ["Gaming"],
                "preferred_format": "third_person",
                "privacy": "private",
                "metadata_source": "llm",
            }
        ),
    )

    res = client.post(
        f"{settings.API_PREFIX}/youtube/auto-stage",
        json={
            "video_id": video.id,
            "top_n": 1,
            "min_score": 0.5,
            "clipping_mode": "third_person",
            "schedule": True,
        },
    )
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["staged_count"] == 1
    assert data["clips"][0]["scheduled_publish_at"]

    staging = client.get(f"{settings.API_PREFIX}/youtube/staging")
    assert staging.status_code == 200
    payload = staging.json()["response"]
    assert payload["total"] == 1
    assert payload["items"][0]["auto_staged"] is True
    assert payload["quota"]["can_upload"] is True


# -----------------------------------------------------------------------------
# Scheduling & native publishAt
# -----------------------------------------------------------------------------


def test_schedule_endpoint_sets_and_clears_publish_at(client, db_session):
    video = _video(db_session, "vid_sched")
    job = RenderJob(
        id="job_sched",
        clip_id="clip_sched",
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=20.0,
        auto_staged=True,
        is_selected_for_upload=True,
    )
    db_session.add(job)
    db_session.commit()

    future = (datetime.now(UTC) + timedelta(hours=5)).isoformat()
    res = client.post(
        f"{settings.API_PREFIX}/youtube/staging/clip_sched/schedule",
        json={"publish_at": future},
    )
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["scheduled_publish_at"] is not None

    db_session.refresh(job)
    assert job.scheduled_publish_at is not None

    cleared = client.post(
        f"{settings.API_PREFIX}/youtube/staging/clip_sched/schedule",
        json={"publish_at": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["response"]["scheduled_publish_at"] is None


def test_schedule_endpoint_rejects_past(client, db_session):
    video = _video(db_session, "vid_past")
    job = RenderJob(
        id="job_past",
        clip_id="clip_past",
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=10.0,
    )
    db_session.add(job)
    db_session.commit()

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    res = client.post(
        f"{settings.API_PREFIX}/youtube/staging/clip_past/schedule",
        json={"publish_at": past},
    )
    assert res.status_code == 400


def _prepare_scheduled_upload(db_session, tmp_path, monkeypatch, clip_id):
    clip_dir = tmp_path / clip_id
    clip_dir.mkdir(parents=True)
    (clip_dir / "vertical_blur.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"
    )
    manifest = {
        "clip_id": clip_id,
        "clip": {"start_seconds": 0.0, "duration_seconds": 25.0},
        "upload_selection": {
            "title": "Scheduled Clip",
            "description": "Scheduled copy",
            "tags": ["Gaming"],
            "privacy": "private",
            "preferred_format": "vertical_blur",
        },
    }
    (clip_dir / "manifest.json").write_text(json.dumps(manifest))

    video = _video(db_session, f"vid_{clip_id}")
    job = RenderJob(
        id=f"job_{clip_id}",
        clip_id=clip_id,
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=25.0,
        selected_format="vertical_blur",
        is_selected_for_upload=True,
        auto_staged=True,
        scheduled_publish_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_auth_status",
        lambda: YouTubeAuthStatusResponse(is_authenticated=True),
    )
    monkeypatch.setattr(YouTubeUploaderService, "get_credentials", lambda: MagicMock())

    mock_insert = MagicMock()
    mock_status = MagicMock()
    mock_status.progress.return_value = 1.0
    mock_insert.next_chunk.return_value = (mock_status, {"id": "yt_scheduled_1"})
    mock_videos = MagicMock()
    mock_videos.insert.return_value = mock_insert
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value = mock_videos
    monkeypatch.setattr(
        "app.services.youtube_uploader.build", lambda *a, **kw: mock_youtube
    )
    return job, mock_videos


def test_upload_uses_publish_at_and_private_privacy(
    client, db_session, tmp_path, monkeypatch
):
    clip_id = "clip_scheduled_1"
    job, mock_videos = _prepare_scheduled_upload(
        db_session, tmp_path, monkeypatch, clip_id
    )

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/{clip_id}", json={"sync": True}
    )
    assert res.status_code == 200
    result = res.json()["response"]
    assert result["scheduled_publish_at"] is not None
    assert result["privacy"] == "private"

    body = mock_videos.insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == "private"
    assert "publishAt" in body["status"]
    assert body["status"]["publishAt"].endswith("Z")

    db_session.refresh(job)
    assert job.youtube_upload_status == "completed"
    assert job.scheduled_publish_at is not None

    usage = db_session.query(YouTubeQuotaUsage).one()
    assert usage.units_used == 1_600


def test_upload_blocked_when_quota_exhausted(client, db_session, monkeypatch):
    video = _video(db_session, "vid_quota_guard")
    job = RenderJob(
        id="job_quota_guard",
        clip_id="whatever_clip",
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=10.0,
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_auth_status",
        lambda: YouTubeAuthStatusResponse(is_authenticated=True),
    )
    for _ in range(6):
        YouTubeQuotaService.reserve_upload(db_session)

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/whatever_clip", json={}
    )
    assert res.status_code == 429
    assert "quota" in res.json()["error_message"].lower()


# -----------------------------------------------------------------------------
# Highlight detection request plumbing
# -----------------------------------------------------------------------------


def test_detect_request_passes_auto_render_top_n(client, db_session, monkeypatch, tmp_path):
    source = tmp_path / "src.mp4"
    source.write_bytes(b"dummy")
    video = Video(
        id="vod_auto_stage",
        title="Marvel Rivals Ranked",
        webpage_url="https://youtube.com/watch?v=vod_auto_stage",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(source),
    )
    db_session.add(video)
    db_session.commit()

    captured = {}

    def fake_execute(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "count": 0, "auto_staged_count": 0}

    monkeypatch.setattr(
        "app.services.highlight.service.execute_highlight_detection_job",
        fake_execute,
    )

    res = client.post(
        f"{settings.API_PREFIX}/videos/vod_auto_stage/highlights/detect",
        json={"sync": True, "auto_render_top_n": 3, "clipping_mode": "direct_crop"},
    )
    assert res.status_code == 200
    assert captured["auto_render_top_n"] == 3
    assert captured["clipping_mode"] == "direct_crop"
