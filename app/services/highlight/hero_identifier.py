"""Hero and ability identification via local HUD icon template matching.

Hero art and ability icons cannot be bundled with the repository, so this module
expects a creator/project-supplied template folder:

```
data/hero_templates/<game>/heroes/<hero>.png
data/hero_templates/<game>/abilities/<ability>.png
```

Matching uses zero-normalized cross-correlation implemented with NumPy (no
OpenCV import required), with a coarse stride plus local refinement so ability
icons can be located inside a wide ability-row ROI quickly.

When the folder is absent or empty every method returns ``None``/``[]`` and the
pipeline continues exactly as before — identification is strictly additive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from app.config import settings
from app.services.highlight.roi_extractor import (
    ROIFrame,
    WindowROIExtractionResult,
)

logger = logging.getLogger(__name__)

SUPPORTED_TEMPLATE_SUFFIXES: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
)

_GRAY_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _to_rgb_array(frame: ROIFrame) -> np.ndarray:
    return np.frombuffer(frame.raw_rgb, dtype=np.uint8).reshape(
        (frame.height, frame.width, 3)
    )


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    return (rgb.astype(np.float32) @ _GRAY_WEIGHTS).astype(np.float32)


def _colorfulness(rgb: np.ndarray) -> float:
    """Mean per-pixel channel spread (0-1); desaturated icons read as grey."""
    if rgb.size == 0:
        return 0.0
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    return float(spread.mean() / 255.0)


def _window_sums(values: np.ndarray, height: int, width: int) -> np.ndarray:
    """Sum over every height x width window using an integral image."""
    integral = np.pad(values.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return (
        integral[height:, width:]
        - integral[:-height, width:]
        - integral[height:, :-width]
        + integral[:-height, :-width]
    )


def _ncc_map(image: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Exact zero-normalized cross-correlation for every window position.

    Window sums and squared sums come from integral images; the
    template/window product term is an FFT cross-correlation, so a wide
    ability-row ROI is still searched exhaustively at sub-millisecond cost.
    """
    # float64 keeps the large integral-image sums from cancelling into noise on
    # mostly-uniform HUD backgrounds (a false peak otherwise divides ~0 by ~0).
    image = image.astype(np.float64, copy=False)
    template = template.astype(np.float64, copy=False)
    template_height, template_width = template.shape
    pixel_count = float(template_height * template_width)

    window_sum = _window_sums(image, template_height, template_width)
    window_square_sum = _window_sums(image * image, template_height, template_width)

    convolution_shape = (
        image.shape[0] + template_height - 1,
        image.shape[1] + template_width - 1,
    )
    convolved = np.fft.irfft2(
        np.fft.rfft2(image, s=convolution_shape)
        * np.fft.rfft2(template[::-1, ::-1], s=convolution_shape),
        s=convolution_shape,
    )
    window_product = convolved[
        template_height - 1 : image.shape[0],
        template_width - 1 : image.shape[1],
    ]

    template_mean = float(template.mean())
    centered_template = template - template_mean
    template_norm = float(np.sqrt((centered_template * centered_template).sum()))

    window_mean = window_sum / pixel_count
    window_variance = window_square_sum - pixel_count * window_mean * window_mean
    numerator = window_product - pixel_count * window_mean * template_mean
    denominator = np.sqrt(np.maximum(window_variance, 0.0)) * template_norm

    return np.divide(numerator, np.maximum(denominator, 1e-6))


def _resize_template(template: np.ndarray, height: int, width: int) -> np.ndarray:
    """Resize a grayscale template to an exact shape using PIL."""
    try:
        from PIL import Image

        resized = Image.fromarray(template.astype(np.uint8)).resize(
            (width, height), Image.Resampling.BILINEAR
        )
        return np.asarray(resized, dtype=np.float32)
    except Exception:
        # Nearest-neighbour fallback without PIL.
        rows = np.linspace(0, template.shape[0] - 1, height).astype(int)
        cols = np.linspace(0, template.shape[1] - 1, width).astype(int)
        return template[np.ix_(rows, cols)]


