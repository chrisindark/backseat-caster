"""Automated tests for Marvel Rivals Visual Matcher (HSV color gating & RapidOCR)."""

from PIL import Image, ImageDraw

from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)
from app.services.highlight.visual_matcher import (
    BatchVisualMatchResult,
    VisualDetectionEvent,
    VisualMatcher,
    VisualMatcherConfig,
    WindowVisualMatchResult,
    evaluate_batch_visuals,
)


def _create_synthetic_roi_frame(
    text: str | None = None,
    text_color: tuple[int, int, int] = (255, 215, 0),  # Gold #FFD700
    bg_color: tuple[int, int, int] = (20, 20, 20),
    width: int = 480,
    height: int = 180,
    timestamp: float = 10.0,
    roi_name: str = "center_ko",
) -> ROIFrame:
    """Helper to generate in-memory synthetic ROIFrame with optional text."""
    img = Image.new("RGB", (width, height), color=bg_color)
    if text:
        draw = ImageDraw.Draw(img)
        # Position centered
        draw.text((140, 70), text, fill=text_color)

    return ROIFrame(
        timestamp=timestamp,
        roi_name=roi_name,
        width=width,
        height=height,
        raw_rgb=img.tobytes(),
    )


def test_classify_text_hierarchy():
    """Verify regex patterns correctly map gaming keywords to event tiers."""
    matcher = VisualMatcher()

    # Team wipe tier
    wipe = matcher.classify_text("TEAM WIPE")
    assert wipe is not None
    assert wipe[0] == "team_wipe"
    assert wipe[2] == 6
    assert wipe[3] == 1.00

    hexa = matcher.classify_text("HEXA KO")
    assert hexa is not None
    assert hexa[0] == "team_wipe"
    assert hexa[2] == 6

    ace = matcher.classify_text("ACE")
    assert ace is not None
    assert ace[0] == "team_wipe"

    # Penta KO tier
    penta = matcher.classify_text("PENTA KO")
    assert penta is not None
    assert penta[0] == "penta_ko"
    assert penta[2] == 5
    assert penta[3] == 0.95

    mega = matcher.classify_text("MEGA KO")
    assert mega is not None
    assert mega[0] == "penta_ko"
    assert mega[2] == 5

    # Quad KO tier
    quad = matcher.classify_text("QUAD KO")
    assert quad is not None
    assert quad[0] == "quad_ko"
    assert quad[2] == 4
    assert quad[3] == 0.90

    ultra = matcher.classify_text("ULTRA KO")
    assert ultra is not None
    assert ultra[0] == "quad_ko"
    assert ultra[2] == 4

    # Disruption: Shutdown
    shutdown = matcher.classify_text("SHUTDOWN")
    assert shutdown is not None
    assert shutdown[0] == "shutdown"
    assert shutdown[2] == 1
    assert shutdown[3] == 0.88

    denied = matcher.classify_text("DENIED")
    assert denied is not None
    assert denied[0] == "shutdown"

    # Streaks: Kill Streak
    streak = matcher.classify_text("UNSTOPPABLE")
    assert streak is not None
    assert streak[0] == "kill_streak"
    assert streak[2] == 1
    assert streak[3] == 0.85

    godlike = matcher.classify_text("GODLIKE")
    assert godlike is not None
    assert godlike[0] == "kill_streak"

    # Triple KO tier
    triple = matcher.classify_text("TRIPLE KO")
    assert triple is not None
    assert triple[0] == "triple_ko"
    assert triple[2] == 3
    assert triple[3] == 0.80

    # Clutch tier
    victory = matcher.classify_text("VICTORY")
    assert victory is not None
    assert victory[0] == "objective_clutch"
    assert victory[2] == 0
    assert victory[3] == 0.75

    overtime = matcher.classify_text("OVERTIME")
    assert overtime is not None
    assert overtime[0] == "objective_clutch"

    point = matcher.classify_text("POINT CAPTURED")
    assert point is not None
    assert point[0] == "objective_clutch"

    # Double KO tier
    double = matcher.classify_text("DOUBLE KO")
    assert double is not None
    assert double[0] == "double_ko"
    assert double[2] == 2
    assert double[3] == 0.70

    # Single KO tier
    elim = matcher.classify_text("ELIMINATED")
    assert elim is not None
    assert elim[0] == "single_ko"
    assert elim[2] == 1
    assert elim[3] == 0.50

    plus100 = matcher.classify_text("+100")
    assert plus100 is not None
    assert plus100[0] == "single_ko"

    first_blood = matcher.classify_text("FIRST BLOOD")
    assert first_blood is not None
    assert first_blood[0] == "single_ko"

    # Match defeat tier
    defeat = matcher.classify_text("DEFEAT")
    assert defeat is not None
    assert defeat[0] == "match_defeat"
    assert defeat[2] == 0
    assert defeat[3] == 0.35

    round_lost = matcher.classify_text("ROUND LOST")
    assert round_lost is not None
    assert round_lost[0] == "match_defeat"

    # Unrelated text
    assert matcher.classify_text("HEALTH PACK COOLDOWN") is None


