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


def test_branding_round_trips_through_the_profile(client, db_session):
    """Bookends are stored on the channel profile and feed the render config."""
    from app.rendering.config import BrandingConfig
    from app.services.channel_profile import ChannelProfileService

    initial = client.get(f"{settings.API_PREFIX}/channel/profile").json()["response"]
    assert initial["branding_enabled"] is False
    assert initial["branding_intro"] is True
    assert initial["branding_outro_title"] == "SUBSCRIBE"

    updated = client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={
            "channel_name": "@NightOwl",
            "branding_enabled": True,
            "branding_intro": False,
            "branding_outro_seconds": 2.5,
            "branding_outro_title": "SUBSCRIBE & TAP THE BELL",
            "branding_outro_subtitle": "Daily clips",
            "branding_accent_color": "#22D3EE",
        },
    )
    assert updated.status_code == 200
    body = updated.json()["response"]
    assert body["branding_enabled"] is True
    assert body["branding_intro"] is False
    assert body["branding_outro"] is True
    assert body["branding_outro_seconds"] == 2.5
    assert body["branding_outro_title"] == "SUBSCRIBE & TAP THE BELL"
    assert body["branding_background_color"] == "#0B0D13"

    resolved: BrandingConfig = ChannelProfileService.branding_config(db_session)
    assert resolved.enabled is True
    assert resolved.has_intro is False
    assert resolved.has_outro is True
    assert resolved.outro_seconds == 2.5
    assert resolved.accent_color == "#22D3EE"
    assert resolved.channel_name == "@NightOwl"
    assert resolved.resolved_outro_subtitle() == "Daily clips"

    # Clearing a text field falls back to the configured default.
    cleared = client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={"branding_outro_title": ""},
    )
    assert cleared.json()["response"]["branding_outro_title"] == "SUBSCRIBE"


def test_branding_falls_back_to_env_defaults_for_unset_columns(
    client, db_session, monkeypatch
):
    """Rows created before branding columns existed must keep rendering."""
    from app.models.channel_profile import ChannelProfile
    from app.services.channel_profile import ChannelProfileService

    monkeypatch.setattr(settings, "BRANDING_ENABLED", True)
    monkeypatch.setattr(settings, "BRANDING_OUTRO_SECONDS", 3.0)
    monkeypatch.setattr(settings, "BRANDING_CHANNEL_NAME", "@EnvChannel")

    # Simulate a legacy row: every branding column is NULL and no channel name.
    profile = ChannelProfileService.get_or_create(db_session)
    for column in ChannelProfile.__table__.columns:
        if column.name.startswith("branding_") or column.name == "channel_name":
            setattr(profile, column.name, None)
    db_session.commit()

    resolved = ChannelProfileService.branding_config(db_session)
    assert resolved.enabled is True
    assert resolved.outro_seconds == 3.0
    assert resolved.channel_name == "@EnvChannel"

    body = client.get(f"{settings.API_PREFIX}/channel/profile").json()["response"]
    assert body["branding_enabled"] is True
    assert body["branding_outro_seconds"] == 3.0


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


def test_duration_budget_resolves_from_profile(client, db_session, monkeypatch):
    """Clip ceiling lives on the profile and subtracts branded bookends."""
    from app.rendering.config import DurationBudget
    from app.services.channel_profile import ChannelProfileService

    # Branding off by default -> no bookends, default ceiling.
    budget = ChannelProfileService.duration_budget(db_session)
    assert budget == DurationBudget(max_seconds=90.0, bookend_seconds=0.0)
    assert budget.clip_budget == 90.0

    # Turn bookends on: the ceiling is shared by intro + outro.
    client.put(
        f"{settings.API_PREFIX}/channel/profile",
        json={
            "branding_enabled": True,
            "branding_intro_seconds": 1.2,
            "branding_outro_seconds": 2.0,
            "max_clip_seconds": 90.0,
        },
    )
    budget = ChannelProfileService.duration_budget(db_session)
    assert budget.bookend_seconds == pytest.approx(3.2)
    assert budget.clip_budget == pytest.approx(86.8)
    assert budget.is_uploadable(86.8) is True
    assert budget.is_uploadable(86.9) is False

    # A creator can raise the ceiling for longer-form uploads.
    client.put(
        f"{settings.API_PREFIX}/channel/profile", json={"max_clip_seconds": 120.0}
    )
    budget = ChannelProfileService.duration_budget(db_session)
    assert budget.max_seconds == 120.0
    assert budget.clip_budget == pytest.approx(116.8)

    # Legacy rows fall back to the env settings instead of 0/None.
    monkeypatch.setattr(settings, "MAX_CLIP_SECONDS", 75.0)
    monkeypatch.setattr(settings, "BRANDING_ENABLED", True)
    monkeypatch.setattr(settings, "BRANDING_INTRO_SECONDS", 1.0)
    monkeypatch.setattr(settings, "BRANDING_OUTRO_SECONDS", 1.0)
    from app.models.channel_profile import ChannelProfile

    profile = ChannelProfileService.get_or_create(db_session)
    for column in ChannelProfile.__table__.columns:
        if column.name.startswith("branding_") or column.name == "max_clip_seconds":
            setattr(profile, column.name, None)
    profile.channel_name = None
    db_session.commit()
    budget = ChannelProfileService.duration_budget(db_session)
    assert budget.max_seconds == 75.0
    assert budget.bookend_seconds == pytest.approx(2.0)
    assert budget.clip_budget == pytest.approx(73.0)
