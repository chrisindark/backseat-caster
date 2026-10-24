"""Structured Marvel Rivals killfeed parsing and player multi-kill chain tracking.

Stage 3 matches generic elimination banners (``TRIPLE KO``, ``TEAM WIPE``).
This module goes one level deeper: it reads the top-right killfeed ROI row by
row, splitting each row into actor / action / victim using OCR bounding-box
geometry, infers friendly (blue) versus enemy (red) combatants from row pixel
colour, and chains rapid eliminations by the same actor into multi-kill
sequences attributed to the played character.

Attribution is deliberately conservative:

- ``name_match``  — a configured ``player_names`` entry appears in the actor.
- ``friendly_chain`` — no player names configured, but the actor is a
  consistently friendly (blue) combatant across the chain.
- ``none`` — no usable attribution; the sequence is retained for context but
  never converted into a highlight trigger on its own.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel, Field

from app.services.highlight.ocr import OCRReader, OCRToken
from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)
from app.services.highlight.visual_matcher import VisualDetectionEvent

logger = logging.getLogger(__name__)

# Action keywords emitted by OCR inside killfeed rows.
ACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "assist",
        re.compile(r"\b(ASSIST(?:ED)?|ASSISTANCE|HELPED)\b", re.IGNORECASE),
    ),
    (
        "knock",
        re.compile(
            r"\b(KNOCKED(?:\s*OUT)?|KNOCKOUT|KNOCKDOWN|DOWNED|STAGGERED)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "elimination",
        re.compile(
            r"\b(ELIMINATED|ELIMINATION|KILLED|KILL|K[O0]'?D|DEFEATED|FINISHED|SLAIN)\b",
            re.IGNORECASE,
        ),
    ),
]

ACTION_PATTERN_BY_NAME: dict[str, re.Pattern[str]] = dict(ACTION_PATTERNS)

# Player-involvement markers that sometimes appear in the feed.
PLAYER_MARKERS: tuple[str, ...] = ("YOU", "SELF")

# Noise tokens that must never become a combatant name.
NOISE_PATTERN: re.Pattern[str] = re.compile(
    r"^(\+?\d+|\d+\s*%|KILL\s*FEED|FEED|CHAT|ALL|TEAM)$",
    re.IGNORECASE,
)

# Inline "A killed B" / "A > B" single-token rows.
INLINE_KILL_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<actor>.+?)\s*(?:KILLED|ELIMINATED|DEFEATED|>|->|→|»)\s*(?P<victim>.+)$",
    re.IGNORECASE,
)

MULTI_KILL_LABELS: dict[int, str] = {
    2: "DOUBLE KO",
    3: "TRIPLE KO",
    4: "QUAD KO",
    5: "PENTA KO",
    6: "TEAM WIPE",
}

MULTI_KILL_EVENT_TYPES: dict[int, str] = {
    2: "double_ko",
    3: "triple_ko",
    4: "quad_ko",
    5: "penta_ko",
    6: "team_wipe",
}

MULTI_KILL_SCORE_WEIGHTS: dict[int, float] = {
    2: 0.70,
    3: 0.80,
    4: 0.90,
    5: 0.95,
    6: 1.00,
}


def multi_kill_label(kill_count: int) -> str | None:
    """Return the banner label for a rapid kill count (2+)."""
    if kill_count < 2:
        return None
    return MULTI_KILL_LABELS.get(kill_count, "TEAM WIPE")


def multi_kill_event_type(kill_count: int) -> str | None:
    """Return the Stage 3 event type matching a rapid kill count (2+)."""
    if kill_count < 2:
        return None
    return MULTI_KILL_EVENT_TYPES.get(kill_count, "team_wipe")


def _normalize_name(text: str) -> str:
    """Normalize OCR text for name comparison (alphanumeric lowercase)."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _clean_name(text: str) -> str:
    """Trim punctuation noise that OCR attaches to combatant names."""
    return text.strip(" \t:|•·-–—[]()<>\"'").strip()


