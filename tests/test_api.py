"""Tests for BackseatCaster API endpoints and BaseResponse envelope."""

import subprocess

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


def test_list_videos_status_filtering(client, db_session):
    # Setup: 1 downloaded, 1 downloading, 1 not_downloaded
    v_dl = Video(
        id="vid_downloaded",
        title="Downloaded Gameplay",
        thumbnail_url="https://i.ytimg.com/vi/vid_downloaded/hqdefault.jpg",
        duration=120,
        duration_formatted="2:00",
        channel_name="Marvel Rivals",
        webpage_url="https://www.youtube.com/watch?v=vid_downloaded",
        is_downloaded=True,
        download_status="completed",
    )
    v_ing = Video(
        id="vid_downloading",
        title="Downloading Gameplay",
        thumbnail_url="https://i.ytimg.com/vi/vid_downloading/hqdefault.jpg",
        duration=90,
        duration_formatted="1:30",
        channel_name="Marvel Rivals",
        webpage_url="https://www.youtube.com/watch?v=vid_downloading",
        is_downloaded=False,
        download_status="downloading",
    )
    v_not = Video(
        id="vid_not_dl",
        title="Not Downloaded Gameplay",
        thumbnail_url="https://i.ytimg.com/vi/vid_not_dl/hqdefault.jpg",
        duration=60,
        duration_formatted="1:00",
        channel_name="Marvel Rivals",
        webpage_url="https://www.youtube.com/watch?v=vid_not_dl",
        is_downloaded=False,
        download_status="not_downloaded",
    )
    db_session.add_all([v_dl, v_ing, v_not])
    db_session.commit()

    # 1. Filter: downloaded
    res_dl = client.get(f"{settings.API_PREFIX}/videos?status=downloaded")
    assert res_dl.status_code == 200
    dl_items = res_dl.json()["response"]["items"]
    assert len(dl_items) == 1
    assert dl_items[0]["id"] == "vid_downloaded"
    assert res_dl.json()["response"]["total"] == 1

    # 2. Filter: not_downloaded
    res_not = client.get(f"{settings.API_PREFIX}/videos?status=not_downloaded")
    assert res_not.status_code == 200
    not_items = res_not.json()["response"]["items"]
    assert len(not_items) == 1
    assert not_items[0]["id"] == "vid_not_dl"
    assert res_not.json()["response"]["total"] == 1

    # 3. Filter: downloading
    res_ing = client.get(f"{settings.API_PREFIX}/videos?status=downloading")
    assert res_ing.status_code == 200
    ing_items = res_ing.json()["response"]["items"]
    assert len(ing_items) == 1
    assert ing_items[0]["id"] == "vid_downloading"
    assert res_ing.json()["response"]["total"] == 1

    # 4. Filter: all
    res_all = client.get(f"{settings.API_PREFIX}/videos?status=all")
    assert res_all.status_code == 200
    assert res_all.json()["response"]["total"] == 3


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
        capture_output=True,
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
            "modes": ["landscape", "vertical_blur", "third_person"],
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


def test_render_default_mode_single_third_person(client, db_session, tmp_path):
    """Verify that omitting modes defaults to the single third_person mode."""
    import subprocess

    dummy_video_path = tmp_path / "test_api_clip_default_mode.mp4"
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
        capture_output=True,
        check=True,
    )

    video = Video(
        id="api_test_vod_default_mode",
        title="API Test VOD Default Mode",
        webpage_url="https://youtube.com/watch?v=api_test_vod_default_mode",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(dummy_video_path),
    )
    db_session.add(video)
    db_session.commit()

    clip_id = f"test_clip_def_{int(tmp_path.stat().st_mtime)}"
    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "api_test_vod_default_mode",
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
    assert render_resp["modes"] == ["third_person"]
    assert "third_person" in render_resp["outputs"]
    assert "landscape" not in render_resp["outputs"]
    assert "vertical_blur" not in render_resp["outputs"]
    assert render_resp["vertical_crop_path"] is not None


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
        capture_output=True,
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


