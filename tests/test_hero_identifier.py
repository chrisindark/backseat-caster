"""Automated tests for hero portrait and ability icon template matching."""

from pathlib import Path

import numpy as np
from PIL import Image

from app.services.highlight.hero_identifier import (
    AbilityTracker,
    HeroIdentifier,
    HeroIdentifierConfig,
    TemplateLibrary,
    locate_best_match,
)
from app.services.highlight.roi_extractor import ROIFrame, WindowROIExtractionResult

GAME = "marvel_rivals"


def template_path(root: Path, kind: str, name: str) -> Path:
    directory = root / GAME / kind
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.png"


def save_noise_template(
    root: Path, kind: str, name: str, seed: int, size: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    Image.fromarray(array, "RGB").save(template_path(root, kind, name))
    return array


def frame_from_array(timestamp: float, array: np.ndarray, roi_name: str) -> ROIFrame:
    return ROIFrame(
        timestamp=timestamp,
        roi_name=roi_name,
        width=int(array.shape[1]),
        height=int(array.shape[0]),
        raw_rgb=array.astype(np.uint8).tobytes(),
    )


def make_ability_frame(
    timestamp: float,
    icon: np.ndarray,
    grey: bool = False,
    x: int = 12,
    y: int = 10,
    width: int = 90,
    height: int = 70,
) -> ROIFrame:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    if grey:
        luminance = (icon.astype(np.float32) @ np.array([0.299, 0.587, 0.114])).astype(
            np.uint8
        )
        patch = np.stack([luminance] * 3, axis=-1)
    else:
        patch = icon
    icon_height, icon_width = patch.shape[:2]
    canvas[y : y + icon_height, x : x + icon_width] = patch
    return frame_from_array(timestamp, canvas, "ability_row")


def test_identify_hero_from_templates(tmp_path):
    spider = save_noise_template(tmp_path, "heroes", "spiderman", seed=1, size=48)
    save_noise_template(tmp_path, "heroes", "hela", seed=2, size=48)

    identifier = HeroIdentifier(
        config=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME)
    )
    match = identifier.identify(frame_from_array(4.0, spider, "hero_portrait"))

    assert match is not None
    assert match.hero == "spiderman"
    assert match.confidence > 0.99
    assert match.template_path is not None


def test_identify_returns_none_without_templates(tmp_path):
    identifier = HeroIdentifier(
        config=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME)
    )
    rng = np.random.default_rng(3)
    frame = frame_from_array(
        1.0, rng.integers(0, 256, (32, 32, 3), dtype=np.uint8), "hero_portrait"
    )

    assert identifier.identify(frame) is None


def test_template_library_lists_kinds(tmp_path):
    save_noise_template(tmp_path, "heroes", "spiderman", seed=4, size=16)
    save_noise_template(tmp_path, "abilities", "web-swing", seed=5, size=16)

    library = TemplateLibrary(templates_dir=tmp_path, game=GAME)
    assert list(library.heroes()) == ["spiderman"]
    assert list(library.abilities()) == ["web-swing"]


def test_locate_best_match_finds_offset(tmp_path):
    rng = np.random.default_rng(6)
    template = rng.integers(0, 256, (24, 24, 3), dtype=np.uint8)
    canvas = np.zeros((70, 90, 3), dtype=np.uint8)
    canvas[17 : 17 + 24, 31 : 31 + 24] = template

    image_gray = canvas.astype(np.float32) @ np.array([0.299, 0.587, 0.114])
    template_gray = template.astype(np.float32) @ np.array([0.299, 0.587, 0.114])

    score, x, y = locate_best_match(image_gray, template_gray)
    assert score > 0.99
    assert (x, y) == (31, 17)


def test_ability_tracker_detects_cooldown_to_ready_activation(tmp_path):
    icon = save_noise_template(tmp_path, "abilities", "web-swing", seed=7, size=24)

    frames = [
        make_ability_frame(1.0, icon, grey=True),
        make_ability_frame(3.0, icon, grey=False),
    ]
    window = WindowROIExtractionResult(
        window_start=0.0,
        window_end=5.0,
        window_duration=5.0,
        frames_by_roi={"ability_row": frames},
        total_frames=2,
    )

    tracker = AbilityTracker(
        config=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME)
    )
    activations = tracker.track_window(window)

    assert len(activations) == 1
    assert activations[0].ability == "web-swing"
    assert activations[0].timestamp == 3.0
    assert activations[0].was_on_cooldown is True


def test_ability_tracker_ignores_always_ready_icons(tmp_path):
    icon = save_noise_template(tmp_path, "abilities", "web-swing", seed=8, size=24)
    frames = [
        make_ability_frame(1.0, icon, grey=False),
        make_ability_frame(2.0, icon, grey=False),
    ]
    window = WindowROIExtractionResult(
        window_start=0.0,
        window_end=3.0,
        window_duration=3.0,
        frames_by_roi={"ability_row": frames},
        total_frames=2,
    )

    tracker = AbilityTracker(
        config=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME)
    )
    assert tracker.track_window(window) == []


def test_ability_tracker_without_templates_is_noop(tmp_path):
    icon = save_noise_template(tmp_path, "heroes", "spiderman", seed=9, size=16)
    window = WindowROIExtractionResult(
        window_start=0.0,
        window_end=3.0,
        window_duration=3.0,
        frames_by_roi={"ability_row": [make_ability_frame(1.0, icon)]},
        total_frames=1,
    )

    tracker = AbilityTracker(
        config=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME)
    )
    assert tracker.track_window(window) == []
