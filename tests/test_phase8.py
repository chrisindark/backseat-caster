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
from app.services.youtube_quota import YouTubeQuotaService
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


def test_quota_reserves_six_uploads_then_allows_overflow(db_session):
    summary = YouTubeQuotaService.get_summary(db_session)
    assert summary["daily_limit_units"] == 10_000
    assert summary["uploads_remaining"] == 6
    assert summary["can_upload"] is True

    for index in range(6):
        YouTubeQuotaService.reserve_upload(db_session)
        expected = 5 - index
        assert (
            YouTubeQuotaService.get_summary(db_session)["uploads_remaining"] == expected
        )

    summary = YouTubeQuotaService.get_summary(db_session)
    assert summary["units_used"] == 9_600
    assert summary["can_upload"] is False

    # Over-budget uploads are advisory: recording keeps counting beyond the
    # daily budget so the quota bar stays accurate. YouTube enforces the limit.
    summary = YouTubeQuotaService.reserve_upload(db_session)
    assert summary["can_upload"] is False
    assert summary["uploads_remaining"] == 0
    assert summary["uploads_today"] == 7


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


def test_upload_allowed_over_quota_with_warning(
    client, db_session, tmp_path, monkeypatch
):
    """An exhausted daily budget dispatches the upload instead of returning 429."""
    clip_id = "clip_quota_warn"
    job, mock_videos = _prepare_scheduled_upload(
        db_session, tmp_path, monkeypatch, clip_id
    )
    for _ in range(6):
        YouTubeQuotaService.reserve_upload(db_session)

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/{clip_id}", json={"sync": True}
    )
    assert res.status_code == 200
    assert mock_videos.insert.called

    usage = (
        db_session.query(YouTubeQuotaUsage)
        .filter_by(day=YouTubeQuotaService.quota_day())
        .one()
    )
    assert usage.units_used == 11_200
    assert usage.uploads_count == 7
    assert res.json()["response"]["status"] == "completed"


# -----------------------------------------------------------------------------
# Highlight detection request plumbing
# -----------------------------------------------------------------------------


def test_detect_request_passes_auto_render_top_n(
    client, db_session, monkeypatch, tmp_path
):
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


# -----------------------------------------------------------------------------
# Regenerate metadata (AI vs deterministic copy comparison)
# -----------------------------------------------------------------------------


def _staged_clip(db, video, clip_id, job_id, title="Original staged title"):
    scheduled = datetime.now(UTC) + timedelta(hours=6)
    job = RenderJob(
        id=job_id,
        clip_id=clip_id,
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=120.0,
        duration_seconds=30.0,
        selected_format="vertical_blur",
        is_selected_for_upload=True,
        auto_staged=True,
        scheduled_publish_at=scheduled,
        upload_metadata=json.dumps(
            {
                "is_selected": True,
                "preferred_format": "vertical_blur",
                "title": title,
                "description": "Original description #Shorts",
                "tags": ["Gaming", "Shorts"],
                "privacy": "private",
                "metadata_source": "llm",
            }
        ),
    )
    db.add(job)
    db.commit()
    return job


def test_regenerate_metadata_deterministic(client, db_session):
    video = _video(db_session, "vid_regen")
    job = _staged_clip(db_session, video, "clip_regen", "job_regen")

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_regen/regenerate-metadata",
        json={"use_llm": False},
    )
    assert res.status_code == 200
    body = res.json()["response"]

    assert body["metadata_source"] == "fallback"
    assert body["used_llm"] is False
    # Fresh deterministic copy replaces the staged copy...
    assert body["upload_selection"]["title"] != "Original staged title"
    assert body["upload_selection"]["title"]
    assert body["upload_selection"]["tags"]
    # ...and the replaced copy is returned for side-by-side comparison.
    assert body["previous"]["title"] == "Original staged title"

    db_session.refresh(job)
    meta = json.loads(job.upload_metadata)
    assert meta["metadata_source"] == "fallback"
    assert meta["privacy"] == "private"
    assert meta["scheduled_publish_at"] is not None
    assert meta["previous_metadata"]["title"] == "Original staged title"
    # Selection, schedule and render are untouched.
    assert job.is_selected_for_upload is True
    assert job.scheduled_publish_at is not None
    assert job.status == "completed"