def test_render_with_custom_modes_and_stream(client, db_session, tmp_path):
    import subprocess

    dummy_video_path = tmp_path / "test_api_modes_source.mp4"
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
        capture_output=True,
        check=True,
    )

    video = Video(
        id="api_test_vod_modes",
        title="API Test VOD Modes",
        webpage_url="https://youtube.com/watch?v=api_test_vod_modes",
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(dummy_video_path),
    )
    db_session.add(video)
    db_session.commit()

    clip_id = f"test_clip_modes_{int(tmp_path.stat().st_mtime)}"
    target_modes = ["third_person", "cinematic", "custom"]
    response = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": "api_test_vod_modes",
            "start_seconds": 0,
            "duration_seconds": 1,
            "clip_id": clip_id,
            "encoder": "libx264",
            "modes": target_modes,
            "crop_blur_padding": 0.1,
            "overwrite": True,
            "sync": True,
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    render_resp = res_data["response"]
    assert render_resp["modes"] == target_modes
    assert "third_person" in render_resp["outputs"]
    assert "cinematic" in render_resp["outputs"]
    assert "custom" in render_resp["outputs"]

    # Verify stream endpoints for the new mode names
    for m in target_modes:
        stream_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}/stream/{m}")
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"] == "video/mp4"

    # Verify manifest
    get_res = client.get(f"{settings.API_PREFIX}/renders/{clip_id}")
    assert get_res.status_code == 200
    manifest = get_res.json()["response"]
    assert manifest["modes"] == target_modes


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
    from app.services.youtube import YtdlpService

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

    monkeypatch.setattr(YtdlpService, "extract_channel_metadata", mock_extract)

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


def test_correlation_id_middleware(client):
    """CorrelationIdMiddleware sets and propagates X-Correlation-ID and X-Request-ID headers."""
    # 1. Without headers -> auto-generated UUID returned for both
    res = client.get(f"{settings.API_PREFIX}/health?check=1")
    assert "x-correlation-id" in res.headers
    assert "x-request-id" in res.headers
    assert len(res.headers["x-correlation-id"]) > 0
    # When neither header is supplied, correlation_id defaults to request_id
    assert res.headers["x-correlation-id"] == res.headers["x-request-id"]

    # 2. With client correlation header -> echoed back
    custom_id = "test-corr-id-12345"
    res2 = client.get(
        f"{settings.API_PREFIX}/health", headers={"x-correlation-id": custom_id}
    )
    assert res2.headers.get("x-correlation-id") == custom_id
    assert "x-request-id" in res2.headers

    # 3. With distinct client request header
    custom_req_id = "test-req-id-67890"
    res3 = client.get(
        f"{settings.API_PREFIX}/health",
        headers={
            "x-correlation-id": custom_id,
            "x-request-id": custom_req_id,
        },
    )
    assert res3.headers.get("x-correlation-id") == custom_id
    assert res3.headers.get("x-request-id") == custom_req_id

    # 4. CORS exposed headers check on CORS preflight / request
    cors_res = client.get(
        f"{settings.API_PREFIX}/health",
        headers={"Origin": "http://localhost:3000"},
    )
    exposed = cors_res.headers.get("access-control-expose-headers", "")
    assert "X-Correlation-ID" in exposed
    assert "X-Request-ID" in exposed


