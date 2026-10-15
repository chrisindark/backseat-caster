"""Unit and integration tests for YouTube OAuth authentication and video/shorts uploading."""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.render_job import RenderJob
from app.schemas.youtube import YouTubeAuthStatusResponse
from app.services.youtube_uploader import YouTubeUploaderService

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False
)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


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


def test_youtube_auth_status_unauthenticated(client, monkeypatch):
    """When no credentials are saved, status reports unauthenticated."""
    monkeypatch.setattr(YouTubeUploaderService, "get_credentials", lambda: None)
    monkeypatch.setattr(YouTubeUploaderService, "get_client_config", lambda: None)

    res = client.get(f"{settings.API_PREFIX}/youtube/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["response"]["is_authenticated"] is False
    assert data["response"]["client_configured"] is False


def test_youtube_auth_status_authenticated(client, monkeypatch):
    """When credentials exist, status returns channel info."""
    mock_creds = MagicMock()
    mock_creds.scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    mock_creds.expiry = None

    monkeypatch.setattr(YouTubeUploaderService, "get_credentials", lambda: mock_creds)
    monkeypatch.setattr(
        YouTubeUploaderService, "get_client_config", lambda: {"web": {}}
    )
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_channel_info",
        lambda creds: {
            "channel_title": "Chris Gaming",
            "channel_id": "UC1234567890",
            "channel_handle": "@chrisgaming",
            "thumbnail_url": "https://example.com/thumb.jpg",
        },
    )

    res = client.get(f"{settings.API_PREFIX}/youtube/auth/status")
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["is_authenticated"] is True
    assert data["channel_title"] == "Chris Gaming"
    assert data["channel_id"] == "UC1234567890"


def test_youtube_auth_url_without_client_config(client, monkeypatch):
    """Generating auth URL without configured credentials returns 400 with helpful error."""
    monkeypatch.setattr(YouTubeUploaderService, "get_client_config", lambda: None)

    res = client.get(f"{settings.API_PREFIX}/youtube/auth/url")
    assert res.status_code == 400
    assert "credentials not found" in res.json()["error_message"]


def test_youtube_auth_url_success(client, monkeypatch):
    """Generating auth URL with credentials returns valid OAuth URL."""
    fake_config = {
        "web": {
            "client_id": "fake-client-id.apps.googleusercontent.com",
            "client_secret": "fake-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8000/api/v1/youtube/auth/callback"],
        }
    }
    monkeypatch.setattr(
        YouTubeUploaderService, "get_client_config", lambda: fake_config
    )

    res = client.get(f"{settings.API_PREFIX}/youtube/auth/url")
    assert res.status_code == 200
    data = res.json()["response"]
    assert "accounts.google.com" in data["auth_url"]
    assert data["client_id"] == "fake-client-id.apps.googleusercontent.com"


def test_youtube_configure_credentials(client, tmp_path, monkeypatch):
    """User can configure client credentials via endpoint."""
    fake_file = tmp_path / "secrets.json"
    monkeypatch.setattr(settings, "YOUTUBE_CLIENT_SECRETS_FILE", str(fake_file))

    payload = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }
    res = client.post(f"{settings.API_PREFIX}/youtube/auth/credentials", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert fake_file.exists()


def test_youtube_auth_revoke(client, monkeypatch):
    """Revoking YouTube credentials removes stored token."""
    mock_revoke = MagicMock(return_value=True)
    monkeypatch.setattr(YouTubeUploaderService, "revoke_credentials", mock_revoke)

    res = client.post(f"{settings.API_PREFIX}/youtube/auth/revoke")
    assert res.status_code == 200
    assert res.json()["response"]["revoked"] is True


def test_youtube_upload_unauthorized_error(client, db_session, monkeypatch):
    """Attempting upload when unauthenticated returns 401."""
    job = RenderJob(
        id="job_unauth_test",
        clip_id="clip_unauth_test",
        video_id="vid_1",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=15.0,
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_auth_status",
        lambda: YouTubeAuthStatusResponse(is_authenticated=False),
    )

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/clip_unauth_test",
        json={"title": "Test Title", "sync": True},
    )
    assert res.status_code == 401
    assert "not authenticated" in res.json()["error_message"].lower()


