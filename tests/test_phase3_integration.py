"""Integration tests for Phase 3 deep visual extraction and scoring."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.services.highlight.audio_scanner import (
    AudioCandidateWindow,
    AudioScanResult,
)
from app.services.highlight.cluster_engine import ClusterConfig, ClusterEngine
from app.services.highlight.deep_visuals import (
    DeepVisualConfig,
    DeepVisualResult,
    evaluate_deep_visuals,
)
from app.services.highlight.detectors import MarvelRivalsDetector
from app.services.highlight.hero_identifier import (
    AbilityActivation,
    HeroIdentifierConfig,
    HeroMatch,
)
from app.services.highlight.killfeed import (
    BatchKillfeedResult,
    KillfeedConfig,
    KillfeedRow,
    KillfeedSequence,
)
from app.services.highlight.ocr import OCRToken
from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)
from app.services.highlight.ultimate_meter import (
    BatchUltimateResult,
    UltimateCast,
    UltimateMeterConfig,
)
from app.services.highlight.visual_matcher import (
    BatchVisualMatchResult,
    VisualDetectionEvent,
    WindowVisualMatchResult,
)

GAME = "marvel_rivals"
BLUE = (40, 120, 240)
RED = (240, 30, 30)


class FakeOCR:
    """OCR stub keyed by (roi_name, timestamp)."""

    def __init__(self, mapping: dict[tuple[str, float], list[OCRToken]]):
        self.mapping = mapping

    def read(self, frame: ROIFrame) -> list[OCRToken]:
        return self.mapping.get((frame.roi_name, round(frame.timestamp, 3)), [])


def token(
    text: str, left: float, top: float, width: float = 110.0, height: float = 20.0
):
    return OCRToken(
        text=text, confidence=0.95, left=left, top=top, width=width, height=height
    )


def killfeed_frame(timestamp: float) -> ROIFrame:
    image = Image.new("RGB", (480, 220), (15, 15, 15))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 240, 220], fill=BLUE)
    draw.rectangle([240, 0, 480, 220], fill=RED)
    return ROIFrame(
        timestamp=timestamp,
        roi_name="kill_feed",
        width=480,
        height=220,
        raw_rgb=image.tobytes(),
    )


def meter_frame(timestamp: float) -> ROIFrame:
    array = np.zeros((50, 80, 3), dtype=np.uint8)
    return ROIFrame(
        timestamp=timestamp,
        roi_name="ultimate_meter",
        width=80,
        height=50,
        raw_rgb=array.tobytes(),
    )


def icon_frame(
    timestamp: float,
    icon: np.ndarray,
    roi_name: str,
    grey: bool = False,
    width: int = 90,
    height: int = 70,
    x: int = 12,
    y: int = 10,
) -> ROIFrame:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    if grey:
        luminance = (icon.astype(np.float32) @ np.array([0.299, 0.587, 0.114])).astype(
            np.uint8
        )
        patch = np.stack([luminance] * 3, axis=-1)
    else:
        patch = icon
    patch_height, patch_width = patch.shape[:2]
    canvas[y : y + patch_height, x : x + patch_width] = patch
    return ROIFrame(
        timestamp=timestamp,
        roi_name=roi_name,
        width=width,
        height=height,
        raw_rgb=canvas.tobytes(),
    )


def save_template(root: Path, kind: str, name: str, seed: int, size: int) -> np.ndarray:
    directory = root / GAME / kind
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    Image.fromarray(array, "RGB").save(directory / f"{name}.png")
    return array


def build_phase3_batch(
    tmp_path: Path,
) -> tuple[BatchROIExtractionResult, FakeOCR, np.ndarray]:
    hero = save_template(tmp_path, "heroes", "spiderman", seed=11, size=40)
    ability = save_template(tmp_path, "abilities", "web-swing", seed=12, size=24)

    kill_frames = [killfeed_frame(10.0), killfeed_frame(12.0)]
    ultimate_frames = [meter_frame(9.0), meter_frame(9.5)]
    hero_frames = [
        icon_frame(1.0, hero, "hero_portrait", width=40, height=40, x=0, y=0),
        icon_frame(2.0, hero, "hero_portrait", width=40, height=40, x=0, y=0),
    ]
    ability_frames = [
        icon_frame(1.0, ability, "ability_row", grey=True),
        icon_frame(2.0, ability, "ability_row", grey=False),
    ]

    window = WindowROIExtractionResult(
        window_start=0.0,
        window_end=20.0,
        window_duration=20.0,
        frames_by_roi={
            "kill_feed": kill_frames,
            "ultimate_meter": ultimate_frames,
            "hero_portrait": hero_frames,
            "ability_row": ability_frames,
        },
        total_frames=sum(
            len(value)
            for value in (
                kill_frames,
                ultimate_frames,
                hero_frames,
                ability_frames,
            )
        ),
    )
    batch = BatchROIExtractionResult(
        file_path="synthetic_vod.mp4",
        source_width=1920,
        source_height=1080,
        fps=1.5,
        windows_extracted=[window],
        total_frames=window.total_frames,
    )

    reader = FakeOCR(
        {
            ("kill_feed", 10.0): [
                token("SPIDERMAN", 20, 40),
                token("HELA", 300, 40),
            ],
            ("kill_feed", 12.0): [
                token("SPIDERMAN", 20, 40),
                token("LOKI", 300, 40),
            ],
            ("ultimate_meter", 9.0): [token("100%", 10, 10, 30)],
            ("ultimate_meter", 9.5): [token("0%", 10, 10, 30)],
        }
    )
    return batch, reader, hero


def test_evaluate_deep_visuals_produces_all_signals(tmp_path):
    batch, reader, _hero = build_phase3_batch(tmp_path)
    config = DeepVisualConfig(
        killfeed=KillfeedConfig(player_names=["SPIDERMAN"]),
        ultimate=UltimateMeterConfig(correlation_window_seconds=8.0),
        hero=HeroIdentifierConfig(templates_dir=str(tmp_path), game=GAME),
    )

    result = evaluate_deep_visuals(batch, config=config, ocr_reader=reader)

    assert len(result.killfeed.windows) == 1
    sequence = result.killfeed.windows[0]
    assert sequence.multi_kill_label == "DOUBLE KO"
    assert sequence.kill_count == 2
    assert sequence.attribution_method == "name_match"

    assert result.kill_timestamps == [10.0, 12.0]
    assert len(result.ultimate.casts) == 1
    cast = result.ultimate.casts[0]
    assert cast.timestamp == 9.5
    assert cast.kills_within_window == 2
    assert cast.followed_by_multi_kill is True

    assert result.hero is not None
    assert result.hero.hero == "spiderman"
    assert len(result.abilities) == 1
    assert result.abilities[0].ability == "web-swing"


def test_cluster_engine_consumes_phase3_signals(tmp_path):
    sequence = KillfeedSequence(
        window_start=5.0,
        window_end=20.0,
        rows=[
            KillfeedRow(
                timestamp=10.0,
                actor="Spider-Man",
                victim="Hela",
                actor_team="friendly",
                actor_is_player=True,
            ),
            KillfeedRow(
                timestamp=12.0,
                actor="Spider-Man",
                victim="Loki",
                actor_team="friendly",
                actor_is_player=True,
            ),
        ],
        attributed_actor="Spider-Man",
        attribution_method="name_match",
        kill_count=2,
        chain_start_seconds=10.0,
        chain_end_seconds=12.0,
        multi_kill_label="DOUBLE KO",
        confidence=0.9,
    )
    cast = UltimateCast(
        timestamp=9.5,
        charge_before=100.0,
        charge_after=0.0,
        followed_by_multi_kill=True,
        kills_within_window=2,
        seconds_to_kill=0.5,
    )

    engine = ClusterEngine(config=ClusterConfig(generate_thumbnails=False))
    candidates = engine.assemble_candidates(
        video_id="vid_phase3",
        media_path=tmp_path / "synthetic.mp4",
        visual_matches=None,
        audio_windows=None,
        total_duration=120.0,
        killfeed_sequences=[sequence],
        ultimate_casts=[cast],
        hero_name="Spider-Man",
        abilities_used=["web-swing"],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.details.hero_name == "Spider-Man"
    assert candidate.details.multi_kill_chain == 2
    assert candidate.details.killfeed_chain is not None
    assert candidate.details.killfeed_chain.kill_count == 2
    assert len(candidate.details.ultimate_casts) == 1
    assert candidate.details.abilities_used == ["web-swing"]
    assert candidate.details.has_ultimate is True
    assert candidate.details.kill_count == 2
    assert "Spider-Man" in candidate.suggested_title
    assert candidate.score >= 0.7


def test_marvel_rivals_detector_runs_phase3_stage(tmp_path, monkeypatch):
    fake_vod = tmp_path / "vod.mp4"
    fake_vod.write_bytes(b"synthetic")

    scan = AudioScanResult(
        file_path=str(fake_vod),
        duration_seconds=120.0,
        has_audio=True,
        silence_threshold_lufs=-30.0,
        excitement_threshold_lufs=-16.0,
        total_buckets=100,
        candidate_windows=[
            AudioCandidateWindow(
                start_seconds=5.0,
                end_seconds=20.0,
                duration_seconds=15.0,
                peak_lufs=-9.0,
                mean_lufs=-13.0,
                peak_true_peak_db=-1.0,
                score=0.9,
                bucket_count=20,
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.highlight.service.scan_audio_energy", lambda media_path: scan
    )

    roi_batch = BatchROIExtractionResult(
        file_path=str(fake_vod),
        source_width=1920,
        source_height=1080,
        fps=1.5,
        windows_extracted=[],
        total_frames=0,
    )
    captured: dict[str, list[str]] = {}

    def fake_extract(
        media_path,
        windows,
        roi_names=None,
        fps=None,
        config=None,
        progress_callback=None,
    ):
        captured["roi_names"] = list(roi_names or [])
        return roi_batch

    monkeypatch.setattr(
        "app.services.highlight.service.extract_candidate_windows_rois", fake_extract
    )

    visual = BatchVisualMatchResult(
        file_path=str(fake_vod),
        windows_matched=[
            WindowVisualMatchResult(
                window_start=5.0,
                window_end=20.0,
                window_duration=15.0,
                events=[
                    VisualDetectionEvent(
                        timestamp=11.0,
                        roi_name="center_ko",
                        event_type="triple_ko",
                        label="TRIPLE KO",
                        confidence=0.9,
                        kill_count=3,
                        score_weight=0.80,
                    )
                ],
            )
        ],
        total_events_detected=1,
    )
    monkeypatch.setattr(
        "app.services.highlight.service.evaluate_batch_visuals",
        lambda batch: visual,
    )

    sequence = KillfeedSequence(
        window_start=5.0,
        window_end=20.0,
        rows=[],
        attributed_actor="Spider-Man",
        attribution_method="name_match",
        kill_count=3,
        chain_start_seconds=10.0,
        chain_end_seconds=12.0,
        multi_kill_label="TRIPLE KO",
        confidence=0.9,
    )
    deep = DeepVisualResult(
        file_path=str(fake_vod),
        killfeed=BatchKillfeedResult(file_path=str(fake_vod), windows=[sequence]),
        ultimate=BatchUltimateResult(
            file_path=str(fake_vod),
            casts=[
                UltimateCast(
                    timestamp=9.5,
                    charge_before=100.0,
                    charge_after=0.0,
                    followed_by_multi_kill=True,
                    kills_within_window=3,
                )
            ],
        ),
        hero=HeroMatch(hero="Spider-Man", confidence=0.92),
        abilities=[
            AbilityActivation(timestamp=10.0, ability="web-swing", confidence=0.9)
        ],
    )
    monkeypatch.setattr(
        "app.services.highlight.detectors.marvel_rivals.evaluate_deep_visuals",
        lambda *args, **kwargs: deep,
    )
    monkeypatch.setattr(
        "app.services.highlight.cluster_engine.extract_thumbnail_frame",
        lambda *args, **kwargs: None,
    )

    detector = MarvelRivalsDetector()
    candidates = detector.detect(
        video_id="vod_phase3",
        media_path=fake_vod,
        min_score=0.5,
    )

    assert {"kill_feed", "ultimate_meter", "hero_portrait", "ability_row"} <= set(
        captured["roi_names"]
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.details.hero_name == "Spider-Man"
    assert candidate.details.multi_kill_chain == 3
    assert candidate.details.killfeed_chain is not None
    assert candidate.details.abilities_used == ["web-swing"]
    assert candidate.details.ultimate_casts[0].followed_by_multi_kill is True
    assert "Spider-Man" in candidate.suggested_title