def test_bulk_delete_renders_sync(client, db_session, tmp_path, monkeypatch):
    """Bulk delete removes clip files from disk and RenderJob rows from database synchronously."""
    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))

    # Setup 2 clips with files and 1 non-existing
    clip1_dir = tmp_path / "bulk_clip_1"
    clip1_dir.mkdir(parents=True)
    (clip1_dir / "landscape.mp4").write_bytes(b"dummy1")
    (clip1_dir / "manifest.json").write_text("{}")

    clip2_dir = tmp_path / "bulk_clip_2"
    clip2_dir.mkdir(parents=True)
    (clip2_dir / "landscape.mp4").write_bytes(b"dummy2")

    job1 = RenderJob(
        id="job_bulk_1",
        clip_id="bulk_clip_1",
        video_id="v1",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=10.0,
    )
    job2 = RenderJob(
        id="job_bulk_2",
        clip_id="bulk_clip_2",
        video_id="v2",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=10.0,
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    # 1. POST /bulk-delete
    res = client.post(
        f"{settings.API_PREFIX}/renders/bulk-delete",
        json={
            "clip_ids": ["bulk_clip_1", "bulk_clip_2", "non_existing_clip"],
            "sync": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    resp = data["response"]
    assert resp["deleted_count"] == 2
    assert "bulk_clip_1" in resp["deleted_clip_ids"]
    assert "bulk_clip_2" in resp["deleted_clip_ids"]
    assert "non_existing_clip" in resp["not_found_clip_ids"]

    # Files must be gone
    assert not clip1_dir.exists()
    assert not clip2_dir.exists()

    # Jobs must be deleted
    remaining = (
        db_session.query(RenderJob)
        .filter(RenderJob.clip_id.in_(["bulk_clip_1", "bulk_clip_2"]))
        .all()
    )
    assert len(remaining) == 0


def test_bulk_delete_renders_preserves_uploaded_history(
    client, db_session, tmp_path, monkeypatch
):
    """Bulk delete preserves RenderJob database record and YouTube info when clip was published."""
    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))

    clip_dir = tmp_path / "uploaded_clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "landscape.mp4").write_bytes(b"dummy_video")

    job = RenderJob(
        id="job_uploaded_1",
        clip_id="uploaded_clip",
        video_id="v_up",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=10.0,
        output_dir=str(clip_dir),
        landscape_path=str(clip_dir / "landscape.mp4"),
        youtube_video_id="yt_test_123",
        youtube_upload_status="completed",
        youtube_upload_url="https://youtube.com/shorts/yt_test_123",
    )
    db_session.add(job)
    db_session.commit()

    # Bulk delete with default preserve_uploaded_history=True
    res = client.post(
        f"{settings.API_PREFIX}/renders/bulk-delete",
        json={"clip_ids": ["uploaded_clip"], "sync": True},
    )
    assert res.status_code == 200
    resp = res.json()["response"]
    assert resp["deleted_count"] == 1
    assert resp["preserved_jobs_count"] == 1

    # Disk files must be cleaned
    assert not clip_dir.exists()

    # Database record must still exist with YouTube info preserved and disk paths cleared
    saved_job = db_session.query(RenderJob).filter_by(id="job_uploaded_1").first()
    assert saved_job is not None
    assert saved_job.youtube_video_id == "yt_test_123"
    assert saved_job.youtube_upload_status == "completed"
    assert saved_job.output_dir is None
    assert saved_job.landscape_path is None


def test_bulk_delete_renders_via_delete_endpoints(
    client, db_session, tmp_path, monkeypatch
):
    """DELETE /renders/bulk route accepts BulkDeleteRendersRequest."""
    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))

    c_dir = tmp_path / "delete_bulk_clip"
    c_dir.mkdir(parents=True)
    (c_dir / "manifest.json").write_text("{}")

    job = RenderJob(
        id="job_del_1",
        clip_id="delete_bulk_clip",
        video_id="v1",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=5.0,
    )
    db_session.add(job)
    db_session.commit()

    res = client.request(
        "DELETE",
        f"{settings.API_PREFIX}/renders/bulk",
        json={"clip_ids": ["delete_bulk_clip"], "sync": True},
    )
    assert res.status_code == 200
    assert res.json()["response"]["deleted_count"] == 1
    assert not c_dir.exists()