def test_youtube_upload_short_synchronous(client, db_session, tmp_path, monkeypatch):
    """Upload a vertical clip (<60s) as a YouTube Short synchronously."""
    clip_id = "test_short_clip_123"
    clip_dir = tmp_path / clip_id
    clip_dir.mkdir(parents=True)
    video_file = clip_dir / "vertical_blur.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")

    manifest_file = clip_dir / "manifest.json"
    manifest_data = {
        "clip_id": clip_id,
        "clip": {"start_seconds": 10.0, "duration_seconds": 25.0},
        "upload_selection": {
            "title": "Epic 5K Elimination",
            "description": "Insane team wipe with Hawkeye!",
            "tags": ["gaming", "rivals"],
            "privacy": "unlisted",
            "preferred_format": "vertical_blur",
        },
    }
    manifest_file.write_text(json.dumps(manifest_data))

    job = RenderJob(
        id=f"job_{clip_id}",
        clip_id=clip_id,
        video_id="vid_parent_1",
        status="completed",
        progress=100.0,
        start_seconds=10.0,
        duration_seconds=25.0,
        selected_format="vertical_blur",
        is_selected_for_upload=True,
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_auth_status",
        lambda: YouTubeAuthStatusResponse(is_authenticated=True),
    )
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_credentials",
        lambda: MagicMock(),
    )

    # Mock googleapiclient build and resumable upload
    mock_insert = MagicMock()
    # next_chunk returns (status, response)
    mock_status = MagicMock()
    mock_status.progress.return_value = 1.0
    mock_insert.next_chunk.side_effect = [
        (mock_status, None),
        (mock_status, {"id": "fake_yt_short_id_456"}),
    ]

    mock_videos = MagicMock()
    mock_videos.insert.return_value = mock_insert
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value = mock_videos

    monkeypatch.setattr(
        "app.services.youtube_uploader.build", lambda *a, **kw: mock_youtube
    )

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/{clip_id}",
        json={"sync": True, "privacy": "unlisted"},
    )
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["youtube_video_id"] == "fake_yt_short_id_456"
    assert "https://www.youtube.com/shorts/fake_yt_short_id_456" in data["youtube_url"]
    assert data["is_short"] is True
    assert "#Shorts" in data["title"]
    assert data["status"] == "completed"

    # Verify database job was updated
    updated_job = (
        db_session.query(RenderJob).filter(RenderJob.clip_id == clip_id).first()
    )
    assert updated_job.youtube_video_id == "fake_yt_short_id_456"
    assert updated_job.youtube_upload_status == "completed"
    assert updated_job.youtube_upload_progress == 100.0


def test_youtube_upload_landscape_video(client, db_session, tmp_path, monkeypatch):
    """Upload a landscape video as standard video without forced Shorts URL."""
    clip_id = "test_landscape_clip_789"
    clip_dir = tmp_path / clip_id
    clip_dir.mkdir(parents=True)
    video_file = clip_dir / "landscape.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")

    job = RenderJob(
        id=f"job_{clip_id}",
        clip_id=clip_id,
        video_id="vid_parent_1",
        status="completed",
        progress=100.0,
        start_seconds=0.0,
        duration_seconds=90.0,
        selected_format="landscape",
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
    mock_insert.next_chunk.return_value = (mock_status, {"id": "fake_yt_long_id_999"})

    mock_videos = MagicMock()
    mock_videos.insert.return_value = mock_insert
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value = mock_videos
    monkeypatch.setattr(
        "app.services.youtube_uploader.build", lambda *a, **kw: mock_youtube
    )

    res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/{clip_id}",
        json={"sync": True, "format": "landscape", "is_short": False},
    )
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["youtube_video_id"] == "fake_yt_long_id_999"
    assert "https://youtu.be/fake_yt_long_id_999" in data["youtube_url"]
    assert data["is_short"] is False