class KillfeedConfig(BaseModel):
    """Configuration for killfeed row parsing and chain attribution."""

    player_names: list[str] = Field(
        default_factory=list,
        description="Known player/hero identifiers used for direct attribution",
    )
    ability_keywords: list[str] = Field(
        default_factory=list,
        description="Optional ability name keywords to lift from middle OCR tokens",
    )
    min_confidence: float = Field(
        default=0.35, description="Minimum OCR confidence for a usable token"
    )
    row_y_tolerance_px: float = Field(
        default=18.0,
        description="Vertical center tolerance (pixels) when grouping tokens into rows",
    )
    min_column_gap_px: float = Field(
        default=30.0,
        description="Horizontal gap (pixels) separating actor from victim columns",
    )
    min_side_color_ratio: float = Field(
        default=0.015,
        description="Minimum team-colour pixel ratio to assign a combatant side",
    )
    friendly_rgb_range: tuple[int, int, int, int, int, int] = Field(
        default=(0, 90, 60, 180, 150, 255),
        description="Friendly/blue RGB bounds (r_min, r_max, g_min, g_max, b_min, b_max)",
    )
    enemy_rgb_range: tuple[int, int, int, int, int, int] = Field(
        default=(170, 255, 0, 90, 0, 90),
        description="Enemy/red RGB bounds (r_min, r_max, g_min, g_max, b_min, b_max)",
    )
    dedupe_seconds: float = Field(
        default=4.0,
        description="Killfeed rows persist on screen; collapse repeats inside this window",
    )
    chain_gap_seconds: float = Field(
        default=7.0,
        description="Maximum gap between two kills still considered one chain",
    )
    max_rows_per_window: int = Field(
        default=30, description="Safety cap on parsed rows per candidate window"
    )


class KillfeedRow(BaseModel):
    """Single combatant-versus-combatant killfeed row."""

    timestamp: float = Field(..., description="Timestamp the row was sampled at")
    actor: str = Field(..., description="Killer / assist actor name")
    victim: str = Field(default="", description="Victim name")
    action: str = Field(
        default="elimination",
        description="Action type: elimination, knock, or assist",
    )
    ability: str | None = Field(
        default=None, description="Weapon/ability keyword when OCR exposed one"
    )
    actor_team: str = Field(
        default="unknown", description="friendly, enemy, or unknown (from row colour)"
    )
    victim_team: str = Field(
        default="unknown", description="friendly, enemy, or unknown (from row colour)"
    )
    actor_is_player: bool = Field(
        default=False, description="True when the actor matches a player identifier"
    )
    victim_is_player: bool = Field(
        default=False, description="True when the victim matches a player identifier"
    )
    confidence: float = Field(
        default=0.0, description="Mean OCR confidence for the row"
    )
    raw_text: str = Field(default="", description="Joined OCR text for the row")


class KillfeedSequence(BaseModel):
    """Chronological killfeed rows plus the attributed rapid kill chain."""

    window_start: float = Field(..., description="Candidate window start in seconds")
    window_end: float = Field(..., description="Candidate window end in seconds")
    rows: list[KillfeedRow] = Field(
        default_factory=list, description="Deduplicated rows inside the window"
    )
    attributed_actor: str | None = Field(
        default=None, description="Actor the chain is attributed to"
    )
    attribution_method: str = Field(
        default="none", description="name_match, friendly_chain, or none"
    )
    kill_count: int = Field(
        default=0, description="Eliminations credited to the attributed actor"
    )
    death_count: int = Field(
        default=0, description="Rows where the player (or a friendly) was eliminated"
    )
    assist_count: int = Field(default=0, description="Assist rows in the window")
    chain_start_seconds: float | None = Field(
        default=None, description="First credited kill timestamp"
    )
    chain_end_seconds: float | None = Field(
        default=None, description="Last credited kill timestamp"
    )
    multi_kill_label: str | None = Field(
        default=None, description="DOUBLE KO / TRIPLE KO / ... when chained"
    )
    confidence: float = Field(
        default=0.0, description="Mean confidence of the parsed rows"
    )

    @property
    def is_player_attributed(self) -> bool:
        """True when the chain could be attributed to the creator's player."""
        return self.attribution_method != "none" and self.kill_count > 0


