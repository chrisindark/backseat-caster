"""Tests for Tier 3 channel brand consistency."""

import base64
from datetime import UTC, datetime

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
from app.services.auto_stage import AutoStageService

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)

# 1x1 transparent PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
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


def test_channel_profile_defaults_and_update(client):
    res = client.get(f"{settings.API_PREFIX}/channel/profile")
    assert res.status_code == 200
    profile = res.json()["response"]
    assert profile["default_framing_preset"] == "third_person"
    assert profile["default_quality_preset"] == "high"
    assert profile["default_privacy"] == "public"
    assert profile["upload_slots"]

    updated = client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={
            "channel_name": "NightOwl",
            "default_framing_preset": "cinematic",
            "default_quality_preset": "compact",
            "title_template": "{title} | {channel}",
            "pinned_hashtags": ["#Shorts", "NightOwl"],
            "default_privacy": "unlisted",
            "upload_slots": ["9:05", "18:30"],
            "upload_timezone": "Asia/Kolkata",
        },
    )
    assert updated.status_code == 200
    body = updated.json()["response"]
    assert body["channel_name"] == "NightOwl"
    assert body["default_framing_preset"] == "cinematic"
    assert body["default_quality_preset"] == "compact"
    assert body["pinned_hashtags"] == ["Shorts", "NightOwl"]
    assert body["upload_slots"] == ["09:05", "18:30"]
    assert body["upload_timezone"] == "Asia/Kolkata"


def test_watermark_upload_preview_and_delete(client):
    res = client.post(
        f"{settings.API_PREFIX}/channel/watermark",
        files={"file": ("logo.png", TINY_PNG, "image/png")},
    )
    assert res.status_code == 200
    payload = res.json()["response"]
    assert payload["profile"]["has_watermark"] is True
    assert payload["profile"]["watermark_enabled"] is True
    assert payload["filename"] == "watermark.png"

    preview = client.get(f"{settings.API_PREFIX}/channel/watermark")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"

    removed = client.delete(f"{settings.API_PREFIX}/channel/watermark")
    assert removed.status_code == 200
    assert removed.json()["response"]["has_watermark"] is False


def test_watermark_rejects_non_image(client):
    res = client.post(
        f"{settings.API_PREFIX}/channel/watermark",
        files={"file": ("logo.png", b"not an image", "image/png")},
    )
    assert res.status_code == 400


def test_channel_upload_slots_drive_scheduling(client, db_session):
    client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={"upload_slots": ["07:15", "19:45"], "upload_timezone": "UTC"},
    )

    slot = AutoStageService.next_publish_slot(
        db_session, now=datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    )
    assert slot == datetime(2026, 1, 1, 7, 15, tzinfo=UTC)


def test_brand_defaults_apply_to_staged_metadata(client, db_session):
    client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={
            "channel_name": "NightOwl",
            "title_template": "{title} | {channel}",
            "pinned_hashtags": ["Shorts", "NightOwl"],
            "default_privacy": "unlisted",
        },
    )

    video = Video(
        id="brand_video",
        title="Ranked Marvel Rivals VOD",
        duration=120,
        duration_formatted="2:00",
        channel_name="NightOwl",
        webpage_url="https://www.youtube.com/watch?v=brand_video",
        is_downloaded=True,
        download_status="completed",
    )
    job = RenderJob(
        id="brand_job",
        clip_id="brand_clip",
        video_id=video.id,
        status="completed",
        start_seconds=10,
        duration_seconds=15,
        crop_preset="third_person",
        modes="third_person",
        quality_preset="high",
    )
    db_session.add_all([video, job])
    db_session.commit()

    res = client.post(
        f"{settings.API_PREFIX}/renders/brand_clip/upload-selection",
        json={"is_selected": True, "preferred_format": "third_person"},
    )
    assert res.status_code == 200
    selection = res.json()["response"]["upload_selection"]

    assert selection["title"].endswith("| NightOwl")
    assert selection["tags"][:2] == ["Shorts", "NightOwl"]
    assert selection["privacy"] == "unlisted"
    assert "#NightOwl" in selection["description"]
