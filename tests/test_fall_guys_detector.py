"""Unit and integration tests for Fall Guys highlight detector and speech mining."""

from unittest.mock import MagicMock, patch

from app.services.highlight.audio_scanner import AudioCandidateWindow, AudioScanResult
from app.services.highlight.detectors import (
    FallGuysDetector,
    GenericHighlightDetector,
    MarvelRivalsDetector,
    get_detector,
    list_supported_detectors,
)
from app.services.highlight.ocr import OCRToken
from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)
from app.services.highlight.speech_mining import snap_to_speech_boundaries
from app.services.upload_metadata import build_description, build_tags, build_title


def test_registry_resolves_fall_guys():
    """Verify registry correctly resolves FallGuysDetector via aliases and title detection."""
    # 1. Explicit aliases
    for alias in ["fall_guys", "Fall Guys", "fallguys", "fall-guys"]:
        d = get_detector(alias)
        assert isinstance(d, FallGuysDetector)
        assert d.game_id == "fall_guys"
        assert d.game_display_name == "Fall Guys"

    # 2. Video title auto-detection
    d_auto = get_detector(video_title="Fall Guys live stream - Solo Show Crown Hunting")
    assert isinstance(d_auto, FallGuysDetector)

    d_auto_compact = get_detector(
        video_title="Fallguys Season 4 New Obstacles Full Play"
    )
    assert isinstance(d_auto_compact, FallGuysDetector)

    # 3. Marvel Rivals still works
    d_mvr = get_detector(video_title="Marvel Rivals Grandmaster")
    assert isinstance(d_mvr, MarvelRivalsDetector)

    # 4. Fallback to generic
    d_gen = get_detector(video_title="Elden Ring Stream")
    assert isinstance(d_gen, GenericHighlightDetector)

    # 5. Catalog list contains fall_guys
    catalog = list_supported_detectors()
    ids = [item["id"] for item in catalog]
    assert "fall_guys" in ids
    assert "marvel_rivals" in ids
    assert "generic" in ids


def test_speech_boundary_snapping_synthetic(tmp_path):
    """Test speech boundary snapping with mocked ffmpeg silence intervals."""
    fake_audio = tmp_path / "stream.wav"
    fake_audio.write_bytes(b"dummy")

    with patch(
        "app.services.highlight.speech_mining.detect_silence_intervals"
    ) as mock_silence:
        # Mock silence intervals around start (e.g. pause ends at 19.5s)
        # and around end (e.g. pause starts at 41.2s)
        def silence_side_effect(media_path, start_seconds, duration_seconds, **kwargs):
            if start_seconds < 25.0:
                return [(18.0, 19.5)]
            else:
                return [(41.2, 43.0)]

        mock_silence.side_effect = silence_side_effect

        snapped_start, snapped_end, dur = snap_to_speech_boundaries(
            media_path=fake_audio,
            start_seconds=20.0,
            end_seconds=42.0,
            min_duration=18.0,
            max_duration=45.0,
        )

        assert snapped_start == 19.5
        assert snapped_end == 41.2
        assert dur == round(41.2 - 19.5, 2)