def test_check_color_triggers_positive_and_negative():
    """Verify HSV gating flags gold/red and filters neutral dark backgrounds."""
    matcher = VisualMatcher()

    # 1. Negative: Neutral dark frame
    neutral_frame = _create_synthetic_roi_frame(text=None, bg_color=(25, 25, 25))
    has_trigger, gold_r, red_r = matcher.check_color_triggers(neutral_frame)
    assert has_trigger is False
    assert gold_r == 0.0
    assert red_r == 0.0

    # 2. Positive: Frame with gold text
    gold_frame = _create_synthetic_roi_frame(text="TRIPLE KO", text_color=(255, 215, 0))
    has_trigger, gold_r, _ = matcher.check_color_triggers(gold_frame)
    assert has_trigger is True
    assert gold_r >= 0.001

    # 3. Positive: Frame with red accent
    red_frame = _create_synthetic_roi_frame(text="VICTORY", text_color=(255, 30, 30))
    has_trigger, _, red_r = matcher.check_color_triggers(red_frame)
    assert has_trigger is True
    assert red_r >= 0.001


def test_evaluate_frame_gold_triple_ko():
    """Test full evaluation pipeline detects Gold TRIPLE KO banner."""
    matcher = VisualMatcher()
    frame = _create_synthetic_roi_frame(
        text="TRIPLE KO",
        text_color=(255, 215, 0),
        timestamp=25.0,
        roi_name="center_ko",
    )

    event = matcher.evaluate_frame(frame)
    assert isinstance(event, VisualDetectionEvent)
    assert event.event_type == "triple_ko"
    assert "TRIPLE KO" in event.label
    assert event.kill_count == 3
    assert event.score_weight == 0.80
    assert event.timestamp == 25.0
    assert event.confidence >= 0.50
    assert event.gold_pixel_ratio >= 0.001


def test_evaluate_frame_skips_when_no_color():
    """Test that frames without Gold/Red accents skip OCR entirely."""
    # White text (no gold or red saturation)
    frame = _create_synthetic_roi_frame(
        text="TRIPLE KO",
        text_color=(255, 255, 255),
        timestamp=10.0,
    )

    matcher = VisualMatcher(config=VisualMatcherConfig(skip_ocr_without_color=True))
    event = matcher.evaluate_frame(frame)
    # Gating pruned it before OCR
    assert event is None


def test_evaluate_window_deduplication():
    """Test that identical banners appearing on consecutive frames within 1s are deduplicated."""
    matcher = VisualMatcher()

    # 3 frames at 1.0s, 1.5s (same event), and 3.0s (new event)
    f1 = _create_synthetic_roi_frame(
        text="DOUBLE KO", timestamp=1.0, roi_name="center_ko"
    )
    f2 = _create_synthetic_roi_frame(
        text="DOUBLE KO", timestamp=1.5, roi_name="center_ko"
    )
    f3 = _create_synthetic_roi_frame(
        text="TRIPLE KO", timestamp=3.0, roi_name="center_ko"
    )

    window_rois = WindowROIExtractionResult(
        window_start=1.0,
        window_end=4.0,
        window_duration=3.0,
        frames_by_roi={"center_ko": [f1, f2, f3]},
        total_frames=3,
    )

    res = matcher.evaluate_window(window_rois)
    assert isinstance(res, WindowVisualMatchResult)
    # f2 was within 0.5s of f1 with identical DOUBLE KO, so deduplicated
    assert len(res.events) == 2
    assert res.events[0].event_type == "double_ko"
    assert res.events[1].event_type == "triple_ko"
    assert res.peak_event_type == "triple_ko"
    assert res.total_kills == 3


def test_evaluate_batch_visuals():
    """Test batch visual matching across candidate windows."""
    f_action = _create_synthetic_roi_frame(
        text="TEAM WIPE", timestamp=5.0, roi_name="center_ko"
    )
    f_quiet = _create_synthetic_roi_frame(text=None, timestamp=15.0)

    win1 = WindowROIExtractionResult(
        window_start=4.0,
        window_end=7.0,
        window_duration=3.0,
        frames_by_roi={"center_ko": [f_action]},
        total_frames=1,
    )
    win2 = WindowROIExtractionResult(
        window_start=14.0,
        window_end=17.0,
        window_duration=3.0,
        frames_by_roi={"center_ko": [f_quiet]},
        total_frames=1,
    )

    batch_rois = BatchROIExtractionResult(
        file_path="dummy_vod.mp4",
        source_width=1920,
        source_height=1080,
        fps=1.0,
        windows_extracted=[win1, win2],
        total_frames=2,
        extraction_duration_seconds=0.1,
    )

    progress_events: list[tuple[float, str]] = []

    def on_progress(pct: float, msg: str) -> None:
        progress_events.append((pct, msg))

    batch_res = evaluate_batch_visuals(batch_rois, progress_callback=on_progress)
    assert isinstance(batch_res, BatchVisualMatchResult)
    assert len(batch_res.windows_matched) == 2
    assert batch_res.total_events_detected == 1
    assert batch_res.windows_matched[0].peak_event_type == "team_wipe"
    assert batch_res.windows_matched[1].peak_event_type is None
    assert len(progress_events) >= 1
    assert progress_events[-1][0] == 100.0
