"""Tests for the composed clip-length ceiling and its soft upload tiers."""

import json

import pytest

from app.rendering.config import (
    DEFAULT_MAX_CLIP_SECONDS,
    SHORTS_DURATION_TIERS,
    DurationBudget,
    default_render_config,
)


def test_default_budget_matches_the_shipped_ceiling():
    budget = DurationBudget(bookend_seconds=3.2)
    assert budget.max_seconds == DEFAULT_MAX_CLIP_SECONDS == 90.0
    assert budget.tiers == SHORTS_DURATION_TIERS == (60.0, 72.0, 88.0)
    assert budget.clip_budget == pytest.approx(86.8)


def test_clip_budget_subtracts_only_the_bookends():
    assert DurationBudget(bookend_seconds=0.0).clip_budget == 90.0
    assert DurationBudget(max_seconds=120.0, bookend_seconds=1.2).clip_budget == 118.8
    # A ceiling shorter than the cards still leaves a positive window.
    assert DurationBudget(max_seconds=5.0, bookend_seconds=9.0).clip_budget == 1.0


def test_composed_duration_includes_bookends():
    budget = DurationBudget(bookend_seconds=3.2)
    assert budget.composed_seconds(60.0) == 63.2
    assert budget.fits(86.8) is True
    assert budget.fits(86.9) is False
    assert budget.is_uploadable(86.8) is True


def test_clamp_trims_to_the_clip_budget():
    budget = DurationBudget(bookend_seconds=3.2)
    assert budget.clamp(120.0) == 86.8
    assert budget.clamp(30.0) == 30.0
    assert budget.clamp(-5.0) == 0.0


def test_every_tier_below_the_ceiling_stays_uploadable():
    """60/72/88 are labels, never gates: 61s or 80s must still upload."""
    budget = DurationBudget(bookend_seconds=0.0)
    assert budget.tier_for_composed(45.0) == "shorts"
    assert budget.tier_for_composed(60.0) == "shorts"
    assert budget.tier_for_composed(60.5) == "extended"
    assert budget.tier_for_composed(72.0) == "extended"
    assert budget.tier_for_composed(80.0) == "long"
    assert budget.tier_for_composed(88.0) == "long"
    assert budget.tier_for_composed(90.0) == "ceiling"
    assert budget.tier_for_composed(91.0) == "over_ceiling"

    for composed in (58.0, 60.0, 61.0, 72.0, 80.0, 88.0, 89.5, 90.0):
        assert budget.tier_for_composed(composed) != "over_ceiling"
        assert budget.fits(composed) is True


def test_tier_uses_the_composed_duration():
    budget = DurationBudget(bookend_seconds=3.2)
    # 58s of gameplay + 3.2s of cards is a 61.2s upload, past the 60s marker.
    assert budget.tier(58.0) == "extended"
    assert budget.tier(50.0) == "shorts"


def test_describe_reports_the_budget_for_the_manifest():
    budget = DurationBudget(bookend_seconds=3.2)
    payload = budget.describe(70.0)
    assert payload == {
        "max_seconds": 90.0,
        "bookend_seconds": 3.2,
        "clip_budget_seconds": 86.8,
        "tiers": [60.0, 72.0, 88.0],
        "composed_seconds": 73.2,
        "tier": "long",
        "uploadable": True,
    }
    assert budget.describe_composed(73.2) == payload


def test_over_ceiling_message_names_the_number_to_use():
    message = DurationBudget(bookend_seconds=3.2).over_ceiling_message(100.0)
    assert "100.0s" in message
    assert "86.8s or less" in message
    assert "90s ceiling" in message


def test_render_config_carries_the_ceiling():
    assert default_render_config.max_total_seconds == DEFAULT_MAX_CLIP_SECONDS


def test_manifest_records_the_duration_budget(tmp_path):
    from app.rendering.manifest import write_manifest
    from app.rendering.probe import MediaProbeResult

    probe = MediaProbeResult(
        file_path="in.mp4",
        file_size_bytes=1000,
        duration=120.0,
        width=1920,
        height=1080,
        fps=60.0,
        video_codec="h264",
        audio_codec="aac",
        has_audio=True,
    )
    budget = DurationBudget(bookend_seconds=3.2)

    manifest_path = write_manifest(
        output_dir=tmp_path,
        clip_id="clip_test",
        source_probe=probe,
        start_seconds=10.0,
        duration_seconds=70.0,
        outputs={"vertical_blur": {"duration": 73.2}},
        duration_budget=budget.describe(70.0),
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["duration_budget"]["composed_seconds"] == 73.2
    assert manifest["duration_budget"]["tier"] == "long"
    assert manifest["duration_budget"]["uploadable"] is True