def test_fall_guys_ocr_matching_banners():
    """Verify FallGuysDetector correctly detects Crown, Qualified, Final Round, Eliminated banners."""
    detector = FallGuysDetector()

    # Create synthetic frames with mocked OCR returns
    f_crown = ROIFrame(
        timestamp=45.0,
        roi_name="center_banner",
        width=1400,
        height=400,
        raw_rgb=b"\x00" * (1400 * 400 * 3),
    )
    f_qual = ROIFrame(
        timestamp=85.0,
        roi_name="center_banner",
        width=1400,
        height=400,
        raw_rgb=b"\x00" * (1400 * 400 * 3),
    )
    f_elim = ROIFrame(
        timestamp=120.0,
        roi_name="center_banner",
        width=1400,
        height=400,
        raw_rgb=b"\x00" * (1400 * 400 * 3),
    )

    batch_rois = BatchROIExtractionResult(
        file_path="mock.mp4",
        source_width=1920,
        source_height=1080,
        fps=1.0,
        windows_extracted=[
            WindowROIExtractionResult(
                window_start=35.0,
                window_end=55.0,
                window_duration=20.0,
                frames_by_roi={"center_banner": [f_crown]},
                total_frames=1,
            ),
            WindowROIExtractionResult(
                window_start=75.0,
                window_end=95.0,
                window_duration=20.0,
                frames_by_roi={"center_banner": [f_qual]},
                total_frames=1,
            ),
            WindowROIExtractionResult(
                window_start=110.0,
                window_end=130.0,
                window_duration=20.0,
                frames_by_roi={"center_banner": [f_elim]},
                total_frames=1,
            ),
        ],
        total_frames=3,
    )

    def mock_read(frame):
        if frame.timestamp == 45.0:
            return [
                OCRToken(
                    text="WINNER!",
                    confidence=0.98,
                    left=100,
                    top=50,
                    width=200,
                    height=50,
                )
            ]
        elif frame.timestamp == 85.0:
            return [
                OCRToken(
                    text="QUALIFIED!",
                    confidence=0.96,
                    left=100,
                    top=50,
                    width=200,
                    height=50,
                )
            ]
        elif frame.timestamp == 120.0:
            return [
                OCRToken(
                    text="ELIMINATED!",
                    confidence=0.94,
                    left=100,
                    top=50,
                    width=200,
                    height=50,
                )
            ]
        return []

    with patch.object(detector.ocr_reader, "read", side_effect=mock_read):
        events = detector._match_banner_events(batch_rois)

        assert len(events) == 3
        # Window 0: Crown Victory
        assert events[0][0]["event_type"] == "crown_victory"
        assert events[0][0]["score"] == 1.00
        assert events[0][0]["time"] == 45.0

        # Window 1: Round Qualified
        assert events[1][0]["event_type"] == "round_qualified"
        assert events[1][0]["score"] == 0.92
        assert events[1][0]["time"] == 85.0

        # Window 2: Eliminated
        assert events[2][0]["event_type"] == "eliminated"
        assert events[2][0]["score"] == 0.78
        assert events[2][0]["time"] == 120.0


