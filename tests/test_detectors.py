"""Automated tests for Highlight Detector Strategy Pattern and Generic Single-Player Detector."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.video import Video
from app.schemas.highlight import HighlightCandidateResponse, HighlightDetailsSchema
from app.services.highlight.audio_scanner import AudioCandidateWindow, AudioScanResult
from app.services.highlight.detectors import (
    GenericHighlightDetector,
    MarvelRivalsDetector,
    get_detector,
    list_supported_detectors,
)

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


@pytest.fixture
def generic_video(db_session, tmp_path):
    fake_video = tmp_path / "elden_ring_vod.mp4"
    fake_video.write_bytes(b"dummy video data")

    video = Video(
        id="vod_elden_01",
        title="Elden Ring Malenia Boss Fight Solo",
        description="Epic no-hit gameplay run",
        webpage_url="https://youtube.com/watch?v=vod_elden_01",
        is_downloaded=True,
        local_file_path=str(fake_video),
        file_size_bytes=2048,
        download_status="completed",
        download_progress=100.0,
        highlight_status="idle",
        highlight_progress=0.0,
        highlight_stage="",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


def test_detector_registry_resolution():
    """Verify registry resolves appropriate detector strategy based on game name or video title."""
    # 1. Explicit aliases for Marvel Rivals
    for alias in ["marvel_rivals", "Marvel Rivals", "MVR", "marvelrivals"]:
        d = get_detector(alias)
        assert isinstance(d, MarvelRivalsDetector)
        assert d.game_id == "marvel_rivals"

    # 2. Explicit custom or generic game
    d_generic = get_detector("generic")
    assert isinstance(d_generic, GenericHighlightDetector)
    assert d_generic.game_display_name == "generic"

    d_elden = get_detector("Elden Ring")
    assert isinstance(d_elden, GenericHighlightDetector)
    assert d_elden.game_display_name == "Elden Ring"
    assert d_elden.game_id == "elden_ring"

    # 3. Auto-detection from video metadata
    d_auto_mvr = get_detector(video_title="Marvel Rivals Competitive Grandmaster Match")
    assert isinstance(d_auto_mvr, MarvelRivalsDetector)

    d_auto_sp = get_detector(video_title="God of War Ragnarok Full Playthrough")
    assert isinstance(d_auto_sp, GenericHighlightDetector)

    # 4. Catalog inspection
    catalog = list_supported_detectors()
    assert len(catalog) >= 2
    ids = [item["id"] for item in catalog]
    assert "generic" in ids
    assert "marvel_rivals" in ids


def test_generic_detector_pipeline(tmp_path):
    """Verify GenericHighlightDetector clusters audio action windows and generates single-player clips."""
    fake_vod = tmp_path / "single_player.mp4"
    fake_vod.write_bytes(b"content")

    # Mock audio scan with 2 nearby high-energy action windows (should be merged)
    mock_scan = AudioScanResult(
        file_path=str(fake_vod),
        duration_seconds=120.0,
        has_audio=True,
        silence_threshold_lufs=-30.0,
        excitement_threshold_lufs=-16.0,
        total_buckets=80,
        candidate_windows=[
            AudioCandidateWindow(
                start_seconds=20.0,
                end_seconds=25.0,
                duration_seconds=5.0,
                peak_lufs=-10.0,
                mean_lufs=-14.0,
                peak_true_peak_db=-0.8,
                score=0.88,
                bucket_count=10,
            ),
            AudioCandidateWindow(
                start_seconds=27.0,
                end_seconds=32.0,
                duration_seconds=5.0,
                peak_lufs=-8.5,
                mean_lufs=-12.0,
                peak_true_peak_db=-0.5,
                score=0.92,
                bucket_count=10,
            ),
        ],
    )

    detector = GenericHighlightDetector(game_name="Cyberpunk 2077")
    progress_records: list[tuple[float, str]] = []

    def mock_cb(p, s):
        progress_records.append((p, s))

    with (
        patch(
            "app.services.highlight.service.scan_audio_energy",
            return_value=mock_scan,
        ),
        patch(
            "app.services.highlight.detectors.generic.extract_thumbnail_frame"
        ) as mock_thumb,
    ):
        candidates = detector.detect(
            video_id="vod_cp77_01",
            media_path=fake_vod,
            min_score=0.5,
            progress_callback=mock_cb,
        )

        assert len(candidates) == 1
        cand = candidates[0]

        # Verify candidate ID and game assignment
        assert cand.candidate_id.startswith("cand_gen_")
        assert cand.game == "Cyberpunk 2077"
        assert cand.score >= 0.85
        assert cand.event_type == "epic_climax"

        # Verify duration clamped to YouTube Shorts window
        assert 18.0 <= cand.duration_seconds <= 45.0
        assert cand.start_seconds <= 20.0
        assert cand.end_seconds >= 32.0

        # Verify title and tags
        assert "Cyberpunk2077" in cand.suggested_title
        assert "Cyberpunk2077" in cand.suggested_tags
        assert "Shorts" in cand.suggested_tags

        # Verify trigger events and non-coupled details
        assert len(cand.details.trigger_events) == 1
        assert cand.details.kill_count is None
        assert cand.details.has_ultimate is None

        # Verify progress callbacks invoked
        assert len(progress_records) >= 3
        mock_thumb.assert_called_once()


def test_schema_flexibility_with_custom_attributes():
    """Verify HighlightDetailsSchema allows arbitrary extra keys without validation errors."""
    data = {
        "kill_count": None,
        "boss_name": "Malenia, Blade of Miquella",
        "attempt_number": 42,
        "weapon_used": "Rivers of Blood",
        "trigger_events": [
            {
                "time": 45.5,
                "label": "Phase 2 Transition",
                "roi_name": "boss_health_bar",
                "confidence": 0.98,
                "extra_metric": 100,
            }
        ],
    }

    schema = HighlightDetailsSchema(**data)
    dumped = schema.model_dump()
    assert dumped["boss_name"] == "Malenia, Blade of Miquella"
    assert dumped["attempt_number"] == 42
    assert dumped["weapon_used"] == "Rivers of Blood"
    assert dumped["trigger_events"][0]["extra_metric"] == 100

    resp = HighlightCandidateResponse(
        candidate_id="cand_gen_test1",
        video_id="video_custom_01",
        start_seconds=10.0,
        end_seconds=35.0,
        duration_seconds=25.0,
        score=0.90,
        event_type="epic_climax",
        game="Elden Ring",
        details=schema,
    )
    resp_dumped = resp.model_dump()
    assert resp_dumped["game"] == "Elden Ring"
    assert resp_dumped["details"]["boss_name"] == "Malenia, Blade of Miquella"


def test_detect_endpoint_with_game_parameter(client, generic_video):
    """Verify POST /detect accepts explicit game parameter and passes it to worker job."""
    with patch(
        "app.services.highlight.service.execute_highlight_detection_job",
        return_value={"status": "completed", "count": 3},
    ) as mock_exec:
        # Request with game='generic'
        res = client.post(
            f"{settings.API_PREFIX}/videos/{generic_video.id}/highlights/detect",
            json={
                "sync": True,
                "game": "generic",
                "min_score": 0.6,
                "force_rescan": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["response"]["run_id"] is not None
        mock_exec.assert_called_once_with(
            video_id=generic_video.id,
            min_score=0.6,
            game="generic",
            run_id=data["response"]["run_id"],
            db_session=pytest.approx(mock_exec.call_args.kwargs.get("db_session")),
        )
