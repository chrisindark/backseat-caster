"""Automated tests for Highlight Candidate Clustering, Padding & Scoring Engine."""

import json
import subprocess
from pathlib import Path

import pytest

from app.services.highlight.audio_scanner import AudioCandidateWindow
from app.services.highlight.cluster_engine import (
    ClusterConfig,
    ClusterEngine,
    HighlightCandidate,
    cluster_highlight_candidates,
    generate_suggested_tags,
    generate_suggested_title,
)
from app.services.highlight.visual_matcher import VisualDetectionEvent


@pytest.fixture(scope="session")
def cluster_test_video(tmp_path_factory) -> Path:
    """Generate a 60-second synthetic test video for clustering & thumbnail tests."""
    temp_dir = tmp_path_factory.mktemp("cluster_engine_assets")
    video_path = temp_dir / "test_vod_60s.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=60:size=1280x720:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    return video_path


def test_suggested_title_and_tags_generation():
    """Verify title generation and tag assignment across event types."""
    # Team wipe in overtime
    t1 = generate_suggested_title("team_wipe", kill_count=6, game_phase="overtime")
    assert "Team Wipe" in t1
    assert "Overtime" in t1
    assert "💥" in t1

    # Triple KO regular
    t2 = generate_suggested_title("triple_ko", kill_count=3, game_phase="regular")
    assert "Triple KO" in t2
    assert "🔥" in t2

    # Shutdown
    t3 = generate_suggested_title("shutdown", kill_count=1)
    assert "Shutdown" in t3

    # Streak milestone titles (tier-aware)
    t4 = generate_suggested_title("kill_streak", streak_count=5)
    assert "5-Player KO Streak" in t4
    assert "🔥" in t4

    t5 = generate_suggested_title("kill_streak", streak_count=4)
    assert "4-Player KO Streak" in t5

    t6 = generate_suggested_title("double_ko", kill_count=2)
    assert "Double KO" in t6

    # Tags
    tags_ot = generate_suggested_tags("triple_ko", game_phase="overtime")
    assert "MarvelRivals" in tags_ot
    assert "TripleKO" in tags_ot
    assert "Overtime" in tags_ot


