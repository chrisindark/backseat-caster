"""Detector registry and resolver for highlight mining strategies."""

from __future__ import annotations

from typing import Any

from app.services.highlight.detectors.base import BaseHighlightDetector
from app.services.highlight.detectors.generic import GenericHighlightDetector
from app.services.highlight.detectors.marvel_rivals import MarvelRivalsDetector

MARVEL_RIVALS_ALIASES = {
    "marvel_rivals",
    "marvel rivals",
    "mvr",
    "marvelrivals",
    "marvel-rivals",
}


def get_detector(
    game: str | None = None,
    video_title: str = "",
    video_description: str = "",
) -> BaseHighlightDetector:
    """
    Resolve appropriate highlight detector strategy for a video.

    Args:
        game: Explicit game name or profile requested (e.g. 'marvel_rivals', 'generic', 'Elden Ring').
        video_title: Source video title used for auto-detection fallback.
        video_description: Source video description used for auto-detection fallback.

    Returns:
        An instance of BaseHighlightDetector.
    """
    if game:
        norm = game.strip().lower()
        if norm in MARVEL_RIVALS_ALIASES:
            return MarvelRivalsDetector()
        return GenericHighlightDetector(game_name=game)

    # Auto-detect from video metadata
    combined = f"{video_title} {video_description}".lower()
    if any(alias in combined for alias in ("marvel rivals", "marvel_rivals")):
        return MarvelRivalsDetector()

    return GenericHighlightDetector(game_name="Generic")


def list_supported_detectors() -> list[dict[str, Any]]:
    """Return catalog of available highlight detector profiles."""
    return [
        {
            "id": "generic",
            "name": "Generic / Single Player",
            "description": "Loudness & excitement-based detection with zero HUD template coupling.",
        },
        {
            "id": "marvel_rivals",
            "name": "Marvel Rivals",
            "description": (
                "HUD OCR banners, structured killfeed chains, ultimate meter casts "
                "and hero/ability template identification."
            ),
        },
    ]
