"""Tests for tagging videos as ignored / do not process (both BE and FE contract)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.highlight_candidate import HighlightCandidate
from app.models.video import Video
from app.services.auto_mine import AutoMineService
from app.services.auto_stage import AutoStageService

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


def _create_test_video(
    db_session,
    video_id: str,
    is_downloaded: bool = False,
    is_ignored: bool = False,
    ignore_reason: str | None = None,
) -> Video:
    vid = Video(
        id=video_id,
        title=f"Test Video {video_id}",
        description="Test description",
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        duration=300,
        duration_formatted="5:00",
        channel_name="Pro Gamer",
        is_downloaded=is_downloaded,
        download_status="completed" if is_downloaded else "not_downloaded",
        local_file_path=f"/tmp/{video_id}.mp4" if is_downloaded else None,
        is_ignored=is_ignored,
        ignore_reason=ignore_reason,
    )
    db_session.add(vid)
    db_session.commit()
    db_session.refresh(vid)
    return vid


def test_update_video_tag_as_ignored(client: TestClient, db_session):
    vid = _create_test_video(db_session, "vid_tag_1")

    # Tag as ignored with reason
    resp = client.patch(
        f"{settings.API_PREFIX}/videos/{vid.id}",
        json={
            "is_ignored": True,
            "ignore_reason": "Too old or low quality gameplay",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["response"]["is_ignored"] is True
    assert data["response"]["ignore_reason"] == "Too old or low quality gameplay"

    # Untag / mark active
    resp2 = client.patch(
        f"{settings.API_PREFIX}/videos/{vid.id}",
        json={
            "is_ignored": False,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["response"]["is_ignored"] is False
    assert data2["response"]["ignore_reason"] is None


def test_batch_tag_videos(client: TestClient, db_session):
    vid1 = _create_test_video(db_session, "batch_vid_1")
    vid2 = _create_test_video(db_session, "batch_vid_2")
    vid3 = _create_test_video(db_session, "batch_vid_3")

    # Batch tag vid1 and vid2 as ignored
    resp = client.post(
        f"{settings.API_PREFIX}/videos/batch-tag",
        json={
            "video_ids": [vid1.id, vid2.id],
            "is_ignored": True,
            "ignore_reason": "Outdated test match",
        },
    )
    assert resp.status_code == 200
    body = resp.json()["response"]
    assert body["updated_count"] == 2
    assert set(body["video_ids"]) == {vid1.id, vid2.id}
    assert body["is_ignored"] is True

    # Check database
    db_session.refresh(vid1)
    db_session.refresh(vid2)
    db_session.refresh(vid3)
    assert vid1.is_ignored is True
    assert vid1.ignore_reason == "Outdated test match"
    assert vid2.is_ignored is True
    assert vid3.is_ignored is False

    # Batch un-tag
    resp_unmark = client.post(
        f"{settings.API_PREFIX}/videos/batch-tag",
        json={
            "video_ids": [vid1.id, vid2.id],
            "is_ignored": False,
        },
    )
    assert resp_unmark.status_code == 200
    db_session.refresh(vid1)
    db_session.refresh(vid2)
    assert vid1.is_ignored is False
    assert vid1.ignore_reason is None
    assert vid2.is_ignored is False


def test_list_videos_ignored_status_filter(client: TestClient, db_session):
    _create_test_video(db_session, "active_vid_1", is_ignored=False)
    _create_test_video(db_session, "ignored_vid_1", is_ignored=True, ignore_reason="Old VOD")
    _create_test_video(db_session, "ignored_vid_2", is_ignored=True, ignore_reason="Boring match")

    # Filter status=ignored
    resp = client.get(f"{settings.API_PREFIX}/videos?status=ignored")
    assert resp.status_code == 200
    items = resp.json()["response"]["items"]
    ids = [item["id"] for item in items]
    assert "ignored_vid_1" in ids
    assert "ignored_vid_2" in ids
    assert "active_vid_1" not in ids

    # Filter status=not_downloaded should NOT include ignored videos
    resp_not_dl = client.get(f"{settings.API_PREFIX}/videos?status=not_downloaded")
    assert resp_not_dl.status_code == 200
    not_dl_ids = [item["id"] for item in resp_not_dl.json()["response"]["items"]]
    assert "active_vid_1" in not_dl_ids
    assert "ignored_vid_1" not in not_dl_ids
    assert "ignored_vid_2" not in not_dl_ids


def test_cannot_download_ignored_video(client: TestClient, db_session):
    vid = _create_test_video(db_session, "dl_block_vid", is_ignored=True, ignore_reason="Too old")

    resp = client.post(f"{settings.API_PREFIX}/videos/{vid.id}/download", json={})
    assert resp.status_code == 400
    data = resp.json()
    error_msg = data.get("error_message") or ""
    assert "Do Not Process" in error_msg or "ignored" in error_msg


def test_cannot_detect_highlights_on_ignored_video(client: TestClient, db_session):
    vid = _create_test_video(db_session, "hl_block_vid", is_downloaded=True, is_ignored=True)

    resp = client.post(f"{settings.API_PREFIX}/videos/{vid.id}/highlights/detect", json={})
    assert resp.status_code == 400
    data = resp.json()
    error_msg = data.get("error_message") or ""
    assert "Do Not Process" in error_msg or "ignored" in error_msg


def test_cannot_create_render_for_ignored_video(client: TestClient, db_session, tmp_path):
    dummy_file = tmp_path / "render_block_vid.mp4"
    dummy_file.write_bytes(b"dummy")

    vid = _create_test_video(db_session, "render_block_vid", is_downloaded=True, is_ignored=True)
    vid.local_file_path = str(dummy_file)
    db_session.commit()

    resp = client.post(
        f"{settings.API_PREFIX}/renders",
        json={
            "video_id": vid.id,
            "start_seconds": 0,
            "duration_seconds": 15,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    error_msg = data.get("error_message") or ""
    assert "Do Not Process" in error_msg or "ignored" in error_msg


def test_auto_mine_skips_ignored_video(db_session, tmp_path):
    dummy_file = tmp_path / "mine_ignored.mp4"
    dummy_file.write_bytes(b"dummy")

    vid = _create_test_video(db_session, "mine_ignored", is_downloaded=True, is_ignored=True)
    vid.local_file_path = str(dummy_file)
    db_session.commit()

    should_mine, reason = AutoMineService.should_mine(vid)
    assert should_mine is False
    assert "ignored" in reason


def test_auto_stage_skips_ignored_video(db_session):
    vid = _create_test_video(db_session, "stage_ignored", is_downloaded=True, is_ignored=True)
    cand = HighlightCandidate(
        id="cand_ign_1",
        video_id=vid.id,
        start_seconds=10.0,
        end_seconds=25.0,
        duration_seconds=15.0,
        score=0.95,
        event_type="test_event",
        details_json="{}",
    )
    db_session.add(cand)
    db_session.commit()

    result = AutoStageService.stage_top_candidates(db_session, vid.id)
    assert result["staged_count"] == 0
    assert "ignored" in result["message"]