def test_bulk_delete_renders_celery_dispatch(client, monkeypatch):
    """Async bulk delete dispatches to Celery task when Celery broker is online."""
    from unittest.mock import MagicMock

    monkeypatch.setattr("app.routers.renders.is_celery_broker_online", lambda: True)
    mock_task = MagicMock()
    mock_task.id = "celery-bulk-del-123"
    mock_delay = MagicMock(return_value=mock_task)
    monkeypatch.setattr(
        "app.routers.renders.bulk_delete_renders_celery_task.delay", mock_delay
    )

    res = client.post(
        f"{settings.API_PREFIX}/renders/bulk-delete",
        json={"clip_ids": ["clip_a", "clip_b"], "sync": False},
    )
    assert res.status_code == 200
    resp = res.json()["response"]
    assert resp["task_id"] == "celery-bulk-del-123"
    assert "via Celery" in resp["message"]
    mock_delay.assert_called_once_with(
        ["clip_a", "clip_b"], preserve_uploaded_history=True
    )


def test_bulk_delete_renders_background_fallback(client, monkeypatch):
    """Async bulk delete dispatches to FastAPI background tasks when Celery broker is offline."""
    monkeypatch.setattr("app.routers.renders.is_celery_broker_online", lambda: False)

    res = client.post(
        f"{settings.API_PREFIX}/renders/bulk-delete",
        json={"clip_ids": ["clip_offline_1"], "sync": False},
    )
    assert res.status_code == 200
    resp = res.json()["response"]
    assert resp["task_id"] is None
    assert "background worker" in resp["message"]


