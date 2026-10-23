"""Automated tests for ultimate meter OCR, gauge fallback and cast tracking."""

import math

import numpy as np

from app.services.highlight.ocr import OCRToken
from app.services.highlight.roi_extractor import ROIFrame, WindowROIExtractionResult
from app.services.highlight.ultimate_meter import (
    UltimateMeterConfig,
    UltimateMeterTracker,
    UltimateReading,
    parse_charge_percent,
)


class FakeOCR:
    def __init__(self, mapping: dict[float, list[OCRToken]]):
        self.mapping = mapping

    def read(self, frame: ROIFrame) -> list[OCRToken]:
        return self.mapping.get(round(frame.timestamp, 3), [])


def make_frame(
    timestamp: float,
    pixels: list[tuple[tuple[int, int, int], tuple[int, int, int]]] | None = None,
    width: int = 80,
    height: int = 50,
    background: tuple[int, int, int] = (10, 10, 10),
) -> ROIFrame:
    """Build a meter ROI frame, optionally painting specific pixels bright."""
    array = np.zeros((height, width, 3), dtype=np.uint8)
    array[:, :] = background
    for (x, y), color in pixels or []:
        array[y, x] = color
    return ROIFrame(
        timestamp=timestamp,
        roi_name="ultimate_meter",
        width=width,
        height=height,
        raw_rgb=array.tobytes(),
    )


def ring_points(radius: float, samples: int, width: int = 80, height: int = 50):
    cx, cy = width / 2.0, height / 2.0
    points = []
    for index in range(samples):
        angle = (2.0 * math.pi * index) / samples
        points.append(
            (
                int(round(cx + radius * math.cos(angle))),
                int(round(cy + radius * math.sin(angle))),
            )
        )
    return points


def test_parse_charge_percent():
    assert parse_charge_percent("88%") == 88.0
    assert parse_charge_percent("ULT 100") == 100.0
    assert parse_charge_percent("0%") == 0.0
    assert parse_charge_percent("READY") is None
    assert parse_charge_percent("250%") is None


def test_read_frame_from_numeric_ocr():
    tracker = UltimateMeterTracker()
    tokens = [OCRToken("88%", 0.99, 10, 10, 30, 20)]
    reading = tracker.read_frame(make_frame(3.0), tokens=tokens)

    assert reading is not None
    assert reading.charge_percent == 88.0
    assert reading.ready is False
    assert reading.method == "ocr"
    assert reading.confidence == 0.99


def test_read_frame_ready_flash():
    tracker = UltimateMeterTracker()
    tokens = [OCRToken("READY", 0.9, 10, 10, 40, 20)]
    reading = tracker.read_frame(make_frame(9.0), tokens=tokens)

    assert reading is not None
    assert reading.charge_percent == 100.0
    assert reading.ready is True
    assert reading.method == "ready_flash"


def test_gauge_fill_full_and_empty():
    tracker = UltimateMeterTracker()
    bright = (255, 215, 0)

    all_bright = make_frame(
        1.0, pixels=[((x, y), bright) for x in range(80) for y in range(50)]
    )
    assert tracker.estimate_gauge_fill(all_bright) == 100.0

    empty = make_frame(2.0)
    assert tracker.estimate_gauge_fill(empty) is None


def test_gauge_fill_partial_ring():
    tracker = UltimateMeterTracker(
        config=UltimateMeterConfig(gauge_ring_radius=10, gauge_ring_samples=8)
    )
    points = ring_points(radius=10, samples=8)
    lit = [(point, (255, 215, 0)) for point in points[:4]]
    frame = make_frame(4.0, pixels=lit)

    assert tracker.estimate_gauge_fill(frame) == 50.0


def test_detect_casts_from_sharp_drain():
    tracker = UltimateMeterTracker()
    readings = [
        UltimateReading(timestamp=10.0, charge_percent=100.0, ready=True, method="ocr"),
        UltimateReading(timestamp=14.0, charge_percent=20.0, method="ocr"),
    ]

    casts = tracker.detect_casts(readings)
    assert len(casts) == 1
    assert casts[0].timestamp == 14.0
    assert casts[0].charge_before == 100.0
    assert casts[0].charge_after == 20.0


def test_detect_casts_requires_charged_start_and_debounce():
    tracker = UltimateMeterTracker()
    low_start = [
        UltimateReading(timestamp=1.0, charge_percent=60.0, method="ocr"),
        UltimateReading(timestamp=2.0, charge_percent=10.0, method="ocr"),
    ]
    assert tracker.detect_casts(low_start) == []

    quick_second = [
        UltimateReading(timestamp=10.0, charge_percent=100.0, method="ocr"),
        UltimateReading(timestamp=11.0, charge_percent=0.0, method="ocr"),
        UltimateReading(timestamp=12.0, charge_percent=100.0, method="ocr"),
        UltimateReading(timestamp=13.0, charge_percent=0.0, method="ocr"),
    ]
    casts = tracker.detect_casts(quick_second)
    assert len(casts) == 1
    assert casts[0].timestamp == 11.0


def test_correlate_casts_with_kills():
    tracker = UltimateMeterTracker(
        config=UltimateMeterConfig(correlation_window_seconds=8.0)
    )
    casts = [
        tracker.detect_casts(
            [
                UltimateReading(timestamp=10.0, charge_percent=100.0, method="ocr"),
                UltimateReading(timestamp=11.0, charge_percent=0.0, method="ocr"),
            ]
        )[0]
    ]

    correlated = tracker.correlate_with_kills(casts, [12.0, 14.0, 30.0])
    assert correlated[0].kills_within_window == 2
    assert correlated[0].followed_by_multi_kill is True
    assert correlated[0].seconds_to_kill == 1.0


def test_track_window_builds_readings_and_casts():
    reader = FakeOCR(
        {
            10.0: [OCRToken("100%", 0.99, 10, 10, 30, 20)],
            11.0: [OCRToken("0%", 0.99, 10, 10, 30, 20)],
        }
    )
    tracker = UltimateMeterTracker(ocr_reader=reader)
    frames = [make_frame(10.0), make_frame(11.0)]
    window = WindowROIExtractionResult(
        window_start=9.0,
        window_end=13.0,
        window_duration=4.0,
        frames_by_roi={"ultimate_meter": frames},
        total_frames=2,
    )

    tracking = tracker.track_window(window)
    assert tracking is not None
    assert len(tracking.readings) == 2
    assert tracking.peak_charge == 100.0
    assert tracking.ready_detected is True
    assert len(tracking.casts) == 1
    assert tracking.casts[0].timestamp == 11.0