def test_cluster_events_chaining():
    """Test merging chained eliminations within 5s into a single highlight clip."""
    # 3 eliminations in close succession: 20s, 23s, 26s
    events = [
        VisualDetectionEvent(
            timestamp=20.0,
            roi_name="center_ko",
            event_type="single_ko",
            label="ELIMINATED",
            confidence=0.90,
            kill_count=1,
            score_weight=0.50,
        ),
        VisualDetectionEvent(
            timestamp=23.0,
            roi_name="center_ko",
            event_type="double_ko",
            label="DOUBLE KO",
            confidence=0.92,
            kill_count=2,
            score_weight=0.70,
        ),
        VisualDetectionEvent(
            timestamp=26.0,
            roi_name="center_ko",
            event_type="triple_ko",
            label="TRIPLE KO",
            confidence=0.95,
            kill_count=3,
            score_weight=0.80,
        ),
    ]

    engine = ClusterEngine(
        config=ClusterConfig(
            event_merge_gap_seconds=5.0,
            pre_roll_seconds=7.0,
            post_roll_seconds=4.0,
            min_clip_duration=18.0,
            max_clip_duration=45.0,
            generate_thumbnails=False,
        )
    )

    candidates = engine.cluster_events(
        events=events,
        total_duration=100.0,
        video_id="vod_test_123",
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.video_id == "vod_test_123"
    assert cand.event_type == "triple_ko"
    assert cand.details.kill_count == 3
    assert cand.details.climax_start_seconds == 20.0
    assert cand.details.climax_end_seconds == 26.0
    assert len(cand.details.trigger_events) == 3
    # Duration clamped to min 18.0s
    assert cand.duration_seconds >= 18.0
    # Climax was at 26s
    assert cand.peak_timestamp == 26.0
    # Chained eliminations receive a bonus above base 0.80
    assert cand.score >= 0.80


def test_cluster_events_separated():
    """Test that eliminations occurring far apart generate separate highlight candidates."""
    events = [
        VisualDetectionEvent(
            timestamp=15.0,
            roi_name="center_ko",
            event_type="double_ko",
            label="DOUBLE KO",
            confidence=0.90,
            kill_count=2,
            score_weight=0.70,
        ),
        VisualDetectionEvent(
            timestamp=55.0,
            roi_name="center_ko",
            event_type="team_wipe",
            label="TEAM WIPE",
            confidence=0.98,
            kill_count=6,
            score_weight=1.00,
        ),
    ]

    engine = ClusterEngine(
        config=ClusterConfig(
            event_merge_gap_seconds=5.0,
            generate_thumbnails=False,
        )
    )
    candidates = engine.cluster_events(
        events=events,
        total_duration=120.0,
        video_id="vod_test",
    )

    assert len(candidates) == 2
    # Candidates are sorted by score descending: team_wipe first
    assert candidates[0].event_type == "team_wipe"
    assert candidates[0].score >= 0.80
    assert candidates[0].score > candidates[1].score
    assert candidates[1].event_type == "double_ko"


def test_duration_constraints():
    """Test min_clip_duration floor and max_clip_duration ceiling constraints."""
    config = ClusterConfig(
        min_clip_duration=18.0,
        max_clip_duration=45.0,
        generate_thumbnails=False,
    )
    engine = ClusterEngine(config=config)

    # 1. Single instantaneous event at 20s
    single_event = [
        VisualDetectionEvent(
            timestamp=20.0,
            roi_name="center_ko",
            event_type="single_ko",
            label="ELIMINATED",
            confidence=0.90,
            kill_count=1,
            score_weight=0.50,
        )
    ]
    cand_short = engine.cluster_events(single_event, total_duration=100.0)[0]
    assert cand_short.duration_seconds == 18.0
    assert cand_short.start_seconds <= 20.0 <= cand_short.end_seconds

    # 2. Extended chain of events spanning 50 seconds
    long_events = [
        VisualDetectionEvent(
            timestamp=float(t),
            roi_name="center_ko",
            event_type="single_ko",
            label="ELIMINATED",
            confidence=0.85,
            kill_count=1,
            score_weight=0.50,
        )
        for t in range(10, 65, 4)
    ]
    cand_long = engine.cluster_events(long_events, total_duration=200.0)[0]
    assert cand_long.duration_seconds <= 45.0


def test_thumbnail_extraction_and_candidate_assembly(cluster_test_video, tmp_path):
    """Test thumbnail frame extraction and end-to-end candidate assembly."""
    events = [
        VisualDetectionEvent(
            timestamp=12.0,
            roi_name="center_ko",
            event_type="triple_ko",
            label="TRIPLE KO",
            confidence=0.95,
            kill_count=3,
            score_weight=0.80,
        )
    ]

    config = ClusterConfig(
        thumbnails_dir=str(tmp_path / "thumbs"),
        generate_thumbnails=True,
    )
    engine = ClusterEngine(config=config)

    candidates = engine.cluster_events(
        events=events,
        total_duration=60.0,
        video_id="video_obs_01",
        media_path=cluster_test_video,
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.thumbnail_path is not None
    assert Path(cand.thumbnail_path).exists()
    assert Path(cand.thumbnail_path).stat().st_size > 0
    assert (
        cand.thumbnail_url
        == f"/api/v1/videos/video_obs_01/highlights/{cand.candidate_id}/thumb.jpg"
    )


def test_audio_energy_fallback_candidates(cluster_test_video):
    """Test that high-energy audio action windows synthesize candidates when no visual events exist."""
    audio_win = AudioCandidateWindow(
        start_seconds=30.0,
        end_seconds=36.0,
        duration_seconds=6.0,
        mean_lufs=-12.0,
        peak_lufs=-8.0,
        peak_true_peak_db=-1.5,
        score=0.88,
        bucket_count=12,
    )

    candidates = cluster_highlight_candidates(
        video_id="audio_vod",
        media_path=cluster_test_video,
        visual_matches=None,
        audio_windows=[audio_win],
        total_duration=60.0,
        config=ClusterConfig(generate_thumbnails=False),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.event_type == "high_energy_action"
    assert cand.score >= 0.60
    assert cand.start_seconds <= 30.0
    assert cand.end_seconds >= 36.0


def test_candidate_schema_contract_json():
    """Verify HighlightCandidate serializes cleanly according to plans.md Section 5."""
    cand = HighlightCandidate(
        candidate_id="cand_mvr_91a2b",
        video_id="obs_67a12b89",
        start_seconds=118.0,
        end_seconds=146.0,
        duration_seconds=28.0,
        score=0.94,
        event_type="triple_ko",
        game="Marvel Rivals",
        thumbnail_url="/api/v1/videos/obs_67a12b89/highlights/cand_mvr_91a2b/thumb.jpg",
        suggested_title="Clean Triple KO in Overtime! 🔥 #MarvelRivals",
        suggested_tags=["MarvelRivals", "Gaming", "Shorts", "TripleKO", "Gameplay"],
    )

    data = cand.model_dump()
    assert data["candidate_id"] == "cand_mvr_91a2b"
    assert data["score"] == 0.94
    assert data["game"] == "Marvel Rivals"
    assert "details" in data

    json_str = cand.model_dump_json()
    loaded = json.loads(json_str)
    assert loaded["event_type"] == "triple_ko"