def test_regenerate_metadata_with_llm(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        LLMMetadataService,
        "_call_gemini",
        staticmethod(
            lambda prompt: {
                "title": "AI generated Short",
                "description": "AI hook line\n\n#Shorts #MarvelRivals",
                "tags": ["marvelrivals", "shorts"],
            }
        ),
    )

    video = _video(db_session, "vid_regen_ai")
    job = _staged_clip(db_session, video, "clip_regen_ai", "job_regen_ai")

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_regen_ai/regenerate-metadata",
        json={"use_llm": True},
    )
    assert res.status_code == 200
    body = res.json()["response"]

    assert body["metadata_source"] == "llm"
    assert body["used_llm"] is True
    assert body["llm_available"] is True
    assert body["upload_selection"]["title"] == "AI generated Short"
    assert body["previous"]["title"] == "Original staged title"

    db_session.refresh(job)
    meta = json.loads(job.upload_metadata)
    assert meta["title"] == "AI generated Short"
    assert meta["metadata_source"] == "llm"


def test_regenerate_metadata_llm_without_key_falls_back(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", True)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    video = _video(db_session, "vid_regen_nokey")
    _staged_clip(db_session, video, "clip_regen_nokey", "job_regen_nokey")

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_regen_nokey/regenerate-metadata",
        json={"use_llm": True},
    )
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["metadata_source"] == "fallback"
    assert body["used_llm"] is False
    assert body["llm_available"] is False


def test_regenerate_metadata_defaults_to_server_config(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    video = _video(db_session, "vid_regen_cfg")
    _staged_clip(db_session, video, "clip_regen_cfg", "job_regen_cfg")

    # No body: follows LLM_METADATA_ENABLED (disabled here) -> deterministic.
    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_regen_cfg/regenerate-metadata", json={}
    )
    assert res.status_code == 200
    assert res.json()["response"]["metadata_source"] == "fallback"
    assert res.json()["response"]["llm_available"] is True


def test_regenerate_metadata_unknown_clip(client):
    res = client.post(
        f"{settings.API_PREFIX}/renders/no_such_clip/regenerate-metadata",
        json={"use_llm": False},
    )
    assert res.status_code == 404