def test_youtube_upload_selected_batch(client, db_session, tmp_path, monkeypatch):
    """Upload all selected clips via /api/v1/youtube/upload/selected."""
    # Create two clips
    for cid in ["batch_clip_1", "batch_clip_2"]:
        cdir = tmp_path / cid
        cdir.mkdir(parents=True)
        (cdir / "vertical_blur.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
        job = RenderJob(
            id=f"job_{cid}",
            clip_id=cid,
            video_id="vid_batch",
            status="completed",
            progress=100.0,
            start_seconds=0.0,
            duration_seconds=15.0,
            is_selected_for_upload=True,
            selected_format="vertical_blur",
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

    # Mock insert
    mock_insert = MagicMock()
    mock_insert.next_chunk.side_effect = [
        (MagicMock(progress=lambda: 1.0), {"id": "batch_id_1"}),
        (MagicMock(progress=lambda: 1.0), {"id": "batch_id_2"}),
    ]
    mock_videos = MagicMock()
    mock_videos.insert.return_value = mock_insert
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value = mock_videos
    monkeypatch.setattr(
        "app.services.youtube_uploader.build", lambda *a, **kw: mock_youtube
    )

    res = client.post(f"{settings.API_PREFIX}/youtube/upload/selected?sync=true")
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["total_requested"] == 2
    assert data["total_succeeded"] == 2
    assert len(data["results"]) == 2


def test_youtube_pkce_flow_caching_and_exchange(tmp_path, monkeypatch):
    """PKCE code_verifier is generated and cached on auth URL generation, then consumed on code exchange."""
    states_file = tmp_path / "youtube_oauth_states.json"
    monkeypatch.setattr(
        YouTubeUploaderService, "_get_states_file_path", lambda: states_file
    )

    fake_config = {
        "web": {
            "client_id": "test-client.apps.googleusercontent.com",
            "client_secret": "test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8000/api/v1/youtube/auth/callback"],
        }
    }
    monkeypatch.setattr(
        YouTubeUploaderService, "get_client_config", lambda: fake_config
    )

    # 1. Generate Auth URL
    auth_resp = YouTubeUploaderService.generate_auth_url()
    assert auth_resp.state is not None
    assert "https://accounts.google.com" in auth_resp.auth_url

    # Check that PKCE verifier was stored
    cached_states = YouTubeUploaderService._load_oauth_states()
    assert auth_resp.state in cached_states
    stored_verifier = cached_states[auth_resp.state]["code_verifier"]
    assert stored_verifier is not None
    assert len(stored_verifier) > 10

    # 2. Exchange code with state
    mock_flow_instance = MagicMock()
    mock_flow_instance.credentials = MagicMock()
    mock_flow_class = MagicMock()
    mock_flow_class.from_client_config.return_value = mock_flow_instance

    monkeypatch.setattr("app.services.youtube_uploader.Flow", mock_flow_class)
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_channel_info",
        lambda creds: {"channel_title": "PKCE Gamer", "channel_id": "UC_PKCE"},
    )
    monkeypatch.setattr(YouTubeUploaderService, "save_credentials", lambda creds: None)

    channel_info = YouTubeUploaderService.exchange_code(
        code="test_auth_code_123", state=auth_resp.state
    )
    assert channel_info["channel_title"] == "PKCE Gamer"
    assert mock_flow_instance.code_verifier == stored_verifier
    mock_flow_instance.fetch_token.assert_called_once_with(
        code="test_auth_code_123", code_verifier=stored_verifier
    )

    # State must be consumed after single use
    remaining_states = YouTubeUploaderService._load_oauth_states()
    assert auth_resp.state not in remaining_states


def test_youtube_auth_callback_redirect_endpoint(client, monkeypatch):
    """GET /auth/callback exchanges code & state and returns HTML confirmation."""
    mock_exchange = MagicMock(return_value={"channel_title": "Chris Plays"})
    monkeypatch.setattr(YouTubeUploaderService, "exchange_code", mock_exchange)

    res = client.get(
        f"{settings.API_PREFIX}/youtube/auth/callback?code=mock_code&state=mock_state"
    )
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "YouTube Connected!" in res.text
    assert "Chris Plays" in res.text
    mock_exchange.assert_called_once_with(code="mock_code", state="mock_state")


