"""Tests for the maintenance pipeline: uploaded-render cleanup and batch staging."""

import json

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
from app.services.auto_pipeline import AutoPipelineService
from app.services.auto_stage import AutoStageService
from app.services.llm_metadata import LLMMetadataService
from app.services.renders import RenderService

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
def storage(tmp_path, monkeypatch):
    """Point render/download storage at a throwaway directory."""
    renders = tmp_path / "renders"
    downloads = tmp_path / "downloads"
    renders.mkdir(parents=True)
    downloads.mkdir(parents=True)
    monkeypatch.setattr(settings, "RENDERS_DIR", str(renders))
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(downloads))
    return renders, downloads


def _video(db, video_id, vod_path=None):
    video = Video(
        id=video_id,
        title=f"Video {video_id}",
        channel_name="Chris Gaming",
        webpage_url=f"https://youtube.com/watch?v={video_id}",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(vod_path) if vod_path else None,
    )
    db.add(video)
    db.commit()
    return video


def _job(db, video, clip_id, uploaded=False):
    job = RenderJob(
        id=f"job_{clip_id}",
        clip_id=clip_id,
        video_id=video.id,
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=20.0,
        youtube_upload_status="completed" if uploaded else "not_uploaded",
        youtube_upload_url=(
            f"https://www.youtube.com/shorts/{clip_id}" if uploaded else None
        ),
    )
    db.add(job)
    db.commit()
    return job


def _candidate(db, video, candidate_id, score, start):
    candidate = HighlightCandidate(
        id=candidate_id,
        video_id=video.id,
        start_seconds=start,
        end_seconds=start + 20.0,
        duration_seconds=20.0,
        score=score,
        event_type="team_wipe",
        game="marvel_rivals",
        details_json=json.dumps({"kill_count": 4}),
        peak_timestamp=start + 5.0,
    )
    db.add(candidate)
    db.commit()
    return candidate


def _fake_render_and_metadata(monkeypatch):
    def fake_create_render(db, request, background_tasks=None):
        job = RenderJob(
            id=f"job_{request.clip_id}",
            clip_id=request.clip_id,
            video_id=request.video_id,
            status="completed",
            progress=100.0,
            start_seconds=request.start_seconds,
            duration_seconds=request.duration_seconds,
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
                "title": "Swept Clip",
                "description": "Swept copy",
                "tags": ["Gaming"],
                "preferred_format": "third_person",
                "privacy": "public",
                "metadata_source": "fallback",
            }
        ),
    )


def test_cleanup_uploaded_renders_keeps_records_and_pending_vod(db_session, storage):
    renders, downloads = storage
    vod = downloads / "vid_clean.mp4"
    vod.write_bytes(b"0" * 1000)

    uploaded_dir = renders / "clip_uploaded"
    uploaded_dir.mkdir()
    (uploaded_dir / "vertical_blur.mp4").write_bytes(b"0" * 2048)

    pending_dir = renders / "clip_pending"
    pending_dir.mkdir()
    (pending_dir / "vertical_blur.mp4").write_bytes(b"0" * 1024)

    video = _video(db_session, "vid_clean", vod)
    _job(db_session, video, "clip_uploaded", uploaded=True)
    _job(db_session, video, "clip_pending", uploaded=False)

    result = AutoPipelineService.cleanup_uploaded_renders(db_session, clean_vod=True)

    assert result["clips_cleaned"] == 1
    assert result["bytes_reclaimed"] == 2048
    assert result["vod_deleted_count"] == 0
    assert not uploaded_dir.exists()
    assert pending_dir.exists()
    assert vod.exists()
    assert db_session.query(RenderJob).count() == 2

    pending = db_session.query(RenderJob).filter_by(clip_id="clip_pending").one()
    pending.youtube_upload_status = "completed"
    pending.youtube_upload_url = "https://www.youtube.com/shorts/pending"
    db_session.commit()

    result = AutoPipelineService.cleanup_uploaded_renders(db_session, clean_vod=True)

    assert result["clips_cleaned"] == 1
    assert result["vod_deleted_count"] == 1
    assert not pending_dir.exists()
    assert not vod.exists()

    db_session.refresh(video)
    assert video.is_downloaded is False
    assert video.download_status == "not_downloaded"
    assert video.local_file_path is None
    assert db_session.query(RenderJob).count() == 2