class BatchKillfeedResult(BaseModel):
    """Killfeed parsing results across all analysed candidate windows."""

    file_path: str = Field(..., description="Source media path")
    windows: list[KillfeedSequence] = Field(
        default_factory=list, description="Parsed sequences per candidate window"
    )
    total_rows: int = Field(default=0, description="Total rows parsed")
    processing_time_seconds: float = Field(
        default=0.0, description="Wall-clock parsing time"
    )


def _band_center(tokens: list[OCRToken]) -> float:
    return sum(token.center_y for token in tokens) / len(tokens)


def _group_into_rows(tokens: list[OCRToken], tolerance: float) -> list[list[OCRToken]]:
    """Cluster OCR tokens into killfeed rows by their vertical centers."""
    rows: list[list[OCRToken]] = []
    for token in sorted(tokens, key=lambda t: (t.center_y, t.left)):
        for row in rows:
            if abs(token.center_y - _band_center(row)) <= tolerance:
                row.append(token)
                break
        else:
            rows.append([token])

    for row in rows:
        row.sort(key=lambda t: t.left)
    rows.sort(key=lambda row: _band_center(row))
    return rows


def _match_action(text: str) -> str | None:
    for action, pattern in ACTION_PATTERNS:
        if pattern.search(text):
            return action
    return None


def _is_noise(text: str) -> bool:
    return bool(NOISE_PATTERN.match(text.strip()))


def _match_ability(text: str, keywords: list[str]) -> str | None:
    lowered = text.lower()
    for keyword in keywords:
        if keyword and keyword.lower() in lowered:
            return keyword
    return None


