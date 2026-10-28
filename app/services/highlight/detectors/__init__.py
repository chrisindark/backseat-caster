"""Highlight detectors package."""

from app.services.highlight.detectors.base import (
    BaseHighlightDetector,
    DetectionMetrics,
)
from app.services.highlight.detectors.fall_guys import FallGuysDetector
from app.services.highlight.detectors.generic import GenericHighlightDetector
from app.services.highlight.detectors.marvel_rivals import MarvelRivalsDetector
from app.services.highlight.detectors.registry import (
    get_detector,
    list_supported_detectors,
)

__all__ = [
    "BaseHighlightDetector",
    "DetectionMetrics",
    "FallGuysDetector",
    "GenericHighlightDetector",
    "MarvelRivalsDetector",
    "get_detector",
    "list_supported_detectors",
]
