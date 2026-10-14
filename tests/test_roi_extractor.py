"""Automated tests for Targeted Marvel Rivals HUD Region Extractor."""

import subprocess
from pathlib import Path

import pytest

from app.services.highlight.audio_scanner import AudioCandidateWindow
from app.services.highlight.roi_extractor import (
    MARVEL_RIVALS_HUD_REGIONS,
    BatchROIExtractionResult,
    HUDRegion,
    ROIExtractor,
    ROIExtractorConfig,
    ROIFrame,
    WindowROIExtractionResult,
    compute_crop_geometry,
    extract_candidate_windows_rois,
    extract_window_rois,
)


@pytest.fixture(scope="session")
def roi_test_videos(tmp_path_factory) -> dict[str, Path]:
    """Generate synthetic video assets at 1080p and 720p using FFmpeg."""
    temp_dir = tmp_path_factory.mktemp("roi_extractor_assets")

    # 1. 5s 1920x1080 test video
    video_1080p = temp_dir / "test_1080p.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=5:size=1920x1080:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_1080p),
        ],
        check=True,
        capture_output=True,
    )

    # 2. 5s 1280x720 test video
    video_720p = temp_dir / "test_720p.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=5:size=1280x720:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_720p),
        ],
        check=True,
        capture_output=True,
    )

    return {
        "1080p": video_1080p,
        "720p": video_720p,
    }


def test_compute_crop_geometry_1080p():
    """Verify crop geometry on native 1080p resolution matches base HUD definitions."""
    ko = MARVEL_RIVALS_HUD_REGIONS["center_ko"]
    kf = MARVEL_RIVALS_HUD_REGIONS["kill_feed"]
    ult = MARVEL_RIVALS_HUD_REGIONS["ultimate_meter"]
    obj = MARVEL_RIVALS_HUD_REGIONS["objective_banner"]

    x_ko, y_ko, w_ko, h_ko = compute_crop_geometry(ko, 1920, 1080)
    assert (x_ko, y_ko, w_ko, h_ko) == (700, 230, 520, 140)

    x_kf, y_kf, w_kf, h_kf = compute_crop_geometry(kf, 1920, 1080)
    assert (x_kf, y_kf, w_kf, h_kf) == (1400, 40, 480, 220)

    x_ult, y_ult, w_ult, h_ult = compute_crop_geometry(ult, 1920, 1080)
    assert (x_ult, y_ult, w_ult, h_ult) == (920, 920, 80, 50)

    x_obj, y_obj, w_obj, h_obj = compute_crop_geometry(obj, 1920, 1080)
    assert (x_obj, y_obj, w_obj, h_obj) == (710, 20, 500, 100)


def test_compute_crop_geometry_scaling():
    """Verify 720p, 1440p, and 4K resolution scaling."""
    ko = MARVEL_RIVALS_HUD_REGIONS["center_ko"]

    # 720p (scale factor 2/3)
    x720, y720, w720, h720 = compute_crop_geometry(ko, 1280, 720)
    assert (x720, y720, w720, h720) == (467, 153, 346, 92)

    # 1440p (scale factor 4/3)
    x1440, y1440, w1440, h1440 = compute_crop_geometry(ko, 2560, 1440)
    assert (x1440, y1440, w1440, h1440) == (933, 307, 692, 186)

    # 4K (scale factor 2.0)
    x4k, y4k, w4k, h4k = compute_crop_geometry(ko, 3840, 2160)
    assert (x4k, y4k, w4k, h4k) == (1400, 460, 1040, 280)


def test_compute_crop_geometry_ultrawide():
    """Verify 21:9 ultrawide geometry centers KO and right-anchors kill feed."""
    ko = MARVEL_RIVALS_HUD_REGIONS["center_ko"]
    kf = MARVEL_RIVALS_HUD_REGIONS["kill_feed"]

    # 2560x1080 (21:9)
    x_ko, y_ko, w_ko, h_ko = compute_crop_geometry(ko, 2560, 1080)
    # Horizontal center offset: (2560 - 1920) / 2 = 320. x = 700 + 320 = 1020
    assert (x_ko, y_ko, w_ko, h_ko) == (1020, 230, 520, 140)

    x_kf, y_kf, w_kf, h_kf = compute_crop_geometry(kf, 2560, 1080)
    # Right-anchored: 1920 - (1400 + 480) = 40 margin. 2560 - 40 - 480 = 2040
    assert (x_kf, y_kf, w_kf, h_kf) == (2040, 40, 480, 220)


