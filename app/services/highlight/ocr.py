"""Shared lightweight OCR token reader for Phase 3 HUD analysis.

Wraps RapidOCR (already used by the Stage 3 visual matcher) behind a small
token contract carrying both the recognised text and its bounding box. The
killfeed parser and ultimate meter tracker need the geometry as much as the
text, so tokens expose left/top/width/height and their derived centers.

The reader degrades gracefully: when RapidOCR is unavailable, ``read()``
returns an empty list and callers fall back to color/template heuristics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.highlight.roi_extractor import ROIFrame

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OCRToken:
    """Single OCR detection with text and pixel bounding box."""

    text: str
    confidence: float
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0


class OCRReader:
    """Lazy RapidOCR wrapper returning ``OCRToken`` instances."""

    def __init__(self, min_confidence: float = 0.35, engine: Any | None = None) -> None:
        self.min_confidence = min_confidence
        self._ocr_engine = engine
        self._initialized = engine is not None

    def _ensure_engine(self) -> Any:
        """Initialize RapidOCR on first use."""
        if not self._initialized:
            self._initialized = True
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._ocr_engine = RapidOCR()
                logger.debug("Shared OCR reader initialized RapidOCR.")
            except Exception as exc:
                logger.warning(
                    "RapidOCR unavailable; Phase 3 OCR stages will be skipped: %s",
                    exc,
                )
                self._ocr_engine = None
        return self._ocr_engine

    def read(self, frame: ROIFrame) -> list[OCRToken]:
        """Run OCR on an in-memory ROI frame and return confident tokens."""
        engine = self._ensure_engine()
        if engine is None:
            return []

        try:
            array = np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
                (frame.height, frame.width, 3)
            )
            results, _ = engine(array)
            if not results:
                return []

            tokens: list[OCRToken] = []
            for item in results:
                # RapidOCR item format: [box, text, confidence]
                if len(item) < 3:
                    continue
                box, text, confidence = item[0], str(item[1]).strip(), float(item[2])
                if not text or confidence < self.min_confidence:
                    continue

                xs = [float(point[0]) for point in box]
                ys = [float(point[1]) for point in box]
                left, top = min(xs), min(ys)
                tokens.append(
                    OCRToken(
                        text=text,
                        confidence=confidence,
                        left=left,
                        top=top,
                        width=max(xs) - left,
                        height=max(ys) - top,
                    )
                )
            return tokens
        except Exception as exc:  # pragma: no cover - defensive OCR failure path
            logger.warning(
                "OCR read failed for %s frame at %.2fs: %s",
                frame.roi_name,
                frame.timestamp,
                exc,
            )
            return []
