"""Phase 3 deep visual extraction orchestrator.

Runs the three deep-HUD stages over the same ROI batch already extracted for
Stage 3, sharing one OCR engine:

- Killfeed row parsing, team colour inference and player multi-kill chains.
- Ultimate meter charge/ready/cast tracking with kill payoff correlation.
- Hero portrait identification and ability cooldown -> ready detection.

Every stage is optional and degrades to a no-op when its inputs (OCR engine,
HUD region, template folder) are unavailable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from pydantic import BaseModel, Field

from app.services.highlight.hero_identifier import (
    AbilityActivation,
    AbilityTracker,
    HeroIdentifier,
    HeroIdentifierConfig,
    HeroMatch,
)
from app.services.highlight.killfeed import (
    BatchKillfeedResult,
    KillfeedConfig,
    KillfeedParser,
)
from app.services.highlight.ocr import OCRReader
from app.services.highlight.roi_extractor import BatchROIExtractionResult
from app.services.highlight.ultimate_meter import (
    BatchUltimateResult,
    UltimateMeterConfig,
    UltimateMeterTracker,
)

logger = logging.getLogger(__name__)


class DeepVisualConfig(BaseModel):
    """Feature switches and per-stage tuning for deep HUD extraction."""

    enable_killfeed: bool = Field(
        default=True, description="Parse killfeed rows and multi-kill chains"
    )
    enable_ultimate: bool = Field(
        default=True, description="Track ultimate charge, readiness and casts"
    )
    enable_hero_identification: bool = Field(
        default=True, description="Match the hero portrait against templates"
    )
    enable_ability_tracking: bool = Field(
        default=True, description="Track ability cooldown -> available transitions"
    )
    ocr_min_confidence: float = Field(
        default=0.35, description="Shared OCR confidence floor for Phase 3 stages"
    )
    killfeed: KillfeedConfig = Field(default_factory=KillfeedConfig)
    ultimate: UltimateMeterConfig = Field(default_factory=UltimateMeterConfig)
    hero: HeroIdentifierConfig = Field(default_factory=HeroIdentifierConfig)


class DeepVisualResult(BaseModel):
    """Aggregated Phase 3 signals for a single video."""

    file_path: str = Field(..., description="Source media path")
    killfeed: BatchKillfeedResult = Field(
        ..., description="Killfeed parsing results across windows"
    )
    ultimate: BatchUltimateResult = Field(
        ..., description="Ultimate meter tracking results across windows"
    )
    hero: HeroMatch | None = Field(
        default=None, description="Best hero portrait match across the video"
    )
    abilities: list[AbilityActivation] = Field(
        default_factory=list,
        description="Ability cooldown -> available transitions across windows",
    )
    kill_timestamps: list[float] = Field(
        default_factory=list,
        description="Player/friendly elimination timestamps used for correlation",
    )
    processing_time_seconds: float = Field(
        default=0.0, description="Wall-clock deep extraction time"
    )


def _friendly_kill_timestamps(batch: BatchKillfeedResult) -> list[float]:
    """Collect elimination times plausibly credited to the player's team."""
    timestamps: set[float] = set()
    for sequence in batch.windows:
        if sequence.is_player_attributed:
            for row in sequence.rows:
                if row.action == "elimination" and not row.victim_is_player:
                    timestamps.add(round(row.timestamp, 3))
            continue

        for row in sequence.rows:
            if (
                row.action == "elimination"
                and row.actor_team == "friendly"
                and not row.victim_is_player
            ):
                timestamps.add(round(row.timestamp, 3))
    return sorted(timestamps)


def evaluate_deep_visuals(
    batch_rois: BatchROIExtractionResult,
    config: DeepVisualConfig | None = None,
    ocr_reader: OCRReader | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> DeepVisualResult:
    """Run all enabled Phase 3 stages over an extracted ROI batch."""
    cfg = config or DeepVisualConfig()
    start = time.perf_counter()
    reader = ocr_reader or OCRReader(min_confidence=cfg.ocr_min_confidence)

    # 1. Killfeed parsing and chain attribution.
    killfeed_result = BatchKillfeedResult(file_path=batch_rois.file_path)
    if cfg.enable_killfeed:
        if progress_callback:
            progress_callback(25.0, "Parsing killfeed rows and multi-kill chains...")
        killfeed_result = KillfeedParser(
            config=cfg.killfeed, ocr_reader=reader
        ).evaluate_batch(batch_rois)

    kill_timestamps = _friendly_kill_timestamps(killfeed_result)

    # 2. Ultimate charge / readiness / cast tracking plus payoff correlation.
    ultimate_result = BatchUltimateResult(file_path=batch_rois.file_path)
    if cfg.enable_ultimate:
        if progress_callback:
            progress_callback(55.0, "Tracking ultimate charge and cast payoffs...")
        ultimate_result = UltimateMeterTracker(
            config=cfg.ultimate, ocr_reader=reader
        ).evaluate_batch(batch_rois, kill_timestamps=kill_timestamps)

    windows = batch_rois.windows_extracted

    # 3. Hero identification.
    hero_match: HeroMatch | None = None
    if cfg.enable_hero_identification:
        if progress_callback:
            progress_callback(80.0, "Identifying played hero from HUD portrait...")
        identifier = HeroIdentifier(config=cfg.hero)
        for window in windows:
            match = identifier.identify_window(window)
            if match and (
                hero_match is None or match.confidence > hero_match.confidence
            ):
                hero_match = match

    # 4. Ability cooldown -> available transitions.
    abilities: list[AbilityActivation] = []
    if cfg.enable_ability_tracking:
        tracker = AbilityTracker(config=cfg.hero)
        for window in windows:
            abilities.extend(tracker.track_window(window))
        abilities.sort(key=lambda activation: activation.timestamp)

    elapsed = round(time.perf_counter() - start, 3)
    logger.info(
        "Deep visual extraction for %s: %d killfeed sequences, %d ult casts, "
        "hero=%s, %d ability activations in %.2fs",
        batch_rois.file_path,
        len(killfeed_result.windows),
        len(ultimate_result.casts),
        hero_match.hero if hero_match else "unknown",
        len(abilities),
        elapsed,
    )

    return DeepVisualResult(
        file_path=batch_rois.file_path,
        killfeed=killfeed_result,
        ultimate=ultimate_result,
        hero=hero_match,
        abilities=abilities,
        kill_timestamps=kill_timestamps,
        processing_time_seconds=elapsed,
    )