def test_youtube_auth_callback_post_endpoint(client, monkeypatch):
    """POST /auth/callback accepts JSON with code, state, and optional verifier."""
    mock_exchange = MagicMock(return_value={"channel_title": "Chris Plays"})
    monkeypatch.setattr(YouTubeUploaderService, "exchange_code", mock_exchange)

    payload = {
        "code": "json_code_123",
        "state": "json_state_456",
        "code_verifier": "explicit_verifier_789",
    }
    res = client.post(f"{settings.API_PREFIX}/youtube/auth/callback", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["response"]["channel_title"] == "Chris Plays"
    mock_exchange.assert_called_once_with(
        code="json_code_123",
        redirect_uri=None,
        state="json_state_456",
        code_verifier="explicit_verifier_789",
    )


def test_youtube_upload_preserves_and_syncs_metadata_and_public_privacy(
    client, db_session, tmp_path, monkeypatch
):
    """
    Ensure selecting a render generates non-null metadata defaults with public privacy,
    and uploading synchronizes job.upload_metadata in DB and sends privacyStatus: public to YouTube.
    """
    clip_id = "test_public_clip_sync"
    clip_dir = tmp_path / clip_id
    clip_dir.mkdir(parents=True)
    video_file = clip_dir / "third_person.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")

    manifest_file = clip_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "clip_id": clip_id,
                "clip": {"start_seconds": 10.0, "duration_seconds": 20.0},
                "outputs": {"third_person": {"file_path": str(video_file)}},
            }
        )
    )

    job = RenderJob(
        id=f"job_{clip_id}",
        clip_id=clip_id,
        video_id="sample_vid",
        status="completed",
        progress=100.0,
        start_seconds=10.0,
        duration_seconds=20.0,
        selected_format="third_person",
        is_selected_for_upload=False,
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path))

    # 1. Select clip for upload without passing title/desc/tags
    sel_res = client.post(
        f"{settings.API_PREFIX}/renders/{clip_id}/upload-selection",
        json={"is_selected": True, "preferred_format": "third_person"},
    )
    assert sel_res.status_code == 200
    sel_data = sel_res.json()["response"]["upload_selection"]
    assert sel_data["is_selected"] is True
    assert sel_data["privacy"] == "public"
    assert sel_data["title"] is not None
    assert sel_data["description"] is not None
    assert len(sel_data["tags"]) > 0

    # Verify DB upload_metadata
    db_session.refresh(job)
    db_meta = json.loads(job.upload_metadata)
    assert db_meta["privacy"] == "public"
    assert db_meta["title"] is not None
    assert db_meta["description"] is not None
    assert len(db_meta["tags"]) > 0

    # 2. Upload clip with custom title, description, tags and public privacy
    monkeypatch.setattr(
        YouTubeUploaderService,
        "get_auth_status",
        lambda: YouTubeAuthStatusResponse(is_authenticated=True),
    )
    monkeypatch.setattr(YouTubeUploaderService, "get_credentials", lambda: MagicMock())

    captured_body = {}
    mock_insert = MagicMock()
    mock_status = MagicMock()
    mock_status.progress.return_value = 1.0
    mock_insert.next_chunk.side_effect = [
        (mock_status, None),
        (mock_status, {"id": "yt_public_video_id"}),
    ]

    mock_videos = MagicMock()

    def mock_insert_call(part, body, media_body):
        captured_body.update(body)
        return mock_insert

    mock_videos.insert.side_effect = mock_insert_call
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value = mock_videos

    monkeypatch.setattr(
        "app.services.youtube_uploader.build", lambda *a, **kw: mock_youtube
    )

    upload_payload = {
        "title": "Custom Epic Public Highlight",
        "description": "Public highlight description",
        "tags": ["gaming", "public", "shorts"],
        "privacy": "public",
        "sync": True,
    }
    up_res = client.post(
        f"{settings.API_PREFIX}/youtube/upload/{clip_id}",
        json=upload_payload,
    )
    assert up_res.status_code == 200
    up_data = up_res.json()["response"]
    assert up_data["status"] == "completed"
    assert up_data["privacy"] == "public"

    # Verify that YouTube API received privacyStatus: public
    assert captured_body["status"]["privacyStatus"] == "public"
    assert captured_body["snippet"]["title"] == "Custom Epic Public Highlight #Shorts"

    # Verify DB job record has updated upload_metadata with title, desc, tags, privacy
    db_session.refresh(job)
    final_db_meta = json.loads(job.upload_metadata)
    assert final_db_meta["title"] == "Custom Epic Public Highlight #Shorts"
    assert "Public highlight description" in final_db_meta["description"]
    assert "gaming" in final_db_meta["tags"]
    assert final_db_meta["privacy"] == "public"