class KillfeedParser:
    """Killfeed row parser and rapid multi-kill chain builder."""

    def __init__(
        self,
        config: KillfeedConfig | None = None,
        ocr_reader: OCRReader | None = None,
    ) -> None:
        self.config = config or KillfeedConfig()
        self._ocr = ocr_reader or OCRReader(min_confidence=self.config.min_confidence)

    # ------------------------------------------------------------------ rows
    def _team_side(
        self,
        frame: ROIFrame,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> str:
        """Infer friendly/enemy from the dominant team colour inside a box."""
        x0 = max(0, min(frame.width - 1, int(left)))
        y0 = max(0, min(frame.height - 1, int(top)))
        x1 = max(x0 + 1, min(frame.width, int(right)))
        y1 = max(y0 + 1, min(frame.height, int(bottom)))
        area = (x1 - x0) * (y1 - y0)
        if area <= 0:
            return "unknown"

        pixels = np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
            (frame.height, frame.width, 3)
        )[y0:y1, x0:x1]
        red_channel, green_channel, blue_channel = (
            pixels[:, :, 0],
            pixels[:, :, 1],
            pixels[:, :, 2],
        )

        def _ratio(bounds: tuple[int, int, int, int, int, int]) -> float:
            r_min, r_max, g_min, g_max, b_min, b_max = bounds
            mask = (
                (red_channel >= r_min)
                & (red_channel <= r_max)
                & (green_channel >= g_min)
                & (green_channel <= g_max)
                & (blue_channel >= b_min)
                & (blue_channel <= b_max)
            )
            return float(np.count_nonzero(mask)) / area

        blue_ratio = _ratio(self.config.friendly_rgb_range)
        red_ratio = _ratio(self.config.enemy_rgb_range)

        threshold = self.config.min_side_color_ratio
        if blue_ratio >= threshold and blue_ratio >= red_ratio * 1.3:
            return "friendly"
        if red_ratio >= threshold and red_ratio >= blue_ratio * 1.3:
            return "enemy"
        return "unknown"

    def _is_player(self, name: str) -> bool:
        normalized = _normalize_name(name)
        if not normalized:
            return False
        for marker in PLAYER_MARKERS:
            if normalized == _normalize_name(marker):
                return True
        for player in self.config.player_names:
            target = _normalize_name(player)
            if target and len(target) >= 3 and target in normalized:
                return True
        return False

    def _split_row(
        self, tokens: list[OCRToken]
    ) -> tuple[str, str, str, str | None] | None:
        """Split a row's tokens into (actor, victim, action, ability)."""
        action = "elimination"
        ability: str | None = None
        cleaned: list[OCRToken] = []

        for token in tokens:
            text = token.text.strip()
            if not text or _is_noise(text):
                continue

            detected_action = _match_action(text)
            if detected_action:
                action = detected_action
                # Keep any name text surrounding the keyword.
                pattern = ACTION_PATTERN_BY_NAME[detected_action]
                stripped = pattern.sub(" ", text).strip()
                if not stripped or _is_noise(stripped):
                    continue
                cleaned.append(
                    OCRToken(
                        text=stripped,
                        confidence=token.confidence,
                        left=token.left,
                        top=token.top,
                        width=token.width,
                        height=token.height,
                    )
                )
                continue

            matched_ability = _match_ability(text, self.config.ability_keywords)
            if matched_ability and not ability:
                ability = matched_ability
                continue

            cleaned.append(token)

        if not cleaned:
            return None

        if len(cleaned) == 1:
            inline = INLINE_KILL_PATTERN.match(cleaned[0].text)
            if inline:
                actor = _clean_name(inline.group("actor"))
                victim = _clean_name(inline.group("victim"))
                if actor and victim:
                    return actor, victim, action, ability
            return None

        # Split on the widest horizontal gap (actor column vs victim column).
        gaps = [
            (cleaned[i + 1].left - cleaned[i].right, i) for i in range(len(cleaned) - 1)
        ]
        widest_gap, split_index = max(gaps, key=lambda item: item[0])
        if widest_gap < self.config.min_column_gap_px:
            # Likely one multi-word name; not a usable combat row.
            return None

        actor_tokens = cleaned[: split_index + 1]
        victim_tokens = cleaned[split_index + 1 :]

        actor = _clean_name(" ".join(t.text for t in actor_tokens))
        victim = _clean_name(" ".join(t.text for t in victim_tokens))
        if not actor or not victim:
            return None

        if len(victim_tokens) >= 2:
            # Middle tokens in a three-column row describe the weapon/ability.
            victim = _clean_name(victim_tokens[-1].text)
            middle = _clean_name(" ".join(t.text for t in victim_tokens[:-1]))
            if middle and not ability:
                ability = middle

        return actor, victim, action, ability

    def parse_frame(
        self, frame: ROIFrame, tokens: list[OCRToken] | None = None
    ) -> list[KillfeedRow]:
        """Parse all killfeed rows visible in a single ROI frame."""
        frame_tokens = tokens if tokens is not None else self._ocr.read(frame)
        if not frame_tokens:
            return []

        rows: list[KillfeedRow] = []
        for row_tokens in _group_into_rows(
            frame_tokens, self.config.row_y_tolerance_px
        ):
            parsed = self._split_row(row_tokens)
            if parsed is None:
                continue
            actor, victim, action, ability = parsed

            left = min(token.left for token in row_tokens)
            right = max(token.right for token in row_tokens)
            top = min(token.top for token in row_tokens)
            bottom = max(token.bottom for token in row_tokens)
            midpoint = (left + right) / 2.0

            rows.append(
                KillfeedRow(
                    timestamp=round(frame.timestamp, 3),
                    actor=actor,
                    victim=victim,
                    action=action,
                    ability=ability,
                    actor_team=self._team_side(frame, left, top, midpoint, bottom),
                    victim_team=self._team_side(frame, midpoint, top, right, bottom),
                    actor_is_player=self._is_player(actor),
                    victim_is_player=self._is_player(victim),
                    confidence=round(
                        sum(token.confidence for token in row_tokens) / len(row_tokens),
                        3,
                    ),
                    raw_text=" ".join(token.text for token in row_tokens),
                )
            )
        return rows

    # -------------------------------------------------------------- sequence
    def _dedupe_rows(self, rows: list[KillfeedRow]) -> list[KillfeedRow]:
        """Collapse repeated killfeed rows that persist across sampled frames."""
        kept: list[KillfeedRow] = []
        for row in sorted(rows, key=lambda r: r.timestamp):
            duplicate = next(
                (
                    prev
                    for prev in kept
                    if _normalize_name(prev.actor) == _normalize_name(row.actor)
                    and _normalize_name(prev.victim) == _normalize_name(row.victim)
                    and abs(row.timestamp - prev.timestamp)
                    <= self.config.dedupe_seconds
                ),
                None,
            )
            if duplicate is None:
                kept.append(row)
            elif row.confidence > duplicate.confidence:
                duplicate.confidence = row.confidence
        return kept[: self.config.max_rows_per_window]

    def _build_chains(
        self, rows: list[KillfeedRow]
    ) -> dict[str, list[list[KillfeedRow]]]:
        """Group eliminations into per-actor chains separated by the chain gap."""
        chains: dict[str, list[list[KillfeedRow]]] = {}
        eliminations = [row for row in rows if row.action == "elimination"]

        for row in eliminations:
            key = _normalize_name(row.actor) or row.actor.lower()
            actor_chains = chains.setdefault(key, [])
            if actor_chains and (
                row.timestamp - actor_chains[-1][-1].timestamp
                <= self.config.chain_gap_seconds
            ):
                actor_chains[-1].append(row)
            else:
                actor_chains.append([row])
        return chains

    def build_sequence(
        self,
        rows: list[KillfeedRow],
        window_start: float,
        window_end: float,
    ) -> KillfeedSequence | None:
        """Assemble a killfeed sequence and attribute the strongest chain."""
        if not rows:
            return None

        chains = self._build_chains(rows)
        name_attributed = [
            row for row in rows if row.actor_is_player or self._is_player(row.actor)
        ]

        attributed_actor: str | None = None
        attribution_method = "none"
        chain: list[KillfeedRow] = []

        if name_attributed:
            # Prefer the actor matching a configured player name.
            counts: dict[str, int] = {}
            for row in name_attributed:
                key = _normalize_name(row.actor) or row.actor.lower()
                counts[key] = counts.get(key, 0) + 1
            best_key = max(counts, key=lambda key: counts[key])
            attributed_actor = next(
                (
                    row.actor
                    for row in name_attributed
                    if (_normalize_name(row.actor) or row.actor.lower()) == best_key
                ),
                name_attributed[0].actor,
            )
            attribution_method = "name_match"
            actor_chains = chains.get(best_key, [])
            chain = max(actor_chains, key=len) if actor_chains else []
        elif not self.config.player_names:
            # No player identity configured: attribute the most consistent
            # friendly (blue) actor chain.
            friendly_rows = [row for row in rows if row.actor_team == "friendly"]
            if friendly_rows:
                counts = {}
                for row in friendly_rows:
                    key = _normalize_name(row.actor) or row.actor.lower()
                    counts[key] = counts.get(key, 0) + 1
                best_key = max(counts, key=lambda key: counts[key])
                actor_chains = chains.get(best_key, [])
                if actor_chains:
                    chain = max(actor_chains, key=len)
                    attributed_actor = chain[0].actor
                    attribution_method = "friendly_chain"

        if not chain and attributed_actor:
            actor_chains = chains.get(
                _normalize_name(attributed_actor) or attributed_actor.lower(), []
            )
            chain = max(actor_chains, key=len) if actor_chains else []

        kill_count = len(chain)
        kill_label = multi_kill_label(kill_count) if kill_count >= 2 else None

        death_count = sum(
            1
            for row in rows
            if row.victim_is_player
            or self._is_player(row.victim)
            or (row.victim_team == "friendly" and row.actor_team == "enemy")
        )
        assist_count = sum(1 for row in rows if row.action == "assist")

        chain_start = min((row.timestamp for row in chain), default=None)
        chain_end = max((row.timestamp for row in chain), default=None)

        return KillfeedSequence(
            window_start=round(window_start, 3),
            window_end=round(window_end, 3),
            rows=rows,
            attributed_actor=attributed_actor,
            attribution_method=attribution_method,
            kill_count=kill_count,
            death_count=death_count,
            assist_count=assist_count,
            chain_start_seconds=chain_start,
            chain_end_seconds=chain_end,
            multi_kill_label=kill_label,
            confidence=round(sum(row.confidence for row in rows) / len(rows), 3),
        )

    def evaluate_window(
        self, window_rois: WindowROIExtractionResult
    ) -> KillfeedSequence | None:
        """Parse and attribute killfeed rows for one candidate window."""
        frames = window_rois.frames_by_roi.get("kill_feed", [])
        if not frames:
            return None

        rows: list[KillfeedRow] = []
        for frame in sorted(frames, key=lambda f: f.timestamp):
            rows.extend(self.parse_frame(frame))

        rows = self._dedupe_rows(rows)
        if not rows:
            return None
        return self.build_sequence(
            rows, window_rois.window_start, window_rois.window_end
        )

    def evaluate_batch(
        self,
        batch_rois: BatchROIExtractionResult,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> BatchKillfeedResult:
        """Parse killfeed rows across every extracted candidate window."""
        start = time.perf_counter()
        sequences: list[KillfeedSequence] = []
        total_rows = 0
        windows = len(batch_rois.windows_extracted)

        for index, window in enumerate(batch_rois.windows_extracted, 1):
            if progress_callback and windows > 0:
                progress_callback(
                    round((index - 1) / windows * 100.0, 1),
                    f"Parsing killfeed sequences (window {index}/{windows})",
                )
            sequence = self.evaluate_window(window)
            if sequence:
                sequences.append(sequence)
                total_rows += len(sequence.rows)

        if progress_callback:
            progress_callback(100.0, "Killfeed sequence parsing completed")

        elapsed = round(time.perf_counter() - start, 3)
        logger.info(
            "Killfeed parsing complete for %s: %d sequences, %d rows in %.2fs.",
            batch_rois.file_path,
            len(sequences),
            total_rows,
            elapsed,
        )
        return BatchKillfeedResult(
            file_path=batch_rois.file_path,
            windows=sequences,
            total_rows=total_rows,
            processing_time_seconds=elapsed,
        )


def killfeed_sequences_to_events(
    sequences: list[KillfeedSequence],
) -> list[VisualDetectionEvent]:
    """Convert attributing killfeed sequences into Stage 3 visual events."""
    events: list[VisualDetectionEvent] = []
    for sequence in sequences:
        if not sequence.is_player_attributed:
            continue

        kill_count = max(1, sequence.kill_count)
        event_type = multi_kill_event_type(kill_count) or "single_ko"
        label = sequence.multi_kill_label or (
            f"{kill_count} KILL CHAIN" if kill_count > 1 else "KILLFEED ELIMINATION"
        )
        weight = MULTI_KILL_SCORE_WEIGHTS.get(kill_count, 0.50)
        timestamp = sequence.chain_end_seconds or sequence.window_start

        events.append(
            VisualDetectionEvent(
                timestamp=round(timestamp, 3),
                roi_name="kill_feed",
                event_type=event_type,
                label=label,
                confidence=sequence.confidence,
                raw_text=" | ".join(
                    f"{row.actor} > {row.victim}" for row in sequence.rows[:8]
                ),
                kill_count=kill_count,
                score_weight=weight,
            )
        )
    return events


def parse_killfeed_batch(
    batch_rois: BatchROIExtractionResult,
    config: KillfeedConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> BatchKillfeedResult:
    """Convenience function to parse a batch of extracted killfeed ROIs."""
    parser = KillfeedParser(config=config)
    return parser.evaluate_batch(batch_rois, progress_callback=progress_callback)
