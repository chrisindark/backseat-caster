"""Tests for Marvel Rivals Highlight Mining API endpoints, DB models, and worker pipeline."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.highlight_candidate import HighlightCandidate
from app.models.highlight_run import HighlightRun
from app.models.video import Video
from app.schemas.highlight import DetectHighlightsRequest
from app.services.highlight.audio_scanner import AudioCandidateWindow, AudioScanResult
from app.services.highlight.cluster_engine import (
    ClusterEngine,
    HighlightDetails,
    TriggerEvent,
)
from app.services.highlight.cluster_engine import HighlightCandidate as ClusterCandidate
from app.services.highlight.roi_extractor import BatchROIExtractionResult
from app.services.highlight.service import (
    HighlightService,
    execute_highlight_detection_job,
)
from app.services.highlight.visual_matcher import (
    BatchVisualMatchResult,
    VisualDetectionEvent,
    WindowVisualMatchResult,
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
def dummy_video(db_session, tmp_path):
    """Create a dummy downloaded video in DB and on disk."""
    fake_video_file = tmp_path / "obs_test123.mp4"
    fake_video_file.write_bytes(b"dummy video data")

    video = Video(
        id="obs_test123",
        title="Marvel Rivals Grandmaster Match",
        description="Competitive match recording",
        webpage_url="https://youtube.com/watch?v=obs_test123",
        is_downloaded=True,
        local_file_path=str(fake_video_file),
        file_size_bytes=1024,
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


def test_highlight_model_and_serialization(db_session, dummy_video):
    """Verify HighlightCandidate model creation, relationship, and JSON serialization."""
    candidate = HighlightCandidate(
        id="cand_mvr_test1",
        video_id=dummy_video.id,
        start_seconds=120.0,
        end_seconds=152.0,
        duration_seconds=32.0,
        score=0.92,
        event_type="triple_ko",
        game="Marvel Rivals",
        details_json=json.dumps(
            {
                "kill_count": 3,
                "has_ultimate": True,
                "is_team_wipe": False,
                "game_phase": "overtime",
                "trigger_events": [
                    {"time": 125.0, "label": "Elimination", "roi_name": "center_ko"},
                    {"time": 129.0, "label": "DOUBLE KO", "roi_name": "center_ko"},
                    {"time": 133.0, "label": "TRIPLE KO", "roi_name": "center_ko"},
                ],
            }
        ),
        thumbnail_url=f"/api/v1/videos/{dummy_video.id}/highlights/cand_mvr_test1/thumb.jpg",
        thumbnail_path="/tmp/thumb.jpg",
        peak_timestamp=133.0,
        suggested_title="Insane Triple KO in Overtime! 🔥 #MarvelRivals",
        suggested_tags_json=json.dumps(["MarvelRivals", "Gaming", "Shorts"]),
    )
    db_session.add(candidate)
    db_session.commit()

    # Query back
    fetched = (
        db_session.query(HighlightCandidate)
        .filter(HighlightCandidate.id == "cand_mvr_test1")
        .first()
    )
    assert fetched is not None
    assert fetched.score == 0.92
    assert fetched.video.id == dummy_video.id

    c_dict = fetched.to_dict()
    assert c_dict["candidate_id"] == "cand_mvr_test1"
    assert c_dict["video_id"] == dummy_video.id
    assert c_dict["event_type"] == "triple_ko"
    assert c_dict["details"]["kill_count"] == 3
    assert len(c_dict["details"]["trigger_events"]) == 3
    assert c_dict["suggested_tags"] == ["MarvelRivals", "Gaming", "Shorts"]


def test_detect_highlights_404_not_found(client):
    """Verify 404 error when triggering detection on non-existent video."""
    response = client.post(
        f"{settings.API_PREFIX}/videos/nonexistent_vid/highlights/detect"
    )
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error_message"].lower()


def test_detect_highlights_400_missing_file(client, db_session):
    """Verify 400 error when video exists in DB but media file is missing on disk."""
    video = Video(
        id="obs_missing",
        title="Missing File Video",
        webpage_url="https://youtube.com/watch?v=obs_missing",
        is_downloaded=True,
        local_file_path="/invalid/nonexistent/path.mp4",
        download_status="completed",
    )
    db_session.add(video)
    db_session.commit()

    response = client.post(f"{settings.API_PREFIX}/videos/{video.id}/highlights/detect")
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error_message"].lower()


def test_detect_highlights_dispatch_async(client, dummy_video):
    """Verify triggering highlight detection returns queued response."""
    with patch(
        "app.services.highlight.service.is_celery_broker_online", return_value=False
    ):
        response = client.post(
            f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/detect",
            json={"force_rescan": True, "min_score": 0.6},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["response"]["video_id"] == dummy_video.id
        assert data["response"]["status"] in ("pending", "scanning")
        assert "queued successfully" in data["response"]["message"].lower()


def test_detect_highlights_already_scanning(client, dummy_video, db_session):
    """Verify triggering detection while already scanning returns notice without re-queueing."""
    dummy_video.highlight_status = "scanning"
    dummy_video.highlight_stage = "Scanning audio..."
    dummy_video.highlight_task_id = "task_abc_123"
    db_session.commit()

    response = client.post(
        f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/detect",
        json={"force_rescan": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["response"]["status"] == "scanning"
    assert "already in progress" in data["response"]["message"].lower()


def test_get_highlight_status(client, dummy_video, db_session):
    """Verify polling highlight status endpoint returns current progress and stages."""
    dummy_video.highlight_status = "scanning"
    dummy_video.highlight_progress = 45.0
    dummy_video.highlight_stage = "Extracting HUD regions..."
    db_session.commit()

    response = client.get(
        f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/status"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["response"]["video_id"] == dummy_video.id
    assert data["response"]["status"] == "scanning"
    assert data["response"]["progress"] == 45.0
    assert data["response"]["stage"] == "Extracting HUD regions..."
    assert data["response"]["candidate_count"] == 0


def test_list_and_delete_highlight_candidates(
    client, dummy_video, db_session, tmp_path
):
    """Verify listing ranked candidates and deleting them."""
    # Create a dummy thumbnail file
    thumb_dir = tmp_path / "cand_mvr_001"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_file = thumb_dir / "thumb.jpg"
    thumb_file.write_bytes(b"jpeg bytes")

    cand1 = HighlightCandidate(
        id="cand_mvr_001",
        video_id=dummy_video.id,
        start_seconds=40.0,
        end_seconds=75.0,
        duration_seconds=35.0,
        score=0.95,
        event_type="team_wipe",
        game="Marvel Rivals",
        details_json=json.dumps(
            {
                "kill_count": 5,
                "has_ultimate": True,
                "is_team_wipe": True,
                "game_phase": "clutch",
                "trigger_events": [
                    {"time": 48.0, "label": "TEAM WIPE", "roi_name": "center_ko"}
                ],
            }
        ),
        thumbnail_url=f"/api/v1/videos/{dummy_video.id}/highlights/cand_mvr_001/thumb.jpg",
        thumbnail_path=str(thumb_file),
        peak_timestamp=48.0,
        suggested_title="Clean Team Wipe! ⚡ #MarvelRivals",
        suggested_tags_json=json.dumps(["TeamWipe", "Shorts"]),
    )
    cand2 = HighlightCandidate(
        id="cand_mvr_002",
        video_id=dummy_video.id,
        start_seconds=110.0,
        end_seconds=142.0,
        duration_seconds=32.0,
        score=0.75,
        event_type="double_ko",
        game="Marvel Rivals",
        details_json=json.dumps(
            {
                "kill_count": 2,
                "has_ultimate": False,
                "is_team_wipe": False,
                "game_phase": "regular",
                "trigger_events": [],
            }
        ),
        thumbnail_url=None,
        thumbnail_path=None,
        peak_timestamp=120.0,
        suggested_title="Double KO #MarvelRivals",
        suggested_tags_json=json.dumps([]),
    )
    db_session.add_all([cand1, cand2])
    dummy_video.highlight_status = "completed"
    dummy_video.highlight_progress = 100.0
    db_session.commit()

    # 1. Test GET /highlights
    get_res = client.get(f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["success"] is True
    assert get_data["response"]["count"] == 2
    candidates = get_data["response"]["candidates"]
    assert candidates[0]["candidate_id"] == "cand_mvr_001"  # Higher score first
    assert candidates[0]["score"] == 0.95
    assert candidates[0]["event_type"] == "team_wipe"
    assert candidates[0]["details"]["kill_count"] == 5
    assert candidates[1]["candidate_id"] == "cand_mvr_002"

    # 2. Test GET thumbnail
    thumb_res = client.get(
        f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/cand_mvr_001/thumb.jpg"
    )
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"] == "image/jpeg"
    assert thumb_res.content == b"jpeg bytes"

    # 3. Test DELETE /highlights
    del_res = client.delete(f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["success"] is True
    assert del_data["response"]["deleted_count"] == 2

    # Verify candidates removed and video status reset
    db_session.refresh(dummy_video)
    assert dummy_video.highlight_status == "idle"
    assert (
        db_session.query(HighlightCandidate)
        .filter(HighlightCandidate.video_id == dummy_video.id)
        .count()
        == 0
    )


def test_get_thumbnail_not_found(client, dummy_video):
    """Verify 404 when requesting thumbnail for non-existent candidate or missing file."""
    res = client.get(
        f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/nonexistent_cand/thumb.jpg"
    )
    assert res.status_code == 404


def test_execute_highlight_detection_pipeline_end_to_end(
    dummy_video, db_session, tmp_path
):
    """
    Test end-to-end execution of execute_highlight_detection_job mocking subcomponents
    and asserting stages, status transitions, and candidate persistence.
    """
    fake_thumb = tmp_path / "thumb_test.jpg"
    fake_thumb.write_bytes(b"jpeg")

    # Synthetic return values for submodules
    mock_audio = AudioScanResult(
        file_path=str(dummy_video.local_file_path),
        duration_seconds=180.0,
        has_audio=True,
        silence_threshold_lufs=-30.0,
        excitement_threshold_lufs=-18.0,
        total_buckets=100,
        candidate_windows=[
            AudioCandidateWindow(
                start_seconds=60.0,
                end_seconds=85.0,
                duration_seconds=25.0,
                peak_lufs=-12.0,
                mean_lufs=-15.0,
                peak_true_peak_db=-1.0,
                score=0.85,
                bucket_count=50,
            )
        ],
    )

    mock_roi = BatchROIExtractionResult(
        file_path=str(dummy_video.local_file_path),
        source_width=1920,
        source_height=1080,
        fps=1.5,
        windows_extracted=[],
        total_frames=30,
    )

    mock_visual = BatchVisualMatchResult(
        file_path=str(dummy_video.local_file_path),
        windows_matched=[
            WindowVisualMatchResult(
                window_start=60.0,
                window_end=85.0,
                window_duration=25.0,
                events=[
                    VisualDetectionEvent(
                        timestamp=72.0,
                        roi_name="center_ko",
                        event_type="triple_ko",
                        label="TRIPLE KO",
                        confidence=0.95,
                    )
                ],
                peak_event_type="triple_ko",
                total_kills=3,
            )
        ],
        total_events_detected=1,
    )

    mock_candidate = ClusterCandidate(
        candidate_id="cand_mvr_simulated1",
        video_id=dummy_video.id,
        start_seconds=55.0,
        end_seconds=89.0,
        duration_seconds=34.0,
        score=0.89,
        event_type="triple_ko",
        game="Marvel Rivals",
        details=HighlightDetails(
            kill_count=3,
            has_ultimate=True,
            is_team_wipe=False,
            game_phase="regular",
            trigger_events=[
                TriggerEvent(time=72.0, label="TRIPLE KO", roi_name="center_ko")
            ],
        ),
        thumbnail_url=f"/api/v1/videos/{dummy_video.id}/highlights/cand_mvr_simulated1/thumb.jpg",
        thumbnail_path=str(fake_thumb),
        peak_timestamp=72.0,
        suggested_title="Triple KO Play! 🔥 #MarvelRivals",
        suggested_tags=["MarvelRivals", "TripleKO"],
    )

    with (
        patch(
            "app.services.highlight.service.scan_audio_energy",
            return_value=mock_audio,
        ),
        patch(
            "app.services.highlight.service.extract_candidate_windows_rois",
            return_value=mock_roi,
        ),
        patch(
            "app.services.highlight.service.evaluate_batch_visuals",
            return_value=mock_visual,
        ),
        patch.object(
            ClusterEngine, "assemble_candidates", return_value=[mock_candidate]
        ),
    ):
        result = execute_highlight_detection_job(
            video_id=dummy_video.id,
            min_score=0.5,
            db_session=db_session,
        )

        assert result["status"] == "completed"
        assert result["count"] == 1

        db_session.refresh(dummy_video)
        assert dummy_video.highlight_status == "completed"
        assert dummy_video.highlight_progress == 100.0
        assert "complete" in dummy_video.highlight_stage.lower()

        # Check persisted HighlightCandidate
        saved_cands = (
            db_session.query(HighlightCandidate)
            .filter(HighlightCandidate.video_id == dummy_video.id)
            .all()
        )
        assert len(saved_cands) == 1
        assert saved_cands[0].id == "cand_mvr_simulated1"
        assert saved_cands[0].score == 0.89
        assert saved_cands[0].event_type == "triple_ko"


def test_detect_highlights_sync(client, dummy_video):
    """Verify synchronous highlight detection triggers execute_highlight_detection_job inline."""
    with patch(
        "app.services.highlight.service.execute_highlight_detection_job",
        return_value={"status": "completed", "count": 2},
    ) as mock_exec:
        response = client.post(
            f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/detect",
            json={"sync": True, "force_rescan": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "synchronously" in data["response"]["message"].lower()
        mock_exec.assert_called_once()


def test_detect_highlights_celery_dispatch(client, dummy_video):
    """Verify Celery task queueing when broker is online."""
    mock_async_res = MagicMock(id="celery_task_xyz_999")
    with (
        patch(
            "app.services.highlight.service.is_celery_broker_online",
            return_value=True,
        ),
        patch(
            "app.services.highlight.service.detect_highlights_celery_task.delay",
            return_value=mock_async_res,
        ),
    ):
        response = client.post(
            f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/detect",
            json={"force_rescan": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["response"]["status"] == "scanning"
        assert data["response"]["task_id"] == "celery_task_xyz_999"
        assert "via celery" in data["response"]["message"].lower()


def test_execute_highlight_detection_failure_handling(dummy_video, db_session):
    """Verify pipeline exception marks Video highlight_status as 'failed' with error recorded."""
    with patch(
        "app.services.highlight.service.scan_audio_energy",
        side_effect=RuntimeError("FFmpeg audio decode error"),
    ):
        result = execute_highlight_detection_job(
            video_id=dummy_video.id,
            db_session=db_session,
        )
        assert result["status"] == "failed"
        assert "FFmpeg audio decode error" in result["error"]

        db_session.refresh(dummy_video)
        assert dummy_video.highlight_status == "failed"
        assert dummy_video.highlight_error == "FFmpeg audio decode error"


def test_sync_celery_task_state(dummy_video, db_session):
    """Verify sync_celery_task_state updates progress and completion from Celery AsyncResult."""
    dummy_video.highlight_status = "scanning"
    dummy_video.highlight_task_id = "celery_task_active"
    db_session.commit()

    # 1. State PROGRESS
    mock_progress_res = MagicMock()
    mock_progress_res.state = "PROGRESS"
    mock_progress_res.info = {"progress": 60.0, "stage": "Color matching"}

    with patch(
        "app.services.highlight.service.celery_app.AsyncResult",
        return_value=mock_progress_res,
    ):
        HighlightService.sync_celery_task_state(db=db_session, video=dummy_video)
        assert dummy_video.highlight_progress == 60.0
        assert dummy_video.highlight_stage == "Color matching"

    # 2. State SUCCESS
    mock_success_res = MagicMock()
    mock_success_res.state = "SUCCESS"

    with patch(
        "app.services.highlight.service.celery_app.AsyncResult",
        return_value=mock_success_res,
    ):
        HighlightService.sync_celery_task_state(db=db_session, video=dummy_video)
        assert dummy_video.highlight_status == "completed"
        assert dummy_video.highlight_progress == 100.0


def test_highlight_run_model_and_serialization(db_session, dummy_video):
    """Verify HighlightRun model attributes, relationships, and dictionary serialization."""
    from datetime import UTC, datetime

    run = HighlightRun(
        id="hrun_test_001",
        video_id=dummy_video.id,
        celery_task_id="task_celery_123",
        status="completed",
        detector_used="marvel_rivals",
        game="marvel_rivals",
        parameters_json=json.dumps({"min_score": 0.5}),
        total_duration_seconds=12.45,
        video_duration_seconds=300.0,
        audio_scan_duration_seconds=3.21,
        roi_extract_duration_seconds=4.50,
        visual_match_duration_seconds=3.10,
        cluster_duration_seconds=0.85,
        audio_windows_count=15,
        frames_analyzed_count=48,
        visual_events_count=4,
        candidates_produced_count=3,
        speedup_factor=24.1,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    db_session.refresh(dummy_video)
    assert len(dummy_video.highlight_runs) == 1
    assert dummy_video.highlight_runs[0].id == "hrun_test_001"

    data = run.to_dict()
    assert data["id"] == "hrun_test_001"
    assert data["video_id"] == dummy_video.id
    assert data["detector_used"] == "marvel_rivals"
    assert data["speedup_factor"] == 24.1
    assert data["audio_windows_count"] == 15
    assert data["parameters"]["min_score"] == 0.5


def test_execute_highlight_detection_records_run_metrics(dummy_video, db_session):
    """Verify execute_highlight_detection_job tracks latency metrics into HighlightRun."""
    mock_audio_res = AudioScanResult(
        file_path="/path/test.mp4",
        duration_seconds=300.0,
        has_audio=True,
        silence_threshold_lufs=-30.0,
        excitement_threshold_lufs=-18.0,
        total_buckets=100,
        candidate_windows=[
            AudioCandidateWindow(
                start_seconds=10.0,
                end_seconds=25.0,
                duration_seconds=15.0,
                peak_lufs=-12.0,
                mean_lufs=-15.0,
                peak_true_peak_db=-1.0,
                score=0.85,
                bucket_count=15,
            )
        ],
    )

    mock_roi_res = BatchROIExtractionResult(
        file_path=str(dummy_video.local_file_path),
        source_width=1920,
        source_height=1080,
        fps=1.5,
        windows_extracted=[],
        total_frames=15,
        duration_seconds=1.2,
    )

    mock_vis_res = BatchVisualMatchResult(
        file_path=str(dummy_video.local_file_path),
        windows_matched=[],
        kill_count=1,
    )

    mock_cluster_res = [
        ClusterCandidate(
            candidate_id="cand_mvr_runtest1",
            video_id=dummy_video.id,
            start_seconds=10.0,
            end_seconds=25.0,
            duration_seconds=15.0,
            score=0.91,
            event_type="solo_kill",
            game="marvel_rivals",
            details=HighlightDetails(
                kill_count=1,
                has_ultimate=False,
                peak_audio_lufs=-12.0,
                trigger_events=[
                    TriggerEvent(
                        time=15.0,
                        label="Elimination",
                        roi_name="kill_feed",
                        confidence=0.9,
                    )
                ],
            ),
            suggested_title="Marvel Rivals Solo Kill",
            suggested_tags=["MarvelRivals", "Gaming"],
        )
    ]

    with (
        patch(
            "app.services.highlight.service.scan_audio_energy",
            return_value=mock_audio_res,
        ),
        patch(
            "app.services.highlight.service.extract_candidate_windows_rois",
            return_value=mock_roi_res,
        ),
        patch(
            "app.services.highlight.service.evaluate_batch_visuals",
            return_value=mock_vis_res,
        ),
        patch.object(
            ClusterEngine,
            "assemble_candidates",
            return_value=mock_cluster_res,
        ),
    ):
        resp = HighlightService.detect_highlights(
            db=db_session,
            video_id=dummy_video.id,
            request=DetectHighlightsRequest(
                sync=True,
                game="marvel_rivals",
                min_score=0.5,
                force_rescan=True,
            ),
        )

        assert resp.status == "completed"
        assert resp.run_id is not None

        run = (
            db_session.query(HighlightRun)
            .filter(HighlightRun.id == resp.run_id)
            .first()
        )
        assert run is not None
        assert run.status == "completed"
        assert run.detector_used == "marvel_rivals"
        assert (
            run.total_duration_seconds is not None and run.total_duration_seconds >= 0
        )
        assert run.video_duration_seconds == 300.0
        assert run.audio_scan_duration_seconds is not None
        assert run.roi_extract_duration_seconds is not None
        assert run.visual_match_duration_seconds is not None
        assert run.cluster_duration_seconds is not None
        assert run.audio_windows_count == 1
        assert run.candidates_produced_count == 1
        assert run.speedup_factor is not None and run.speedup_factor > 0


def test_execute_highlight_detection_run_records_failure(dummy_video, db_session):
    """Verify run status and error message are persisted on pipeline failure."""
    from datetime import UTC, datetime

    run = HighlightRun(
        id="hrun_fail_test",
        video_id=dummy_video.id,
        status="pending",
        detector_used="marvel_rivals",
        game="marvel_rivals",
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    with patch(
        "app.services.highlight.service.scan_audio_energy",
        side_effect=RuntimeError("Audio scanner catastrophic failure"),
    ):
        result = execute_highlight_detection_job(
            video_id=dummy_video.id,
            run_id=run.id,
            db_session=db_session,
        )

        assert result["status"] == "failed"
        assert result["run_id"] == "hrun_fail_test"

        db_session.refresh(run)
        assert run.status == "failed"
        assert "Audio scanner catastrophic failure" in (run.error_message or "")
        assert run.total_duration_seconds is not None
        assert run.completed_at is not None


def test_status_endpoint_returns_latest_run(client, dummy_video, db_session):
    """Verify GET /status includes the latest run's latency and detector details."""
    from datetime import UTC, datetime, timedelta

    run_old = HighlightRun(
        id="hrun_old",
        video_id=dummy_video.id,
        status="completed",
        detector_used="marvel_rivals",
        game="marvel_rivals",
        speedup_factor=10.0,
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    run_new = HighlightRun(
        id="hrun_new",
        video_id=dummy_video.id,
        status="completed",
        detector_used="marvel_rivals",
        game="marvel_rivals",
        speedup_factor=25.5,
        total_duration_seconds=5.2,
        created_at=datetime.now(UTC),
    )
    db_session.add(run_old)
    db_session.add(run_new)
    db_session.commit()

    res = client.get(f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/status")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["response"]["latest_run"] is not None
    assert data["response"]["latest_run"]["id"] == "hrun_new"
    assert data["response"]["latest_run"]["speedup_factor"] == 25.5
    assert data["response"]["latest_run"]["total_duration_seconds"] == 5.2


def test_list_highlight_runs_endpoint(client, dummy_video, db_session):
    """Verify GET /runs returns historical run records ordered descending."""
    from datetime import UTC, datetime, timedelta

    run1 = HighlightRun(
        id="hrun_batch_1",
        video_id=dummy_video.id,
        status="completed",
        detector_used="marvel_rivals",
        game="marvel_rivals",
        total_duration_seconds=10.0,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    run2 = HighlightRun(
        id="hrun_batch_2",
        video_id=dummy_video.id,
        status="completed",
        detector_used="generic",
        game="generic",
        total_duration_seconds=4.0,
        created_at=datetime.now(UTC),
    )
    db_session.add(run1)
    db_session.add(run2)
    db_session.commit()

    # Successful fetch
    res = client.get(f"{settings.API_PREFIX}/videos/{dummy_video.id}/highlights/runs")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["response"]["video_id"] == dummy_video.id
    assert data["response"]["count"] == 2
    runs = data["response"]["runs"]
    assert runs[0]["id"] == "hrun_batch_2"
    assert runs[1]["id"] == "hrun_batch_1"

    # Non-existent video returns 404
    res_404 = client.get(
        f"{settings.API_PREFIX}/videos/nonexistent_vid/highlights/runs"
    )
    assert res_404.status_code == 404
