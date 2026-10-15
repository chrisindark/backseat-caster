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
    width: int = 520,
    height: int = 140,
    timestamp: float = 10.0,
    roi_name: str = "center_ko",
) -> ROIFrame:
    """Helper to generate in-memory synthetic ROIFrame with realistic banner dimensions."""
    from PIL import ImageFont

    img = Image.new("RGB", (width, height), color=bg_color)
    if text:
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=28)
        # Position centered
        draw.text((120, 50), text, fill=text_color, font=font)

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
    assert hexa[0] == "hexa_ko"
    assert hexa[2] == 6

    # ACE and isolated 6 KO are stripped to prevent scoreboard false positives
    assert matcher.classify_text("ACE") is None
    assert matcher.classify_text("6 KO") is None

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

    double_bang = matcher.classify_text("DOUBLE!")
    assert double_bang is not None
    assert double_bang[0] == "double_ko"
    assert double_bang[2] == 2

    # Specific streak milestone
    streak_5 = matcher.classify_text("5 PLAYER KO STREAK!")
    assert streak_5 is not None
    assert streak_5[0] == "kill_streak"
    assert streak_5[1] == "5 PLAYER KO STREAK"

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
    # f2 was within 0.5s of f1 with identical DOUBLE KO, so corroborated
    assert len(res.events) == 2
    assert res.events[0].event_type == "double_ko"
    assert res.events[0].frame_count == 2
    assert res.events[1].event_type == "triple_ko"
    assert res.events[1].frame_count == 1
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


def test_negative_screen_rejection():
    """Verify that Tab scoreboard and stats screens are immediately discarded."""
    matcher = VisualMatcher()
    for neg_text in [
        "YOUR TEAM ENEMY TEAM",
        "DAMAGE BLOCKED 2850",
        "CAREER STATS HEALING",
        "PRESS TAB",
    ]:
        frame = _create_synthetic_roi_frame(
            text=neg_text,
            text_color=(255, 215, 0),
            timestamp=50.0,
            roi_name="center_ko",
        )
        evt = matcher.evaluate_frame(frame)
        assert evt is None, f"Expected {neg_text} to be rejected by negative filter"


def test_typography_gating_rejects_tiny_text():
    """Verify that tiny text below minimum bounding box threshold is rejected."""
    from PIL import Image, ImageDraw

    # Frame with tiny font (default PIL font produces ~12px height)
    img = Image.new("RGB", (520, 140), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.text((150, 60), "TRIPLE KO", fill=(255, 215, 0))  # tiny unscaled font

    frame = ROIFrame(
        timestamp=10.0,
        roi_name="center_ko",
        width=520,
        height=140,
        raw_rgb=img.tobytes(),
    )
    # Configure min_gold_ratio lower so color passes, but typography fails
    matcher = VisualMatcher(
        config=VisualMatcherConfig(
            min_gold_ratio=0.0001, min_box_height=22.0, min_box_width=90.0
        )
    )
    evt = matcher.evaluate_frame(frame)
    assert evt is None


def test_classify_text_returns_matched_text():
    """classify_text exposes the exact matched substring for box attribution."""
    matcher = VisualMatcher()

    triple = matcher.classify_text("TRIPLE KO")
    assert triple is not None
    assert triple[0] == "triple_ko"
    assert triple[4].replace(" ", "") == "TRIPLEKO"

    streak = matcher.classify_text("5 PLAYER KO STREAK!")
    assert streak is not None
    assert streak[0] == "kill_streak"
    assert streak[4].replace(" ", "") == "5PLAYERKOSTREAK"


def test_matched_typography_uses_only_participating_boxes():
    """Typography metrics must come from the matched box, not the whole ROI."""
    # A tiny banner next to a huge unrelated box must report only the banner.
    items = [
        ("TEAM WIPE", 0.99, 30.0, 25.0),
        ("99999", 0.99, 400.0, 40.0),
    ]
    width, height = VisualMatcher._matched_typography(items, "TEAM WIPE")
    assert width == 30.0
    assert height == 25.0

    # A multi-token banner sums the participating boxes.
    multi = [("TEAM", 0.9, 40.0, 25.0), ("WIPE", 0.9, 45.0, 25.0)]
    multi_w, multi_h = VisualMatcher._matched_typography(multi, "TEAM WIPE")
    assert multi_w == 85.0
    assert multi_h == 25.0

    # Unattributable match falls back to the largest box in the ROI.
    fallback = [("ZZZ", 0.9, 12.0, 8.0), ("YYY", 0.9, 70.0, 30.0)]
    fb_w, fb_h = VisualMatcher._matched_typography(fallback, "NO MATCH HERE")
    assert fb_w == 70.0
    assert fb_h == 30.0


def test_width_gate_uses_matched_box_not_roi_total(monkeypatch):
    """A tiny banner must not pass the width gate just because large unrelated
    HUD text shares the ROI (regression for summed-width gating)."""
    matcher = VisualMatcher(
        config=VisualMatcherConfig(min_box_height=22.0, min_box_width=90.0)
    )
    monkeypatch.setattr(
        matcher, "check_color_triggers", lambda frame: (True, 0.02, 0.0)
    )
    frame = _create_synthetic_roi_frame(text=None, timestamp=5.0)

    # Tiny "TEAM WIPE" alongside a wide unrelated box -> rejected.
    monkeypatch.setattr(
        matcher,
        "run_ocr",
        lambda f: [
            ("TEAM WIPE", 0.99, 30.0, 25.0),
            ("TEAM KDA 99999", 0.99, 400.0, 40.0),
        ],
    )
    assert matcher.evaluate_frame(frame) is None

    # A genuinely large matched banner still passes the gate.
    monkeypatch.setattr(
        matcher, "run_ocr", lambda f: [("TEAM WIPE", 0.99, 150.0, 30.0)]
    )
    evt = matcher.evaluate_frame(frame)
    assert evt is not None
    assert evt.event_type == "team_wipe"


def test_evaluate_window_calls_color_gate_once_per_frame(monkeypatch):
    """evaluate_window must not run the HSV color gate twice per frame."""
    matcher = VisualMatcher()
    calls = {"n": 0}
    original = matcher.check_color_triggers

    def counting(frame):
        calls["n"] += 1
        return original(frame)

    monkeypatch.setattr(matcher, "check_color_triggers", counting)

    frame_a = _create_synthetic_roi_frame(text="TRIPLE KO", timestamp=1.0)
    frame_b = _create_synthetic_roi_frame(
        text=None, timestamp=1.5, bg_color=(25, 25, 25)
    )
    window_rois = WindowROIExtractionResult(
        window_start=1.0,
        window_end=2.0,
        window_duration=1.0,
        frames_by_roi={"center_ko": [frame_a, frame_b]},
        total_frames=2,
    )

    matcher.evaluate_window(window_rois)
    assert calls["n"] == 2