def locate_best_match(
    image_gray: np.ndarray,
    template_gray: np.ndarray,
) -> tuple[float, int, int]:
    """Locate a template in an image, returning (score, x, y)."""
    if image_gray.size == 0 or template_gray.size == 0:
        return 0.0, 0, 0

    if (
        template_gray.shape[0] > image_gray.shape[0]
        or template_gray.shape[1] > image_gray.shape[1]
    ):
        template_gray = _resize_template(template_gray, *image_gray.shape)

    scores = _ncc_map(image_gray, template_gray)
    y, x = np.unravel_index(int(np.argmax(scores)), scores.shape)
    return float(scores[y, x]), int(x), int(y)


@dataclass
class TemplateImage:
    """Loaded icon template with lazily derived grayscale/colour metrics."""

    name: str
    rgb: np.ndarray
    path: str
    _gray: np.ndarray | None = None
    _colorfulness: float | None = None

    @property
    def gray(self) -> np.ndarray:
        if self._gray is None:
            self._gray = _to_gray(self.rgb)
        return self._gray

    @property
    def colorfulness(self) -> float:
        if self._colorfulness is None:
            self._colorfulness = _colorfulness(self.rgb)
        return self._colorfulness


class TemplateLibrary:
    """Filesystem-backed hero/ability icon template library."""

    def __init__(
        self,
        templates_dir: str | Path | None = None,
        game: str = "marvel_rivals",
    ) -> None:
        base = Path(templates_dir) if templates_dir else settings.hero_templates_path
        self.root = Path(base) / game
        self._cache: dict[str, dict[str, TemplateImage]] = {}

    def _load_kind(self, kind: str) -> dict[str, TemplateImage]:
        if kind in self._cache:
            return self._cache[kind]

        directory = self.root / kind
        templates: dict[str, TemplateImage] = {}
        if directory.exists():
            for path in sorted(directory.iterdir()):
                if not path.is_file() or path.suffix.lower() not in (
                    SUPPORTED_TEMPLATE_SUFFIXES
                ):
                    continue
                try:
                    from PIL import Image

                    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
                except Exception as exc:
                    logger.warning("Could not load HUD template %s: %s", path, exc)
                    continue
                templates[path.stem] = TemplateImage(
                    name=path.stem, rgb=rgb, path=str(path)
                )

        if not templates:
            logger.debug("No HUD %s templates found in %s", kind, directory)
        self._cache[kind] = templates
        return templates

    def heroes(self) -> dict[str, TemplateImage]:
        """Hero portrait templates keyed by hero name."""
        return self._load_kind("heroes")

    def abilities(self) -> dict[str, TemplateImage]:
        """Ability icon templates keyed by ability name."""
        return self._load_kind("abilities")


class HeroIdentifierConfig(BaseModel):
    """Configuration for hero portrait and ability icon matching."""

    templates_dir: str | None = Field(
        default=None,
        description="Override for the HUD template root (defaults to settings)",
    )
    game: str = Field(default="marvel_rivals", description="Template game subfolder")
    hero_roi: str = Field(
        default="hero_portrait", description="HUD region holding the hero portrait"
    )
    ability_roi: str = Field(
        default="ability_row", description="HUD region holding the ability icon row"
    )
    hero_match_threshold: float = Field(
        default=0.55, description="Minimum correlation to accept a hero match"
    )
    ability_match_threshold: float = Field(
        default=0.45, description="Minimum correlation to recognise an ability icon"
    )
    activation_threshold: float = Field(
        default=0.60,
        description="Correlation required to call a recognised icon available",
    )
    cooldown_colorfulness_ratio: float = Field(
        default=0.55,
        description="Icon colourfulness ratio below which the ability is on cooldown",
    )


class HeroMatch(BaseModel):
    """Identified played character."""

    hero: str = Field(..., description="Matched hero template name")
    confidence: float = Field(..., description="Correlation score (0-1)")
    template_path: str | None = Field(
        default=None, description="Template file used for the match"
    )


class AbilityMatch(BaseModel):
    """Recognised ability icon inside the ability row."""

    ability: str = Field(..., description="Matched ability template name")
    confidence: float = Field(..., description="Correlation score (0-1)")
    x: int = Field(default=0, description="Matched x offset in the ROI")
    y: int = Field(default=0, description="Matched y offset in the ROI")
    on_cooldown: bool = Field(
        default=False, description="True when the icon is desaturated/dimmed"
    )


