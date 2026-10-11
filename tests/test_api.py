"""Tests for BackseatCaster API endpoints and BaseResponse envelope."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
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
    assert data["error_code"] == None


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