def test_stage_all_top_candidates_batches_per_video(db_session, monkeypatch):
    _fake_render_and_metadata(monkeypatch)

    video_a = _video(db_session, "vid_batch_a")
    video_b = _video(db_session, "vid_batch_b")

    _candidate(db_session, video_a, "cand_a1", 0.95, 10.0)
    _candidate(db_session, video_a, "cand_a2", 0.90, 40.0)
    _candidate(db_session, video_a, "cand_a3", 0.80, 70.0)
    _candidate(db_session, video_b, "cand_b1", 0.99, 5.0)
    _candidate(db_session, video_b, "cand_b2", 0.70, 35.0)

    first = AutoStageService.stage_all_top_candidates(
        db_session, top_n=2, min_score=0.6, schedule=False
    )
    assert first["videos_processed"] == 2
    assert first["staged_count"] == 4
    staged_ids = {clip["candidate_id"] for clip in first["clips"]}
    assert {"cand_a1", "cand_a2", "cand_b1", "cand_b2"} == staged_ids

    second = AutoStageService.stage_all_top_candidates(
        db_session, top_n=2, min_score=0.6, schedule=False
    )
    assert second["videos_processed"] == 1
    assert second["staged_count"] == 1
    assert second["clips"][0]["candidate_id"] == "cand_a3"

    third = AutoStageService.stage_all_top_candidates(
        db_session, top_n=2, min_score=0.6, schedule=False
    )
    assert third["staged_count"] == 0
    assert db_session.query(RenderJob).count() == 5


def test_cleanup_uploaded_endpoint(db_session, client, storage):
    renders, _ = storage
    clip_dir = renders / "clip_api_cleanup"
    clip_dir.mkdir()
    (clip_dir / "vertical_blur.mp4").write_bytes(b"0" * 512)

    video = _video(db_session, "vid_api_cleanup")
    _job(db_session, video, "clip_api_cleanup", uploaded=True)

    res = client.post(
        f"{settings.API_PREFIX}/renders/cleanup-uploaded",
        json={"sync": True, "clean_vod": False},
    )

    assert res.status_code == 200
    body = res.json()["response"]
    assert body["clips_cleaned"] == 1
    assert body["bytes_reclaimed"] == 512
    assert not clip_dir.exists()
    assert db_session.query(RenderJob).count() == 1


def test_auto_pipeline_endpoint_stages_and_cleans(
    db_session, client, storage, monkeypatch
):
    _fake_render_and_metadata(monkeypatch)
    renders, _ = storage

    uploaded_dir = renders / "clip_already_uploaded"
    uploaded_dir.mkdir()
    (uploaded_dir / "vertical_blur.mp4").write_bytes(b"0" * 1024)

    video = _video(db_session, "vid_pipeline")
    _job(db_session, video, "clip_already_uploaded", uploaded=True)
    _candidate(db_session, video, "cand_pipeline", 0.91, 15.0)

    res = client.post(
        f"{settings.API_PREFIX}/renders/auto-pipeline",
        json={
            "stage": True,
            "cleanup": True,
            "clean_vod": False,
            "top_n": 1,
            "min_score": 0.6,
            "schedule": False,
            "sync": True,
        },
    )

    assert res.status_code == 200
    body = res.json()["response"]
    assert body["staged_count"] == 1
    assert body["clips_cleaned"] == 1
    assert body["bytes_reclaimed"] == 1024
    assert not uploaded_dir.exists()
    assert (
        db_session.query(RenderJob).filter_by(clip_id="auto_cand_pipeline").count() == 1
    )