def test_extract_window_rois_1080p(roi_test_videos):
    """Test extracting HUD ROIs on 1080p video at 1 FPS."""
    res = extract_window_rois(
        roi_test_videos["1080p"],
        start_seconds=1.0,
        duration_seconds=3.0,
        fps=1.0,
    )

    assert isinstance(res, WindowROIExtractionResult)
    assert res.window_start == 1.0
    assert res.window_end == 4.0
    assert res.window_duration == 3.0
    assert res.total_frames == 6

    # Verify Center KO frames
    ko_frames = res.frames_by_roi["center_ko"]
    assert len(ko_frames) == 3
    assert ko_frames[0].width == 520
    assert ko_frames[0].height == 140
    assert len(ko_frames[0].raw_rgb) == 520 * 140 * 3
    assert ko_frames[0].timestamp == 1.0
    assert ko_frames[1].timestamp == 2.0
    assert ko_frames[2].timestamp == 3.0

    # Verify Kill Feed frames
    kf_frames = res.frames_by_roi["kill_feed"]
    assert len(kf_frames) == 3
    assert kf_frames[0].width == 480
    assert kf_frames[0].height == 220
    assert len(kf_frames[0].raw_rgb) == 480 * 220 * 3


def test_extract_window_rois_720p_normalized(roi_test_videos):
    """Test that 720p source video ROIs are normalized to standard 1080p base geometry."""
    res = extract_window_rois(
        roi_test_videos["720p"],
        start_seconds=0.5,
        duration_seconds=2.0,
        fps=1.0,
    )

    assert res.total_frames == 4
    ko_frames = res.frames_by_roi["center_ko"]
    # Cropped from 720p but normalized back to 520x140
    assert ko_frames[0].width == 520
    assert ko_frames[0].height == 140
    assert len(ko_frames[0].raw_rgb) == 520 * 140 * 3


def test_extract_window_rois_higher_fps(roi_test_videos):
    """Test extracting at 2.0 FPS extracts twice as many frames."""
    res = extract_window_rois(
        roi_test_videos["1080p"],
        start_seconds=1.0,
        duration_seconds=2.0,
        fps=2.0,
    )

    # 2 seconds at 2 fps = 4 frames per ROI (total 8 frames)
    assert res.total_frames == 8
    assert len(res.frames_by_roi["center_ko"]) == 4
    assert res.frames_by_roi["center_ko"][1].timestamp == 1.5


def test_roi_frame_pixel_access_and_color_counts():
    """Test ROIFrame pixel inspection, color matching, and ratio calculations."""
    width, height = 4, 4
    # Create 16-pixel buffer: 4 Gold pixels (255, 215, 0) and 12 Black pixels (0, 0, 0)
    gold = bytes([255, 215, 0])
    black = bytes([0, 0, 0])
    raw = gold * 4 + black * 12

    frame = ROIFrame(
        timestamp=10.0,
        roi_name="test_roi",
        width=width,
        height=height,
        raw_rgb=raw,
    )

    assert frame.get_pixel_rgb(0, 0) == (255, 215, 0)
    assert frame.get_pixel_rgb(0, 1) == (0, 0, 0)

    with pytest.raises(IndexError):
        frame.get_pixel_rgb(4, 4)

    # Count Gold pixels
    gold_matches = frame.count_color_matches(
        r_min=240,
        r_max=255,
        g_min=200,
        g_max=230,
        b_min=0,
        b_max=20,
    )
    assert gold_matches == 4

    # Ratio: 4 out of 16 pixels = 0.25 (25%)
    ratio = frame.color_ratio(
        r_min=240,
        r_max=255,
        g_min=200,
        g_max=230,
        b_min=0,
        b_max=20,
    )
    assert ratio == 0.25


