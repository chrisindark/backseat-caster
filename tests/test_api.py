"""Tests for BackseatCaster API endpoints and BaseResponse envelope."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.render_job import RenderJob
from app.models.video import Video

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


def test_health_check(client):
    response = client.get(f"{settings.API_PREFIX}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status_code"] == 200
    assert data["response"]["status"] == "healthy"
    assert data["error_message"] is None
    assert data["error_code"] is None


def test_list_empty_videos(client):
    response = client.get(f"{settings.API_PREFIX}/videos")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status_code"] == 200
    assert data["response"]["items"] == []
    assert data["response"]["total"] == 0
    assert data["response"]["page"] == 1


def test_list_videos_with_content(client, db_session):
    video = Video(
        id="sample_vid_1",
        title="Marvel Rivals Alpha Gameplay",
        thumbnail_url="https://i.ytimg.com/vi/sample_vid_1/hqdefault.jpg",
        duration=180,
        duration_formatted="3:00",
        channel_name="Marvel Rivals",
        channel_id="UC_sample",
        channel_url="https://www.youtube.com/@MarvelRivals",
        view_count=50000,
        webpage_url="https://www.youtube.com/watch?v=sample_vid_1",
        is_downloaded=False,
        download_status="not_downloaded",
    )
    db_session.add(video)
    db_session.commit()

    response = client.get(f"{settings.API_PREFIX}/videos")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status_code"] == 200
    payload = data["response"]
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "sample_vid_1"
    assert payload["items"][0]["title"] == "Marvel Rivals Alpha Gameplay"
    assert payload["items"][0]["duration_formatted"] == "3:00"


def test_get_single_video(client, db_session):
    video = Video(
        id="sample_vid_2",
        title="Epic Team Fight",
        thumbnail_url="https://i.ytimg.com/vi/sample_vid_2/hqdefault.jpg",
        duration=75,
        duration_formatted="1:15",
        channel_name="Marvel Rivals",
        webpage_url="https://www.youtube.com/watch?v=sample_vid_2",
    )
    db_session.add(video)
    db_session.commit()

    response = client.get(f"{settings.API_PREFIX}/videos/sample_vid_2")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status_code"] == 200
    assert data["response"]["id"] == "sample_vid_2"
    assert data["response"]["title"] == "Epic Team Fight"


def test_get_nonexistent_video(client):
    response = client.get(f"{settings.API_PREFIX}/videos/non_existent_123")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["status_code"] == 404
    assert data["response"] is None
    assert "not found" in data["error_message"].lower()
    assert data["error_code"] == "NOT_FOUND"


def test_get_video_status(client, db_session):
    video = Video(
        id="status_vid_1",
        title="Status Check Video",
        webpage_url="https://www.youtube.com/watch?v=status_vid_1",
        download_status="downloading",
        download_progress=45.5,
    )
    db_session.add(video)
    db_session.commit()

    response = client.get(f"{settings.API_PREFIX}/videos/status_vid_1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["response"]["video_id"] == "status_vid_1"
    assert data["response"]["download_status"] == "downloading"
    assert data["response"]["download_progress"] == 45.5


def test_delete_video_download(client, db_session):
    video = Video(
        id="delete_vid_1",
        title="Delete Test Video",
        webpage_url="https://www.youtube.com/watch?v=delete_vid_1",
        is_downloaded=True,
        download_status="completed",
        download_progress=100.0,
    )
    db_session.add(video)
    db_session.commit()

    response = client.delete(f"{settings.API_PREFIX}/videos/delete_vid_1/download")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["response"]["status"] == "success"

    # Verify db was updated
    db_session.refresh(video)
    assert video.is_downloaded is False
    assert video.download_status == "not_downloaded"


def test_validation_error_format(client):
    # Pass invalid limit (must be <= 100, page >= 1)
    response = client.get(f"{settings.API_PREFIX}/videos?limit=500")
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["status_code"] == 422
    assert data["error_code"] == "VALIDATION_ERROR"
    assert data["error_message"] is not None


def test_list_renders_empty_or_items(client):
    response = client.get(f"{settings.API_PREFIX}/renders")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "items" in data["response"]


def test_get_render_nonexistent(client):
    response = client.get(f"{settings.API_PREFIX}/renders/nonexistent_clip_999")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["status_code"] == 404
    assert data["error_code"] == "NOT_FOUND"


def test_create_render_nonexistent_video(client):
    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "totally_missing_video_id",
            "start_seconds": 0,
            "duration_seconds": 5,
        },
    )
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "NOT_FOUND"


def test_render_and_stream_endpoints(client, db_session, tmp_path):
    import subprocess

    # 1. Create a 2s dummy video
    dummy_video_path = tmp_path / "test_api_clip_source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=640x360:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dummy_video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    # 2. Add video record to DB
    video = Video(
        id="api_test_vod_1",
        title="API Test VOD",
        webpage_url="https://youtube.com/watch?v=api_test_vod_1",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(dummy_video_path),
    )
    db_session.add(video)
    db_session.commit()

    # 3. Post render request
    clip_id = f"test_clip_{int(tmp_path.stat().st_mtime)}"
    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "api_test_vod_1",
            "start_seconds": 0,
            "duration_seconds": 1,
            "clip_id": clip_id,
            "encoder": "libx264",
            "overwrite": True,
            "sync": True,
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    render_resp = res_data["response"]
    assert render_resp["clip_id"] == clip_id
    assert render_resp["status"] in ("pending", "completed")
    assert (
        render_resp["landscape_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/landscape"
    )
    assert (
        render_resp["vertical_blur_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_blur"
    )
    assert (
        render_resp["vertical_crop_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_crop"
    )
    assert (
        render_resp["manifest_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/manifest"
    )

    # Verify status polling endpoint
    job_id = render_resp.get("job_id")
    assert job_id is not None
    job_status_res = client.get(f"{settings.API_PREFIX}/renders/jobs/{job_id}")
    assert job_status_res.status_code == 200
    job_data = job_status_res.json()["response"]
    assert job_data["status"] == "completed"
    assert job_data["progress"] == 100.0

    # Verify {clip_id}/status endpoint
    clip_status_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}/status")
    assert clip_status_res.status_code == 200
    assert clip_status_res.json()["response"]["status"] == "completed"

    # 4. Get specific render manifest
    get_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}")
    assert get_res.status_code == 200
    manifest = get_res.json()["response"]
    assert manifest["clip_id"] == clip_id
    assert (
        manifest["landscape_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/landscape"
    )
    assert (
        manifest["vertical_blur_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_blur"
    )
    assert (
        manifest["vertical_crop_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_crop"
    )
    assert (
        manifest["manifest_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/manifest"
    )
    assert (
        manifest["outputs"]["landscape"]["path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/landscape"
    )
    assert (
        manifest["outputs"]["vertical_blur"]["path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_blur"
    )
    assert (
        manifest["outputs"]["vertical_crop"]["path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/vertical_crop"
    )

    # Test list_renders endpoint
    list_res = client.get(f"{settings.API_PREFIX}/renders")
    assert list_res.status_code == 200
    items = list_res.json()["response"]["items"]
    assert len(items) > 0
    item_matches = [it for it in items if it["clip_id"] == clip_id]
    assert len(item_matches) == 1
    assert (
        item_matches[0]["landscape_path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/landscape"
    )
    assert (
        item_matches[0]["outputs"]["landscape"]["path"]
        == f"{settings.API_PREFIX}/renders/{clip_id}/stream/landscape"
    )

    # 5. Stream landscape, vertical_blur, vertical_crop
    for v_type in ("landscape", "vertical_blur", "vertical_crop"):
        stream_res = client.get(
            f"{settings.API_PREFIX}/renders/{clip_id}/stream/{v_type}"
        )
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"] == "video/mp4"
        assert len(stream_res.content) > 0

    # Stream manifest via stream endpoint
    manifest_stream = client.get(
        f"{settings.API_PREFIX}/renders/{clip_id}/stream/manifest"
    )
    assert manifest_stream.status_code == 200
    assert manifest_stream.headers["content-type"] == "application/json"
    assert len(manifest_stream.content) > 0

    # Stream manifest via direct manifest endpoint
    manifest_file_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}/manifest")
    assert manifest_file_res.status_code == 200
    assert manifest_file_res.headers["content-type"] == "application/json"
    assert len(manifest_file_res.content) > 0

    # 6. Stream invalid type
    bad_stream = client.get(
        f"{settings.API_PREFIX}/renders/{clip_id}/stream/invalid_type"
    )
    assert bad_stream.status_code == 400


def test_render_with_direct_crop_preset(client, db_session, tmp_path):
    import subprocess

    dummy_video_path = tmp_path / "test_api_crop_preset.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=640x360:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dummy_video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    video = Video(
        id="api_test_vod_crop",
        title="API Test VOD Crop",
        webpage_url="https://youtube.com/watch?v=api_test_vod_crop",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(dummy_video_path),
    )
    db_session.add(video)
    db_session.commit()

    clip_id = f"test_clip_direct_{int(tmp_path.stat().st_mtime)}"
    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "api_test_vod_crop",
            "start_seconds": 0,
            "duration_seconds": 1,
            "clip_id": clip_id,
            "encoder": "libx264",
            "crop_preset": "direct_crop",
            "crop_blur_padding": 0.0,
            "overwrite": True,
            "sync": True,
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True

    get_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}")
    assert get_res.status_code == 200
    manifest = get_res.json()["response"]
    assert manifest["outputs"]["vertical_crop"]["crop_preset"] == "direct_crop"
    assert manifest["outputs"]["vertical_crop"]["crop_blur_padding"] == 0.0


def test_render_job_celery_dispatch(client, db_session, monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from app.models.render_job import RenderJob

    # Mock video file
    dummy_file = tmp_path / "celery_mock_vod.mp4"
    dummy_file.write_text("fake video content")

    video = Video(
        id="celery_vod_1",
        title="Celery VOD",
        webpage_url="https://youtube.com/watch?v=celery_vod_1",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(dummy_file),
    )
    db_session.add(video)
    db_session.commit()

    # Mock Celery broker as online
    monkeypatch.setattr("app.worker.helpers.is_celery_broker_online", lambda: True)

    mock_async_result = MagicMock()
    mock_async_result.id = "celery-task-xyz-789"
    mock_delay = MagicMock(return_value=mock_async_result)
    monkeypatch.setattr(
        "app.services.renders.render_clip_celery_task.delay", mock_delay
    )

    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "celery_vod_1",
            "start_seconds": 0,
            "duration_seconds": 2,
            "clip_id": "clip_celery_dispatch",
            "encoder": "libx264",
            "overwrite": True,
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "via Celery" in res_data["response"]["message"]
    job_id = res_data["response"]["job_id"]

    # Verify task was dispatched with job ID
    mock_delay.assert_called_once_with(job_id)

    # Verify job record in database
    job = db_session.query(RenderJob).filter(RenderJob.id == job_id).first()
    assert job is not None
    assert job.celery_task_id == "celery-task-xyz-789"
    assert job.status == "pending"


def test_render_job_status_failed(client, db_session):
    from app.models.render_job import RenderJob

    job = RenderJob(
        id="render_job_failed_1",
        clip_id="clip_failed_1",
        video_id="vod_failed_1",
        status="failed",
        progress=25.0,
        start_seconds=10.0,
        duration_seconds=15.0,
        error_message="FFmpeg exited with error: codec not supported",
    )
    db_session.add(job)
    db_session.commit()

    # Query status by job_id
    res = client.get(f"{settings.API_PREFIX}/renders/jobs/render_job_failed_1")
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["job_id"] == "render_job_failed_1"
    assert data["status"] == "failed"
    assert data["progress"] == 25.0
    assert "codec not supported" in data["error_message"]

    # Query status by clip_id
    clip_res = client.get(f"{settings.API_PREFIX}/renders/clip_failed_1/status")
    assert clip_res.status_code == 200
    clip_data = clip_res.json()["response"]
    assert clip_data["status"] == "failed"


def test_render_job_status_not_found(client):
    res = client.get(f"{settings.API_PREFIX}/renders/jobs/job_does_not_exist_999")
    assert res.status_code == 404
    assert res.json()["success"] is False


def test_get_channel_youtube_videos_preview(client, db_session, monkeypatch):
    """Verify previewing channel videos does not insert them to DB and detects existing ones."""
    from app.services.youtube import YouTubeService

    # Insert one existing video
    existing = Video(
        id="yt_vid_1",
        title="Existing Video",
        webpage_url="https://youtube.com/watch?v=yt_vid_1",
        is_downloaded=True,
    )
    db_session.add(existing)
    db_session.commit()

    def mock_extract(channel_input, limit=20, offset=0):
        return {
            "channel_title": "Test Channel",
            "channel_id": "UC_TEST",
            "channel_url": "https://youtube.com/@test",
            "videos": [
                {
                    "id": "yt_vid_1",
                    "title": "Existing Video",
                    "description": "Desc 1",
                    "thumbnail_url": "https://thumb/1.jpg",
                    "duration": 120,
                    "duration_formatted": "2:00",
                    "channel_name": "Test Channel",
                    "channel_id": "UC_TEST",
                    "channel_url": "https://youtube.com/@test",
                    "view_count": 100,
                    "published_at": "2026-01-01",
                    "webpage_url": "https://youtube.com/watch?v=yt_vid_1",
                },
                {
                    "id": "yt_vid_2",
                    "title": "Brand New Video",
                    "description": "Desc 2",
                    "thumbnail_url": "https://thumb/2.jpg",
                    "duration": 240,
                    "duration_formatted": "4:00",
                    "channel_name": "Test Channel",
                    "channel_id": "UC_TEST",
                    "channel_url": "https://youtube.com/@test",
                    "view_count": 200,
                    "published_at": "2026-01-02",
                    "webpage_url": "https://youtube.com/watch?v=yt_vid_2",
                },
            ],
        }

    monkeypatch.setattr(YouTubeService, "extract_channel_metadata", mock_extract)

    res = client.get(
        f"{settings.API_PREFIX}/videos/youtube/channel?channel=@test&limit=20&offset=0"
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    payload = data["response"]
    assert payload["channel_title"] == "Test Channel"
    assert len(payload["videos"]) == 2

    v1 = payload["videos"][0]
    assert v1["id"] == "yt_vid_1"
    assert v1["is_in_database"] is True
    assert v1["is_downloaded"] is True

    v2 = payload["videos"][1]
    assert v2["id"] == "yt_vid_2"
    assert v2["is_in_database"] is False
    assert v2["is_downloaded"] is False

    # Check that DB was NOT modified by the preview
    total_in_db = db_session.query(Video).count()
    assert total_in_db == 1


def test_sync_channel_with_selected_videos(client, db_session):
    """Verify syncing selected videos adds new ones, skips existing ones."""
    existing = Video(
        id="sync_vid_1",
        title="Existing Video",
        webpage_url="https://youtube.com/watch?v=sync_vid_1",
    )
    db_session.add(existing)
    db_session.commit()

    payload = {
        "channel_url": "@test",
        "videos": [
            {
                "id": "sync_vid_1",
                "title": "Existing Video",
                "webpage_url": "https://youtube.com/watch?v=sync_vid_1",
                "duration": 100,
                "duration_formatted": "1:40",
            },
            {
                "id": "sync_vid_2",
                "title": "Second Video To Add",
                "webpage_url": "https://youtube.com/watch?v=sync_vid_2",
                "duration": 200,
                "duration_formatted": "3:20",
            },
        ],
    }

    res = client.post(f"{settings.API_PREFIX}/videos/sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    resp = data["response"]
    assert resp["new_added"] == 1
    assert resp["skipped"] == 1

    # Verify database now has both videos
    assert db_session.query(Video).count() == 2
    new_v = db_session.query(Video).filter(Video.id == "sync_vid_2").first()
    assert new_v is not None
    assert new_v.title == "Second Video To Add"


def test_list_render_jobs(client, db_session):
    video = Video(
        id="render_job_vid_1",
        title="Render Job Parent Video",
        webpage_url="https://youtube.com/watch?v=render_job_vid_1",
    )
    db_session.add(video)

    job1 = RenderJob(
        id="job_123",
        clip_id="clip_123",
        video_id="render_job_vid_1",
        status="completed",
        progress=100.0,
        start_seconds=10.0,
        duration_seconds=15.0,
    )
    job2 = RenderJob(
        id="job_456",
        clip_id="clip_456",
        video_id="render_job_vid_1",
        status="rendering",
        progress=45.0,
        start_seconds=20.0,
        duration_seconds=30.0,
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    res = client.get(f"{settings.API_PREFIX}/renders/jobs")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["response"]["total"] == 2
    items = data["response"]["items"]
    assert len(items) == 2
    assert items[0]["video_title"] == "Render Job Parent Video"

    # Filter by status
    res_status = client.get(f"{settings.API_PREFIX}/renders/jobs?status=rendering")
    assert res_status.status_code == 200
    assert res_status.json()["response"]["total"] == 1
    assert res_status.json()["response"]["items"][0]["job_id"] == "job_456"


def test_update_upload_selection(client, db_session):
    job = RenderJob(
        id="job_upload_sel",
        clip_id="clip_upload_sel",
        video_id="sample_vid",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=15.0,
    )
    db_session.add(job)
    db_session.commit()

    payload = {
        "is_selected": True,
        "preferred_format": "vertical_blur",
        "title": "Selected Highlight Short",
        "description": "Epic Marvel Rivals elimination",
        "tags": ["gaming", "rivals"],
        "privacy": "unlisted",
    }
    res = client.post(
        f"{settings.API_PREFIX}/renders/clip_upload_sel/upload-selection",
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["response"]["upload_selection"]["is_selected"] is True

    # Check that database record updated
    db_job = (
        db_session.query(RenderJob).filter(RenderJob.id == "job_upload_sel").first()
    )
    assert db_job.is_selected_for_upload is True
    assert db_job.selected_format == "vertical_blur"


def test_delete_render(client, db_session):
    job = RenderJob(
        id="job_to_del",
        clip_id="clip_to_del",
        video_id="sample_vid",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=15.0,
    )
    db_session.add(job)
    db_session.commit()

    res = client.delete(f"{settings.API_PREFIX}/renders/clip_to_del")
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert (
        db_session.query(RenderJob).filter(RenderJob.id == "job_to_del").first() is None
    )


def test_download_celery_dispatch(client, db_session, monkeypatch):
    from unittest.mock import MagicMock

    from app.models.video import Video

    video = Video(
        id="celery_dl_vod_1",
        title="Celery DL Video",
        webpage_url="https://www.youtube.com/watch?v=celery_dl_vod_1",
        is_downloaded=False,
        download_status="not_downloaded",
    )
    db_session.add(video)
    db_session.commit()

    monkeypatch.setattr("app.worker.helpers.is_celery_broker_online", lambda: True)

    mock_async_result = MagicMock()
    mock_async_result.id = "celery-dl-task-123"
    mock_delay = MagicMock(return_value=mock_async_result)
    monkeypatch.setattr(
        "app.services.videos.download_video_celery_task.delay", mock_delay
    )

    response = client.post(
        f"{settings.API_PREFIX}/videos/celery_dl_vod_1/download",
        json={"quality": "best"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "via Celery" in res_data["response"]["message"]
    mock_delay.assert_called_once_with("celery_dl_vod_1", "best")


def test_worker_tasks_backwards_compatible_imports():
    from app.services.renders import execute_render_job as svc_render_job
    from app.services.renders import render_clip_celery_task as svc_render_task
    from app.services.videos import download_video_celery_task as svc_dl_task
    from app.services.videos import execute_download_job as svc_dl_job
    from app.worker.tasks import (
        download_video_celery_task,
        execute_download_job,
        execute_render_job,
        render_clip_celery_task,
    )

    assert download_video_celery_task is svc_dl_task
    assert execute_download_job is svc_dl_job
    assert render_clip_celery_task is svc_render_task
    assert execute_render_job is svc_render_job


def test_stream_video_not_found(client):
    """Streaming a non-existent video returns 404."""
    res = client.get(f"{settings.API_PREFIX}/videos/nonexistent_id/stream")
    assert res.status_code == 404


def test_stream_video_not_downloaded(client, db_session):
    """Streaming a video that is in DB but not downloaded returns 404."""
    v = Video(
        id="not_dl_stream_test",
        title="Not Downloaded Video",
        webpage_url="https://youtube.com/watch?v=not_dl_stream_test",
        is_downloaded=False,
    )
    db_session.add(v)
    db_session.commit()

    res = client.get(f"{settings.API_PREFIX}/videos/not_dl_stream_test/stream")
    assert res.status_code == 404


def test_stream_video_downloaded_success(client, db_session, tmp_path):
    """Streaming a downloaded video returns 200 and streamable video bytes."""
    dummy_file = tmp_path / "stream_vod_1.mp4"
    dummy_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")

    v = Video(
        id="stream_vod_1",
        title="Streamable Video",
        webpage_url="https://youtube.com/watch?v=stream_vod_1",
        is_downloaded=True,
        local_file_path=str(dummy_file),
        file_size_bytes=len(dummy_file.read_bytes()),
    )
    db_session.add(v)
    db_session.commit()

    res = client.get(f"{settings.API_PREFIX}/videos/stream_vod_1/stream")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("video/mp4")
    assert len(res.content) == len(dummy_file.read_bytes())
