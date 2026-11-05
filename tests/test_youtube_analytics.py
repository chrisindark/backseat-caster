"""Tests for YouTube Short View Velocity Tracker and Optimal Slot Optimizer."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.channel_profile import ChannelProfile
from app.models.render_job import RenderJob
from app.models.video_analytics_snapshot import VideoAnalyticsSnapshot
from app.services.channel_profile import ChannelProfileService
from app.services.youtube_analytics import YouTubeAnalyticsService

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


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


@pytest.fixture
def sample_channel_profile(db_session):
    profile = ChannelProfileService.get_or_create(db_session)
    profile.upload_slots = json.dumps(["08:00", "12:30", "16:00", "18:00", "20:00", "22:00"])
    profile.upload_timezone = "Asia/Kolkata"
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture
def sample_uploaded_jobs(db_session, sample_channel_profile):
    ist = ZoneInfo("Asia/Kolkata")
    # Base date: Nov 2, 2026
    dt_1800 = datetime(2026, 11, 2, 18, 0, tzinfo=ist).astimezone(UTC)
    dt_2000 = datetime(2026, 11, 2, 20, 0, tzinfo=ist).astimezone(UTC)
    dt_1230 = datetime(2026, 11, 2, 12, 30, tzinfo=ist).astimezone(UTC)

    j1 = RenderJob(
        id="job_analytics_1",
        clip_id="clip_1",
        video_id="vid_1",
        start_seconds=0.0,
        duration_seconds=30.0,
        status="completed",
        youtube_video_id="yt_vid_1",
        youtube_upload_status="completed",
        youtube_uploaded_at=dt_1800,
        scheduled_publish_at=dt_1800,
        latest_view_count=2400,
        latest_like_count=120,
        latest_comment_count=15,
        velocity_3h=850,
        velocity_24h=2400,
    )
    j2 = RenderJob(
        id="job_analytics_2",
        clip_id="clip_2",
        video_id="vid_1",
        start_seconds=0.0,
        duration_seconds=30.0,
        status="completed",
        youtube_video_id="yt_vid_2",
        youtube_upload_status="completed",
        youtube_uploaded_at=dt_1800 + timedelta(minutes=3),
        scheduled_publish_at=dt_1800 + timedelta(minutes=3),
        latest_view_count=1800,
        latest_like_count=90,
        latest_comment_count=10,
        velocity_3h=600,
        velocity_24h=1800,
    )
    j3 = RenderJob(
        id="job_analytics_3",
        clip_id="clip_3",
        video_id="vid_1",
        start_seconds=0.0,
        duration_seconds=30.0,
        status="completed",
        youtube_video_id="yt_vid_3",
        youtube_upload_status="completed",
        youtube_uploaded_at=dt_2000,
        scheduled_publish_at=dt_2000,
        latest_view_count=1200,
        latest_like_count=50,
        latest_comment_count=5,
        velocity_3h=400,
        velocity_24h=1200,
    )
    j4 = RenderJob(
        id="job_analytics_4",
        clip_id="clip_4",
        video_id="vid_1",
        start_seconds=0.0,
        duration_seconds=30.0,
        status="completed",
        youtube_video_id="yt_vid_4",
        youtube_upload_status="completed",
        youtube_uploaded_at=dt_1230,
        scheduled_publish_at=dt_1230,
        latest_view_count=350,
        latest_like_count=12,
        latest_comment_count=2,
        velocity_3h=100,
        velocity_24h=350,
    )
    db_session.add_all([j1, j2, j3, j4])
    db_session.commit()
    return [j1, j2, j3, j4]


def test_get_slot_analytics(db_session, sample_uploaded_jobs):
    analytics = YouTubeAnalyticsService.get_slot_analytics(db_session)
    assert analytics["timezone"] == "Asia/Kolkata"
    assert analytics["total_tracked_videos"] == 4

    slots = {s["slot"]: s for s in analytics["slots"]}
    assert "18:00" in slots
    assert "20:00" in slots
    assert "12:30" in slots

    # 18:00 slot has 2 videos (j1 and j2)
    s18 = slots["18:00"]
    assert s18["videos_count"] == 2
    assert s18["avg_views"] == 2100.0  # (2400 + 1800) / 2
    assert s18["avg_velocity_3h"] == 725.0  # (850 + 600) / 2
    assert s18["avg_velocity_24h"] == 2100.0

    # 18:00 should be rank 1
    assert s18["rank"] == 1
    assert s18["recommended"] is True

    # 12:30 should have lowest views
    s12 = slots["12:30"]
    assert s12["avg_views"] == 350.0
    assert s12["rank"] > 1

    assert "18:00" in analytics["recommended_slots"]


def test_apply_optimal_slots(db_session, sample_uploaded_jobs):
    res = YouTubeAnalyticsService.apply_optimal_slots(db_session, top_n=3)
    assert "applied_slots" in res
    assert len(res["applied_slots"]) >= 2
    assert "18:00" in res["applied_slots"]

    # Check updated channel profile
    profile = ChannelProfileService.get_or_create(db_session)
    slots = json.loads(profile.upload_slots)
    assert "18:00" in slots


def test_poll_video_statistics_mocked(db_session, sample_uploaded_jobs, monkeypatch):
    mock_youtube = MagicMock()
    mock_request = MagicMock()
    mock_request.execute.return_value = {
        "items": [
            {
                "id": "yt_vid_1",
                "statistics": {
                    "viewCount": "2550",
                    "likeCount": "130",
                    "commentCount": "18",
                },
            },
            {
                "id": "yt_vid_2",
                "statistics": {
                    "viewCount": "1920",
                    "likeCount": "95",
                    "commentCount": "12",
                },
            },
        ]
    }
    mock_youtube.videos.return_value.list.return_value = mock_request

    monkeypatch.setattr(
        "app.services.youtube_analytics.YouTubeUploaderService.get_credentials",
        lambda: MagicMock(valid=True),
    )
    monkeypatch.setattr(
        "app.services.youtube_analytics.build",
        lambda *args, **kwargs: mock_youtube,
    )

    result = YouTubeAnalyticsService.poll_video_statistics(db_session, max_age_days=14)
    assert result["updated_count"] == 2
    assert result["snapshots_created"] == 2

    # Verify updated job metrics in DB
    j1 = db_session.query(RenderJob).filter(RenderJob.id == "job_analytics_1").first()
    assert j1.latest_view_count == 2550
    assert j1.latest_like_count == 130
    assert j1.latest_comment_count == 18
    assert j1.metrics_last_polled_at is not None

    # Verify snapshots created
    snaps = (
        db_session.query(VideoAnalyticsSnapshot)
        .filter(VideoAnalyticsSnapshot.job_id == "job_analytics_1")
        .all()
    )
    assert len(snaps) == 1
    assert snaps[0].view_count == 2550


def test_get_clip_velocity_timeline(db_session, sample_uploaded_jobs):
    now_utc = datetime.now(UTC)
    s1 = VideoAnalyticsSnapshot(
        job_id="job_analytics_1",
        clip_id="clip_1",
        youtube_video_id="yt_vid_1",
        recorded_at=now_utc - timedelta(hours=2),
        hours_since_publish=1.0,
        view_count=200,
        like_count=10,
    )
    s2 = VideoAnalyticsSnapshot(
        job_id="job_analytics_1",
        clip_id="clip_1",
        youtube_video_id="yt_vid_1",
        recorded_at=now_utc - timedelta(hours=1),
        hours_since_publish=2.0,
        view_count=650,
        like_count=35,
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    timeline = YouTubeAnalyticsService.get_clip_velocity_timeline(db_session, "clip_1")
    assert timeline["clip_id"] == "clip_1"
    assert len(timeline["snapshots"]) == 2
    assert timeline["snapshots"][0]["views"] == 200
    assert timeline["snapshots"][1]["views"] == 650


def test_analytics_api_endpoints(client, db_session, sample_uploaded_jobs, monkeypatch):
    # 1. GET /youtube/analytics/slots
    res = client.get(f"/api/v1/youtube/analytics/slots")
    assert res.status_code == 200
    data = res.json()["response"]
    assert data["timezone"] == "Asia/Kolkata"
    assert len(data["slots"]) > 0

    # 2. POST /youtube/analytics/apply-optimal-slots
    res_apply = client.post(f"/api/v1/youtube/analytics/apply-optimal-slots?top_n=3")
    assert res_apply.status_code == 200
    applied_data = res_apply.json()["response"]
    assert len(applied_data["applied_slots"]) >= 2

    # 3. GET /youtube/analytics/timeline/clip_1
    res_timeline = client.get(f"/api/v1/youtube/analytics/timeline/clip_1")
    assert res_timeline.status_code == 200
    timeline_data = res_timeline.json()["response"]
    assert timeline_data["clip_id"] == "clip_1"


# --- Quota throttle tests ---

from app.services.youtube_errors import backoff_delay as _backoff_delay
from app.services.youtube_quota import YouTubeQuotaService as _QuotaService


def test_analytics_quota_gate_blocks_at_threshold(db_session):
    # Analytics budget is 2,000 units by default — exhausting it blocks sync
    _QuotaService.record_units_used(db_session, 2000)
    gate = _QuotaService.check_analytics_budget(db_session)
    assert gate["can_analytics"] is False
    assert gate["analytics_block_reason"] == "analytics_budget_exceeded"

    result = YouTubeAnalyticsService.poll_video_statistics(db_session)
    assert result.get("skipped") is True
    assert result["polled_count"] == 0


def test_upload_and_analytics_have_separate_gates(db_session):
    # 6 uploads (9,600 total units) exhaust the 8,000 upload budget
    for _ in range(6):
        _QuotaService.record_upload_success(db_session)
    summary = _QuotaService.get_summary(db_session)
    assert summary["uploads_remaining"] == 0
    assert summary["can_upload"] is False
    # ...but analytics (2,000 budget, 0 used) is still open
    assert summary["can_analytics"] is True
    assert summary["analytics_units_remaining"] == 2000
    # Analytics still fails the shared pool — 9,600/10,000 leaves 400 units
    assert summary["units_used"] == 9600


def test_analytics_quota_gate_allows_upload_limit_block(db_session):
    # uploadLimitExceeded should NOT block analytics reads
    from datetime import datetime, timedelta, UTC

    usage = _QuotaService.get_or_create_usage(db_session)
    usage.blocked_reason = "upload_limit_exceeded"
    usage.blocked_until = datetime.now(UTC) + timedelta(hours=1)
    db_session.commit()
    gate = _QuotaService.check_analytics_budget(db_session)
    # uploads blocked, analytics NOT blocked by upload limit
    assert gate["can_upload"] is False
    assert gate["can_analytics"] is True
    assert gate["analytics_block_reason"] is None


def test_backoff_delay_exponential():
    assert _backoff_delay(0) == 2.0
    assert _backoff_delay(1) == 4.0
    assert _backoff_delay(2) == 8.0
    # capped
    assert _backoff_delay(20, base_seconds=2.0, max_seconds=120.0) == 120.0


def test_celery_rate_limits_configured():
    from app.worker.celery_app import celery_app

    assert celery_app.conf.task_default_rate_limit == "10/m"
    annotations = celery_app.conf.task_annotations or {}
    assert annotations.get("upload_clip_celery_task", {}).get("rate_limit") == "1/m"
    assert annotations.get("batch_upload_clips_celery_task", {}).get("rate_limit") == "1/m"
    from app.services.youtube_analytics import sync_video_analytics_celery_task

    assert sync_video_analytics_celery_task.rate_limit == "10/m"
    from app.services.youtube_uploader import upload_clip_celery_task

    assert upload_clip_celery_task.rate_limit == "1/m"


def test_quota_summary_exposes_throttle_fields(db_session):
    summary = _QuotaService.get_summary(db_session)
    assert summary["can_analytics"] is True
    assert summary["analytics_threshold"] == 0.8
    assert summary["analytics_batch_limit"] == 50
    assert summary["usage_fraction"] == 0.0
    assert summary["upload_budget_units"] == 8000
    assert summary["analytics_budget_units"] == 2000