def test_roi_frame_ppm_conversion_and_file_save(tmp_path):
    """Test PPM byte generation and file writing."""
    raw = bytes([255, 0, 0, 0, 255, 0])  # 2 pixels: Red, Green
    frame = ROIFrame(
        timestamp=2.5,
        roi_name="center_ko",
        width=2,
        height=1,
        raw_rgb=raw,
    )

    ppm_bytes = frame.to_ppm()
    assert ppm_bytes.startswith(b"P6\n2 1\n255\n")

    ppm_path = tmp_path / "test.ppm"
    saved = frame.save_ppm(ppm_path)
    assert saved.exists()
    assert saved.read_bytes() == ppm_bytes

    # PNG export via FFmpeg
    png_path = tmp_path / "test.png"
    frame.save_png(png_path)
    assert png_path.exists()
    assert png_path.stat().st_size > 0


def test_extract_candidate_windows_batch(roi_test_videos):
    """Test batch extraction across AudioCandidateWindows with progress callback."""
    candidate_windows = [
        AudioCandidateWindow(
            start_seconds=0.5,
            end_seconds=2.5,
            duration_seconds=2.0,
            mean_lufs=-15.0,
            peak_lufs=-10.0,
            peak_true_peak_db=-2.0,
            score=0.90,
            bucket_count=4,
        ),
        AudioCandidateWindow(
            start_seconds=3.0,
            end_seconds=4.5,
            duration_seconds=1.5,
            mean_lufs=-18.0,
            peak_lufs=-12.0,
            peak_true_peak_db=-4.0,
            score=0.75,
            bucket_count=3,
        ),
    ]

    progress_events: list[tuple[float, str]] = []

    def on_progress(pct: float, msg: str) -> None:
        progress_events.append((pct, msg))

    batch_res = extract_candidate_windows_rois(
        roi_test_videos["1080p"],
        windows=candidate_windows,
        fps=1.0,
        progress_callback=on_progress,
    )

    assert isinstance(batch_res, BatchROIExtractionResult)
    assert batch_res.source_width == 1920
    assert batch_res.source_height == 1080
    assert len(batch_res.windows_extracted) == 2
    assert batch_res.total_frames >= 4
    assert batch_res.extraction_duration_seconds > 0.0

    assert len(progress_events) >= 1
    assert progress_events[-1][0] == 100.0


def test_unknown_roi_error(roi_test_videos):
    """Test requesting an unregistered ROI raises ValueError."""
    extractor = ROIExtractor()
    with pytest.raises(ValueError, match="Unknown HUD region 'minimap'"):
        extractor.extract_window_rois(
            roi_test_videos["1080p"],
            start_seconds=1.0,
            duration_seconds=1.0,
            roi_names=["minimap"],
        )


def test_nonexistent_media_error(tmp_path):
    """Test extracting from missing video raises FileNotFoundError."""
    missing = tmp_path / "ghost.mp4"
    extractor = ROIExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract_window_rois(
            missing,
            start_seconds=1.0,
            duration_seconds=1.0,
        )


def test_custom_hud_region_registration(roi_test_videos):
    """Test registering and extracting a custom HUD region."""
    custom_region = HUDRegion(
        name="custom_ammo",
        x=1600,
        y=900,
        width=200,
        height=100,
        description="Custom Weapon Ammo ROI",
    )

    extractor = ROIExtractor(
        config=ROIExtractorConfig(custom_regions={"custom_ammo": custom_region})
    )

    res = extractor.extract_window_rois(
        roi_test_videos["1080p"],
        start_seconds=1.0,
        duration_seconds=1.0,
        roi_names=["custom_ammo"],
    )

    assert "custom_ammo" in res.frames_by_roi
    frames = res.frames_by_roi["custom_ammo"]
    assert len(frames) == 1
    assert frames[0].width == 200
    assert frames[0].height == 100