def test_fall_guys_detect_pipeline(tmp_path):
    """End-to-end FallGuysDetector test with mock audio scan and OCR."""
    fake_video = tmp_path / "fall_guys_vod.mp4"
    fake_video.write_bytes(b"dummy")

    mock_scan = AudioScanResult(
        file_path=str(fake_video),
        duration_seconds=300.0,
        has_audio=True,
        silence_threshold_lufs=-30.0,
        excitement_threshold_lufs=-16.0,
        total_buckets=150,
        candidate_windows=[
            AudioCandidateWindow(
                start_seconds=40.0,
                end_seconds=60.0,
                duration_seconds=20.0,
                peak_lufs=-10.0,
                mean_lufs=-14.0,
                peak_true_peak_db=-0.5,
                score=0.95,
                bucket_count=10,
            ),
            AudioCandidateWindow(
                start_seconds=150.0,
                end_seconds=170.0,
                duration_seconds=20.0,
                peak_lufs=-11.0,
                mean_lufs=-15.0,
                peak_true_peak_db=-0.8,
                score=0.88,
                bucket_count=10,
            ),
        ],
    )

    f_crown = ROIFrame(
        timestamp=52.0,
        roi_name="center_banner",
        width=1400,
        height=400,
        raw_rgb=b"\x00" * 100,
    )
    f_qual = ROIFrame(
        timestamp=162.0,
        roi_name="center_banner",
        width=1400,
        height=400,
        raw_rgb=b"\x00" * 100,
    )

    mock_rois = BatchROIExtractionResult(
        file_path=str(fake_video),
        source_width=1920,
        source_height=1080,
        fps=1.0,
        windows_extracted=[
            WindowROIExtractionResult(
                window_start=40.0,
                window_end=60.0,
                window_duration=20.0,
                frames_by_roi={"center_banner": [f_crown]},
                total_frames=1,
            ),
            WindowROIExtractionResult(
                window_start=150.0,
                window_end=170.0,
                window_duration=20.0,
                frames_by_roi={"center_banner": [f_qual]},
                total_frames=1,
            ),
        ],
        total_frames=2,
    )

    detector = FallGuysDetector()

    def mock_read(frame):
        if frame.timestamp == 52.0:
            return [
                OCRToken(
                    text="WINNER!",
                    confidence=0.99,
                    left=100,
                    top=50,
                    width=200,
                    height=50,
                )
            ]
        elif frame.timestamp == 162.0:
            return [
                OCRToken(
                    text="QUALIFIED!",
                    confidence=0.97,
                    left=100,
                    top=50,
                    width=200,
                    height=50,
                )
            ]
        return []

    progress_log = []

    def mock_progress(pct, stage):
        progress_log.append((pct, stage))

    with (
        patch(
            "app.services.highlight.service.scan_audio_energy",
            return_value=mock_scan,
        ),
        patch(
            "app.services.highlight.service.extract_candidate_windows_rois",
            return_value=mock_rois,
        ),
        patch.object(detector.ocr_reader, "read", side_effect=mock_read),
        patch(
            "app.services.highlight.detectors.fall_guys.extract_thumbnail_frame"
        ) as mock_thumb,
        patch(
            "app.services.highlight.detectors.fall_guys.snap_to_speech_boundaries"
        ) as mock_snap,
    ):
        mock_snap.side_effect = (
            lambda media_path, start_seconds, end_seconds, **kwargs: (
                start_seconds,
                end_seconds,
                round(end_seconds - start_seconds, 2),
            )
        )

        candidates = detector.detect(
            video_id="vod_fallguys_01",
            media_path=fake_video,
            min_score=0.5,
            progress_callback=mock_progress,
        )

        assert len(candidates) == 2
        cand_crown = candidates[0]
        cand_qual = candidates[1]

        # Verify crown candidate
        assert cand_crown.event_type == "crown_victory"
        assert cand_crown.score == 1.0
        assert cand_crown.game == "Fall Guys"
        assert "CROWN VICTORY" in cand_crown.suggested_title
        assert "Crown" in cand_crown.suggested_tags
        assert "Shorts" in cand_crown.suggested_tags
        assert cand_crown.candidate_id.startswith("cand_fg_")

        # Verify qualified candidate
        assert cand_qual.event_type == "round_qualified"
        assert cand_qual.score == 0.92
        assert cand_qual.game == "Fall Guys"
        assert "Qualification" in cand_qual.suggested_title
        assert "Qualified" in cand_qual.suggested_tags

        # Verify thumbnail calls
        assert mock_thumb.call_count == 2
        assert len(progress_log) >= 4


def test_fall_guys_metadata_generation():
    """Verify deterministic build_title, build_tags and build_description for Fall Guys."""
    candidate_crown = {
        "event_type": "crown_victory",
        "score": 1.0,
        "suggested_tags": ["Crown", "Winner", "Shorts"],
        "game": "Fall Guys",
    }

    title = build_title(
        video=MagicMock(title="Fall Guys Solo Show"),
        candidate=candidate_crown,
        game="Fall Guys",
    )
    assert "Fall Guys Crown Victory" in title or "CROWN VICTORY" in title.upper()
    assert "#FallGuys" in title

    tags = build_tags(
        video=MagicMock(title="Fall Guys Solo Show"),
        candidate=candidate_crown,
        game="Fall Guys",
    )
    assert "Fall Guys" in tags
    assert "Crown" in tags
    assert "Shorts" in tags

    desc = build_description(
        video=MagicMock(
            title="Fall Guys Live Stream", webpage_url="https://youtube.com/watch?v=fg1"
        ),
        candidate=candidate_crown,
        game="Fall Guys",
    )
    assert "Crown Victory" in desc
    assert "Fall Guys" in desc