def test_staging_response_reports_llm_availability(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _video(db_session, "vid_staging_llm")

    res = client.get(f"{settings.API_PREFIX}/youtube/staging")
    assert res.status_code == 200
    assert res.json()["response"]["llm_available"] is True


def test_llm_metadata_parses_markdown_fences_and_parsed_object(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    class MockModel:
        def model_dump(self):
            return {
                "title": "Parsed Title",
                "description": "Parsed Desc",
                "tags": ["hero", "game"],
            }

    class MockResponseParsed:
        parsed = MockModel()
        text = "ignored text"

    # 1. Test SDK parsed attribute takes priority
    monkeypatch.setattr(
        "google.genai.Client",
        lambda api_key: type(
            "C",
            (),
            {
                "models": type(
                    "M",
                    (),
                    {"generate_content": lambda *args, **kwargs: MockResponseParsed()},
                )()
            },
        )(),
    )
    result = LLMMetadataService._call_gemini("test prompt")
    assert result is not None
    assert result["title"] == "Parsed Title"

    # 2. Test markdown-fenced text parsing
    class MockResponseFenced:
        parsed = None
        text = '```json\n{"title": "Fenced Title", "description": "Fenced Desc", "tags": ["fenced"]}\n```'

    monkeypatch.setattr(
        "google.genai.Client",
        lambda api_key: type(
            "C",
            (),
            {
                "models": type(
                    "M",
                    (),
                    {"generate_content": lambda *args, **kwargs: MockResponseFenced()},
                )()
            },
        )(),
    )
    result = LLMMetadataService._call_gemini("test prompt")
    assert result is not None
    assert result["title"] == "Fenced Title"


def test_regenerate_metadata_with_explicit_hero_and_context(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", True)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    captured_prompt = {}

    def mock_call_gemini(prompt: str):
        captured_prompt["prompt"] = prompt
        return {
            "title": "Magneto 5K Defense",
            "description": "Magneto wipes team on payload.\n\n#Shorts #Magneto",
            "tags": ["magneto", "shorts"],
        }

    monkeypatch.setattr(
        LLMMetadataService, "_call_gemini", staticmethod(mock_call_gemini)
    )

    video = _video(db_session, "vid_hero_test")
    _staged_clip(db_session, video, "clip_hero_test", "job_hero_test")

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_hero_test/regenerate-metadata",
        json={
            "use_llm": True,
            "hero_name": "Magneto",
            "clip_context": "5k defense holding point B",
        },
    )
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["used_llm"] is True
    assert body["upload_selection"]["title"] == "Magneto 5K Defense"
    assert body["upload_selection"]["hero_name"] == "Magneto"
    assert body["upload_selection"]["clip_context"] == "5k defense holding point B"

    # Verify that the LLM prompt received hero and context
    assert "Hero: Magneto" in captured_prompt["prompt"]
    assert "Extra context: 5k defense holding point B" in captured_prompt["prompt"]


def test_regenerate_metadata_deterministic_uses_hero_context_and_tags(
    client, db_session
):
    """Deterministic copy incorporates hero name, clip context, candidate tags, and suggested title without LLM."""
    from app.models.highlight_candidate import HighlightCandidate

    video = _video(db_session, "vid_det_rich")
    cand = HighlightCandidate(
        id="cand_det_rich_1",
        video_id=video.id,
        start_seconds=150.0,
        end_seconds=185.0,
        duration_seconds=35.0,
        score=0.99,
        event_type="team_wipe",
        game="Marvel Rivals",
        suggested_title="Insane Team Wipe Ultimate! 💥 #MarvelRivals",
        suggested_tags_json=json.dumps(
            ["Marvel Rivals", "team wipe", "Venom", "Shorts"]
        ),
        details_json=json.dumps(
            {
                "hero_name": "Venom",
                "is_team_wipe": True,
                "kill_count": 5,
            }
        ),
    )
    db_session.add(cand)
    db_session.commit()

    job = _staged_clip(db_session, video, "clip_det_rich", "job_det_rich")
    job.highlight_candidate_id = "cand_det_rich_1"
    job.start_seconds = 150.0
    job.duration_seconds = 35.0
    db_session.commit()

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_det_rich/regenerate-metadata",
        json={
            "use_llm": False,
            "hero_name": "Venom",
            "clip_context": "clutch team wipe holding choke point B",
            "game": "Marvel Rivals",
        },
    )
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["used_llm"] is False
    assert body["metadata_source"] == "fallback"

    sel = body["upload_selection"]
    # 1. Title features the hero!
    assert "Venom" in sel["title"]
    assert "Team Wipe" in sel["title"]
    assert "#MarvelRivals" in sel["title"]

    # 2. Description features the hero and context!
    assert "Venom" in sel["description"]
    assert "clutch team wipe holding choke point B" in sel["description"]
    assert "#Shorts" in sel["description"]
    assert "#MarvelRivals" in sel["description"]

    # 3. Tags include candidate tags, hero and game!
    tags = sel["tags"]
    assert "Venom" in tags
    assert "Marvel Rivals" in tags
    assert "team wipe" in tags
    assert "Shorts" in tags
    assert sel["hero_name"] == "Venom"
    assert sel["clip_context"] == "clutch team wipe holding choke point B"


def test_regenerate_metadata_auto_matches_candidate_by_timestamp(
    client, db_session, monkeypatch
):
    from app.models.highlight_candidate import HighlightCandidate

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_METADATA_ENABLED", True)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    captured_prompt = {}

    def mock_call_gemini(prompt: str):
        captured_prompt["prompt"] = prompt
        return {
            "title": "Penta Kill Streak",
            "description": "Insane 5 kill streak!\n\n#Shorts #Gaming",
            "tags": ["penta", "shorts"],
        }

    monkeypatch.setattr(
        LLMMetadataService, "_call_gemini", staticmethod(mock_call_gemini)
    )

    video = _video(db_session, "vid_auto_cand")
    # Candidate at 100.0s - 130.0s with 4 kills
    cand = HighlightCandidate(
        id="cand_auto_123",
        video_id=video.id,
        start_seconds=100.0,
        end_seconds=130.0,
        duration_seconds=30.0,
        score=0.95,
        event_type="kill_streak",
        details_json=json.dumps(
            {
                "kill_count": 4,
                "streak_count": 5,
                "multi_kill_chain": "Quad KO",
                "trigger_events": [{"label": "QUAD KO", "time": 115.0}],
            }
        ),
    )
    db_session.add(cand)
    db_session.commit()

    # Staged clip at 102.0s with duration 25.0s, highlight_candidate_id=None
    job = _staged_clip(db_session, video, "clip_auto_cand", "job_auto_cand")
    job.start_seconds = 102.0
    job.duration_seconds = 25.0
    job.highlight_candidate_id = None
    db_session.commit()

    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_auto_cand/regenerate-metadata",
        json={"use_llm": True},
    )
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["upload_selection"]["highlight_candidate_id"] == "cand_auto_123"

    # Prompt now has the real mined candidate kills, streak, and trigger events!
    assert "Kills in clip: 4" in captured_prompt["prompt"]
    assert "Player streak: 5" in captured_prompt["prompt"]
    assert "Trigger events: QUAD KO" in captured_prompt["prompt"]