def test_create_video_success(client, db_session):
    """POST /videos creates a new Video catalog entry and returns 201."""
    payload = {
        "id": "test_crud_vid_1",
        "title": "CRUD Test Video",
        "description": "Test description",
        "duration": 90,
        "channel_name": "TestChannel",
        "webpage_url": "https://www.youtube.com/watch?v=test_crud_vid_1",
    }
    res = client.post(f"{settings.API_PREFIX}/videos", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["response"]["id"] == "test_crud_vid_1"
    assert data["response"]["title"] == "CRUD Test Video"
    assert data["response"]["duration_formatted"] == "1:30"

    # Verify persisted in database
    db_vid = db_session.query(Video).filter(Video.id == "test_crud_vid_1").first()
    assert db_vid is not None
    assert db_vid.title == "CRUD Test Video"


def test_create_video_auto_extracted_id(client, db_session):
    """POST /videos extracts video ID from webpage_url when id is not supplied."""
    payload = {
        "title": "Auto ID Video",
        "webpage_url": "https://www.youtube.com/watch?v=abcdef12345",
    }
    res = client.post(f"{settings.API_PREFIX}/videos", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["response"]["id"] == "abcdef12345"


def test_create_video_duplicate_conflict(client):
    """POST /videos returns 409 Conflict when video with the same ID already exists."""
    payload = {
        "id": "dup_video_id",
        "title": "First Creation",
        "webpage_url": "https://www.youtube.com/watch?v=dup_video_id",
    }
    res1 = client.post(f"{settings.API_PREFIX}/videos", json=payload)
    assert res1.status_code == 201

    res2 = client.post(f"{settings.API_PREFIX}/videos", json=payload)
    assert res2.status_code == 409
    err_text = res2.json().get("error_message") or res2.json().get("detail") or ""
    assert "already exists" in err_text


def test_update_video_success(client, db_session):
    """PATCH and PUT /videos/{video_id} update video attributes."""
    video = Video(
        id="upd_vid_1",
        title="Original Title",
        duration=60,
        duration_formatted="1:00",
        webpage_url="https://youtube.com/watch?v=upd_vid_1",
    )
    db_session.add(video)
    db_session.commit()

    # 1. PATCH update title and duration
    patch_res = client.patch(
        f"{settings.API_PREFIX}/videos/upd_vid_1",
        json={"title": "Updated Title", "duration": 125},
    )
    assert patch_res.status_code == 200
    pdata = patch_res.json()["response"]
    assert pdata["title"] == "Updated Title"
    assert pdata["duration"] == 125
    assert pdata["duration_formatted"] == "2:05"

    # 2. PUT alias
    put_res = client.put(
        f"{settings.API_PREFIX}/videos/upd_vid_1",
        json={"channel_name": "New Channel"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["response"]["channel_name"] == "New Channel"


def test_update_video_not_found(client):
    """PATCH /videos/{video_id} returns 404 for unknown video."""
    res = client.patch(
        f"{settings.API_PREFIX}/videos/nonexistent_id",
        json={"title": "Doesn't exist"},
    )
    assert res.status_code == 404


def test_delete_video_with_file_and_associated_jobs(client, db_session, tmp_path):
    """DELETE /videos/{video_id} removes database row, associated RenderJobs, and downloaded file."""
    fake_file = tmp_path / "del_vid.mp4"
    fake_file.write_bytes(b"content")

    video = Video(
        id="del_vid",
        title="To Delete",
        webpage_url="https://youtube.com/watch?v=del_vid",
        is_downloaded=True,
        local_file_path=str(fake_file),
    )
    job = RenderJob(
        id="job_linked_vid",
        clip_id="clip_linked_vid",
        video_id="del_vid",
        start_seconds=0.0,
        duration_seconds=5.0,
    )
    db_session.add_all([video, job])
    db_session.commit()

    res = client.delete(f"{settings.API_PREFIX}/videos/del_vid?delete_file=true")
    assert res.status_code == 200
    assert res.json()["response"]["status"] == "success"

    # Video must be removed from DB
    assert db_session.query(Video).filter(Video.id == "del_vid").first() is None
    # Associated RenderJob must be removed
    assert (
        db_session.query(RenderJob).filter(RenderJob.video_id == "del_vid").first()
        is None
    )
    # Disk file must be deleted
    assert not fake_file.exists()


def test_delete_video_not_found(client):
    """DELETE /videos/{video_id} returns 404 for unknown video."""
    res = client.delete(f"{settings.API_PREFIX}/videos/unknown_id")
    assert res.status_code == 404


def test_create_render_job_via_jobs_endpoint(client, db_session, monkeypatch, tmp_path):
    """POST /renders/jobs creates a render job and returns 201 Created."""
    from unittest.mock import MagicMock

    dummy_vod = tmp_path / "jobs_endpoint_vid.mp4"
    dummy_vod.write_bytes(b"dummy")

    video = Video(
        id="jobs_endpoint_vid",
        title="Jobs Endpoint Video",
        webpage_url="https://youtube.com/watch?v=jobs_endpoint_vid",
        is_downloaded=True,
        local_file_path=str(dummy_vod),
    )
    db_session.add(video)
    db_session.commit()

    monkeypatch.setattr("app.routers.renders.is_celery_broker_online", lambda: True)
    mock_task = MagicMock()
    mock_task.id = "celery-job-123"
    monkeypatch.setattr(
        "app.services.renders.render_clip_celery_task.delay",
        MagicMock(return_value=mock_task),
    )

    res = client.post(
        f"{settings.API_PREFIX}/renders/jobs",
        json={
            "video_id": "jobs_endpoint_vid",
            "start_seconds": 10.0,
            "duration_seconds": 20.0,
            "crop_preset": "third_person",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["response"]["job_id"] is not None


def test_update_render_job_success(client, db_session):
    """PATCH and PUT /renders/jobs/{job_id} update job fields."""
    job = RenderJob(
        id="upd_render_job_1",
        clip_id="upd_clip_1",
        video_id="v1",
        status="rendering",
        progress=45.0,
        start_seconds=0.0,
        duration_seconds=10.0,
    )
    db_session.add(job)
    db_session.commit()

    # 1. PATCH progress and status
    res = client.patch(
        f"{settings.API_PREFIX}/renders/jobs/upd_render_job_1",
        json={
            "status": "completed",
            "progress": 100.0,
            "crop_preset": "cinematic",
            "is_selected_for_upload": True,
        },
    )
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["status"] == "completed"
    assert data["progress"] == 100.0
    assert data["crop_preset"] == "cinematic"
    assert data["is_selected_for_upload"] is True
    assert data["completed_at"] is not None

    # 2. PUT alias
    put_res = client.put(
        f"{settings.API_PREFIX}/renders/jobs/upd_render_job_1",
        json={"error_message": "test note"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["response"]["error_message"] == "test note"


def test_update_render_job_not_found(client):
    """PATCH /renders/jobs/{job_id} returns 404 for unknown job."""
    res = client.patch(
        f"{settings.API_PREFIX}/renders/jobs/nonexistent_job",
        json={"progress": 50.0},
    )
    assert res.status_code == 404


def test_delete_render_job_success(client, db_session, tmp_path, monkeypatch):
    """DELETE /renders/jobs/{job_id} removes the database job record and clip directory."""
    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))

    clip_dir = tmp_path / "del_job_clip"
    clip_dir.mkdir(parents=True)
    (clip_dir / "landscape.mp4").write_bytes(b"dummy")

    job = RenderJob(
        id="del_job_id",
        clip_id="del_job_clip",
        video_id="v1",
        start_seconds=0.0,
        duration_seconds=5.0,
    )
    db_session.add(job)
    db_session.commit()

    res = client.delete(f"{settings.API_PREFIX}/renders/jobs/del_job_id")
    assert res.status_code == 200
    assert res.json()["response"]["status"] == "deleted"

    # Record and directory must be gone
    assert (
        db_session.query(RenderJob).filter(RenderJob.id == "del_job_id").first() is None
    )
    assert not clip_dir.exists()


def test_delete_render_job_not_found(client):
    """DELETE /renders/jobs/{job_id} returns 404 for unknown job."""
    res = client.delete(f"{settings.API_PREFIX}/renders/jobs/nonexistent_job")
    assert res.status_code == 404


def test_upload_local_video_success(client, db_session, tmp_path, monkeypatch):
    """POST /videos/upload ingests local/OBS recording, creates thumbnail, and catalogues video."""
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(downloads_dir))

    # Generate a lightweight 1-second synthetic video
    sample_mp4 = tmp_path / "obs_test.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=1:size=320x240:rate=15",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(sample_mp4),
        ],
        capture_output=True,
        check=True,
    )

    with open(sample_mp4, "rb") as f:
        response = client.post(
            f"{settings.API_PREFIX}/videos/upload",
            files={"file": ("obs_session_01.mp4", f, "video/mp4")},
            data={"title": "Ranked OBS Match", "channel_name": "Pro Gamer"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    video_item = data["response"]
    assert video_item["id"].startswith("obs_")
    assert video_item["title"] == "Ranked OBS Match"
    assert video_item["channel_name"] == "Pro Gamer"
    assert video_item["is_downloaded"] is True
    assert video_item["download_status"] == "completed"
    assert video_item["duration"] >= 1
    assert video_item["thumbnail_url"] is not None

    # Test thumbnail retrieval endpoint
    thumb_res = client.get(f"{settings.API_PREFIX}/videos/{video_item['id']}/thumbnail")
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"].startswith("image/jpeg")


def test_upload_local_video_unsupported_format(client):
    """POST /videos/upload rejects non-video file formats with 400 Bad Request."""
    response = client.post(
        f"{settings.API_PREFIX}/videos/upload",
        files={"file": ("notes.txt", b"plain text content", "text/plain")},
        data={"title": "Text File"},
    )
    assert response.status_code == 400


def test_render_with_audio_normalization(client, db_session, tmp_path, monkeypatch):
    """POST /renders persists and respects normalize_audio and target_lufs."""
    renders_dir = tmp_path / "renders"
    renders_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "RENDERS_DIR", str(renders_dir))

    norm_file = tmp_path / "norm.mp4"
    norm_file.write_bytes(b"dummy_mp4_bytes")

    v = Video(
        id="norm_vid_1",
        title="Loudness Test Video",
        webpage_url="local://norm_vid_1",
        duration=60,
        is_downloaded=True,
        download_status="completed",
        local_file_path=str(norm_file),
    )
    db_session.add(v)
    db_session.commit()

    payload = {
        "video_id": "norm_vid_1",
        "start_seconds": 0.0,
        "duration_seconds": 10.0,
        "normalize_audio": True,
        "target_lufs": -14.0,
    }
    res = client.post(f"{settings.API_PREFIX}/renders", json=payload)
    assert res.status_code == 200
    job_data = res.json()["response"]
    assert job_data["status"] == "pending"

    # Check database record
    db_job = (
        db_session.query(RenderJob).filter(RenderJob.video_id == "norm_vid_1").first()
    )
    assert db_job is not None
    assert db_job.normalize_audio is True
    assert db_job.target_lufs == -14.0


def test_video_highlight_and_upload_tracking(client, db_session):
    """Test that videos track highlight candidate mining and uploaded highlight metrics."""
    # Video 1: Highlights mined, not downloaded
    v1 = Video(
        id="vid_hl_mined",
        title="Mined Highlights VOD",
        webpage_url="https://youtube.com/watch?v=vid_hl_mined",
        highlight_status="completed",
        is_downloaded=False,
    )
    # Video 2: Downloaded, 1 render uploaded to YouTube Shorts
    v2 = Video(
        id="vid_uploaded_vod",
        title="Uploaded Highlights VOD",
        webpage_url="https://youtube.com/watch?v=vid_uploaded_vod",
        is_downloaded=True,
        download_status="completed",
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    # Add 2 highlight candidates for v1
    c1 = HighlightCandidate(
        id="cand_1",
        video_id="vid_hl_mined",
        start_seconds=10.0,
        end_seconds=25.0,
        duration_seconds=15.0,
        score=0.85,
        event_type="team_wipe",
        details_json="{}",
    )
    c2 = HighlightCandidate(
        id="cand_2",
        video_id="vid_hl_mined",
        start_seconds=40.0,
        end_seconds=55.0,
        duration_seconds=15.0,
        score=0.92,
        event_type="triple_ko",
        details_json="{}",
    )
    db_session.add_all([c1, c2])

    # Add 2 render jobs for v2 (1 uploaded, 1 not uploaded)
    r1 = RenderJob(
        id="job_up_1",
        clip_id="clip_v2_short1",
        video_id="vid_uploaded_vod",
        status="completed",
        start_seconds=10.0,
        duration_seconds=30.0,
        youtube_upload_status="completed",
        youtube_video_id="ShortId123",
        youtube_upload_url="https://www.youtube.com/shorts/ShortId123",
        selected_format="vertical_blur",
    )
    r2 = RenderJob(
        id="job_up_2",
        clip_id="clip_v2_short2",
        video_id="vid_uploaded_vod",
        status="completed",
        start_seconds=60.0,
        duration_seconds=30.0,
        youtube_upload_status="not_uploaded",
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    # Verify single video endpoint for v2
    res_v2 = client.get(f"{settings.API_PREFIX}/videos/vid_uploaded_vod")
    assert res_v2.status_code == 200
    v2_data = res_v2.json()["response"]
    assert v2_data["rendered_clip_count"] == 2
    assert v2_data["uploaded_clip_count"] == 1
    assert v2_data["has_uploaded_highlights"] is True
    assert v2_data["can_cleanup_vod"] is True
    assert len(v2_data["uploaded_highlights"]) == 1
    assert v2_data["uploaded_highlights"][0]["clip_id"] == "clip_v2_short1"
    assert (
        v2_data["uploaded_highlights"][0]["youtube_upload_url"]
        == "https://www.youtube.com/shorts/ShortId123"
    )

    # Verify single video endpoint for v1
    res_v1 = client.get(f"{settings.API_PREFIX}/videos/vid_hl_mined")
    assert res_v1.status_code == 200
    v1_data = res_v1.json()["response"]
    assert v1_data["highlight_candidate_count"] == 2
    assert v1_data["highlight_status"] == "completed"
    assert v1_data["has_uploaded_highlights"] is False

    # Test status filters
    # 1. status=highlights_mined
    res_hl = client.get(f"{settings.API_PREFIX}/videos?status=highlights_mined")
    assert res_hl.status_code == 200
    hl_ids = [item["id"] for item in res_hl.json()["response"]["items"]]
    assert "vid_hl_mined" in hl_ids

    # 2. status=uploaded
    res_up = client.get(f"{settings.API_PREFIX}/videos?status=uploaded")
    assert res_up.status_code == 200
    up_ids = [item["id"] for item in res_up.json()["response"]["items"]]
    assert "vid_uploaded_vod" in up_ids

    # 3. status=cleanup_ready
    res_clean = client.get(f"{settings.API_PREFIX}/videos?status=cleanup_ready")
    assert res_clean.status_code == 200
    clean_ids = [item["id"] for item in res_clean.json()["response"]["items"]]
    assert "vid_uploaded_vod" in clean_ids
    assert "vid_hl_mined" not in clean_ids  # Because v1 is not downloaded


def test_video_storage_cleanup_endpoint(client, db_session, tmp_path):
    """Test POST /api/v1/videos/{video_id}/cleanup reclaims storage and removes files."""
    dummy_vod = settings.downloads_path / "vid_clean_test.mp4"
    dummy_vod.write_bytes(b"0" * 1024 * 100)  # 100 KB

    dummy_render_dir = settings.renders_path / "clip_clean_test_1"
    dummy_render_dir.mkdir(parents=True, exist_ok=True)
    (dummy_render_dir / "short.mp4").write_bytes(b"0" * 1024 * 50)  # 50 KB

    try:
        video = Video(
            id="vid_clean_test",
            title="Clean Test Video",
            webpage_url="https://youtube.com/watch?v=vid_clean_test",
            is_downloaded=True,
            local_file_path=str(dummy_vod),
            file_size_bytes=102400,
            download_status="completed",
        )
        job = RenderJob(
            id="job_clean_1",
            clip_id="clip_clean_test_1",
            video_id="vid_clean_test",
            status="completed",
            start_seconds=0.0,
            duration_seconds=15.0,
            youtube_upload_status="completed",
            youtube_upload_url="https://www.youtube.com/shorts/clean123",
        )
        db_session.add_all([video, job])
        db_session.commit()

        # Run cleanup
        cleanup_res = client.post(
            f"{settings.API_PREFIX}/videos/vid_clean_test/cleanup",
            json={
                "clean_vod": True,
                "clean_uploaded_renders": True,
                "clean_all_renders": False,
            },
        )
        assert cleanup_res.status_code == 200
        payload = cleanup_res.json()["response"]
        assert payload["vod_deleted"] is True
        assert payload["renders_deleted_count"] == 1
        assert payload["reclaimed_bytes"] >= 153600  # 100KB + 50KB

        # Verify files removed from disk
        assert not dummy_vod.exists()
        assert not dummy_render_dir.exists()

        # Verify database video record preserved with download reset
        db_video = db_session.query(Video).filter(Video.id == "vid_clean_test").first()
        assert db_video is not None
        assert db_video.is_downloaded is False
        assert db_video.download_status == "not_downloaded"
    finally:
        if dummy_vod.exists():
            dummy_vod.unlink()
        if dummy_render_dir.exists():
            import shutil

            shutil.rmtree(dummy_render_dir, ignore_errors=True)


def test_list_videos_with_null_highlight_fields(client, db_session):
    """GET /videos successfully serializes videos when database contains NULL highlight and status fields."""
    # Video where highlight columns and download columns are None (e.g. from migrations or manual inserts)
    null_video = Video(
        id="vid_null_fields_test",
        title="Video with Null Fields",
        webpage_url="https://youtube.com/watch?v=vid_null_fields_test",
        duration=120,
        highlight_status=None,
        highlight_progress=None,
        highlight_stage=None,
        download_status=None,
        download_progress=None,
    )
    db_session.add(null_video)
    db_session.commit()

    res = client.get(f"{settings.API_PREFIX}/videos?limit=20&status=all")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    items = data["response"]["items"]
    found = next((item for item in items if item["id"] == "vid_null_fields_test"), None)
    assert found is not None
    assert found["highlight_status"] == "idle"
    assert found["highlight_progress"] == 0.0
    assert found["highlight_stage"] == ""
    assert found["download_status"] == "not_downloaded"
    assert found["download_progress"] == 0.0