class AbilityActivation(BaseModel):
    """Transition of an ability icon from cooldown back to available."""

    timestamp: float = Field(..., description="Activation timestamp in seconds")
    ability: str = Field(..., description="Ability template name")
    confidence: float = Field(..., description="Correlation score at activation")
    was_on_cooldown: bool = Field(
        default=True, description="True when a prior frame showed the icon dimmed"
    )


class HeroIdentifier:
    """Matches the hero portrait ROI against hero templates."""

    def __init__(
        self,
        config: HeroIdentifierConfig | None = None,
        library: TemplateLibrary | None = None,
    ) -> None:
        self.config = config or HeroIdentifierConfig()
        self.library = library or TemplateLibrary(
            templates_dir=self.config.templates_dir, game=self.config.game
        )

    def identify(self, frame: ROIFrame) -> HeroMatch | None:
        """Identify the played hero from a single portrait frame."""
        templates = self.library.heroes()
        if not templates:
            return None

        image_gray = _to_gray(_to_rgb_array(frame))
        best: HeroMatch | None = None
        for template in templates.values():
            score, _, _ = locate_best_match(image_gray, template.gray)
            if score < self.config.hero_match_threshold:
                continue
            if best is None or score > best.confidence:
                best = HeroMatch(
                    hero=template.name,
                    confidence=round(score, 3),
                    template_path=template.path,
                )
        return best

    def identify_window(
        self, window_rois: WindowROIExtractionResult
    ) -> HeroMatch | None:
        """Identify the hero across every portrait frame in a window."""
        frames = window_rois.frames_by_roi.get(self.config.hero_roi, [])
        best: HeroMatch | None = None
        for frame in frames:
            match = self.identify(frame)
            if match and (best is None or match.confidence > best.confidence):
                best = match
        return best


class AbilityTracker:
    """Tracks ability icon availability and cooldown -> ready transitions."""

    def __init__(
        self,
        config: HeroIdentifierConfig | None = None,
        library: TemplateLibrary | None = None,
    ) -> None:
        self.config = config or HeroIdentifierConfig()
        self.library = library or TemplateLibrary(
            templates_dir=self.config.templates_dir, game=self.config.game
        )

    def _match_ability(
        self, frame: ROIFrame, template: TemplateImage
    ) -> AbilityMatch | None:
        rgb = _to_rgb_array(frame)
        score, x, y = locate_best_match(_to_gray(rgb), template.gray)
        if score < self.config.ability_match_threshold:
            return None

        height = min(template.rgb.shape[0], frame.height - y)
        width = min(template.rgb.shape[1], frame.width - x)
        region = rgb[y : y + height, x : x + width]
        available = _colorfulness(region) >= (
            template.colorfulness * self.config.cooldown_colorfulness_ratio
        )
        return AbilityMatch(
            ability=template.name,
            confidence=round(score, 3),
            x=int(x),
            y=int(y),
            on_cooldown=not available,
        )

    def track_window(
        self, window_rois: WindowROIExtractionResult
    ) -> list[AbilityActivation]:
        """Detect cooldown -> available transitions inside a window."""
        templates = self.library.abilities()
        frames = window_rois.frames_by_roi.get(self.config.ability_roi, [])
        if not templates or not frames:
            return []

        previous_state: dict[str, bool] = {}
        activations: list[AbilityActivation] = []

        for frame in sorted(frames, key=lambda f: f.timestamp):
            for template in templates.values():
                match = self._match_ability(frame, template)
                if match is None:
                    continue

                was_on_cooldown = previous_state.get(match.ability)
                if (
                    was_on_cooldown
                    and not match.on_cooldown
                    and match.confidence >= self.config.activation_threshold
                ):
                    activations.append(
                        AbilityActivation(
                            timestamp=round(frame.timestamp, 3),
                            ability=match.ability,
                            confidence=match.confidence,
                            was_on_cooldown=True,
                        )
                    )
                previous_state[match.ability] = match.on_cooldown

        return activations