def test_next_publish_slot_daily_slots_ist(db_session, monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(settings, "AUTO_STAGE_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr(
        settings,
        "AUTO_STAGE_DAILY_SLOTS",
        ["08:00", "12:30", "16:00", "18:30", "20:30", "23:00"],
    )

    ist = ZoneInfo("Asia/Kolkata")
    # Reference: 2026-10-25 07:00:00 IST (01:30:00 UTC)
    ref_ist = datetime(2026, 10, 25, 7, 0, 0, tzinfo=ist)
    ref_utc = ref_ist.astimezone(UTC)

    # 1. First slot should be today at 08:00 IST
    slot1 = AutoStageService.next_publish_slot(db_session, now=ref_utc)
    slot1_ist = slot1.astimezone(ist)
    assert slot1_ist.hour == 8
    assert slot1_ist.minute == 0
    assert slot1_ist.day == 25

    # 2. Next slot after slot1 should be 12:30 IST
    slot2 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot1)
    slot2_ist = slot2.astimezone(ist)
    assert slot2_ist.hour == 12
    assert slot2_ist.minute == 30
    assert slot2_ist.day == 25

    # 3. Next slots: 16:00, 18:30, 20:30, 23:00
    slot3 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot2)
    assert slot3.astimezone(ist).hour == 16

    slot4 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot3)
    assert slot4.astimezone(ist).hour == 18
    assert slot4.astimezone(ist).minute == 30

    slot5 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot4)
    assert slot5.astimezone(ist).hour == 20
    assert slot5.astimezone(ist).minute == 30

    slot6 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot5)
    assert slot6.astimezone(ist).hour == 23
    assert slot6.astimezone(ist).minute == 0
    assert slot6.astimezone(ist).day == 25

    # 4. Rolling over to next day after 23:00 should pick tomorrow at 08:00 IST
    slot7 = AutoStageService.next_publish_slot(db_session, now=ref_utc, after=slot6)
    slot7_ist = slot7.astimezone(ist)
    assert slot7_ist.hour == 8
    assert slot7_ist.minute == 0
    assert slot7_ist.day == 26


def test_next_publish_slot_skips_booked_slots(db_session, monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(settings, "AUTO_STAGE_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr(
        settings,
        "AUTO_STAGE_DAILY_SLOTS",
        ["08:00", "12:30", "16:00"],
    )

    ist = ZoneInfo("Asia/Kolkata")
    ref_utc = datetime(2026, 10, 25, 7, 0, 0, tzinfo=ist).astimezone(UTC)
    booked_0800 = datetime(2026, 10, 25, 8, 0, 0, tzinfo=ist).astimezone(UTC)

    # Book 08:00 slot in database
    job = RenderJob(
        id="job_booked_slot",
        clip_id="clip_booked_slot",
        video_id="vid_test",
        status="completed",
        start_seconds=10.0,
        duration_seconds=15.0,
        scheduled_publish_at=booked_0800,
    )
    db_session.add(job)
    db_session.commit()

    # Next slot should skip 08:00 and select 12:30
    slot = AutoStageService.next_publish_slot(db_session, now=ref_utc)
    slot_ist = slot.astimezone(ist)
    assert slot_ist.hour == 12
    assert slot_ist.minute == 30
    assert slot_ist.day == 25


def test_llm_metadata_prompt_requests_emojis():
    from app.services.llm_metadata import _METADATA_PROMPT

    assert (
        "gaming action emojis" in _METADATA_PROMPT
        or "gaming emojis" in _METADATA_PROMPT
    )
    assert "No emojis" not in _METADATA_PROMPT
