"""Branded intro/outro cards: rasterise a card, concatenate it with the clip.

Why Pillow instead of FFmpeg's ``drawtext``: ``drawtext`` needs an FFmpeg built
with libfreetype **and** a resolvable font file at runtime. The Homebrew build on
macOS ships without freetype and slim container images often have no fonts, so a
``drawtext``-based implementation silently fails on the exact machines creators
use. Rasterising the card with Pillow and feeding it back as a looped image input
works everywhere FFmpeg can encode, and gives full control over the layout.

The cards are concatenated inside the same FFmpeg pass that renders the clip, so
branding costs no extra encode generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.rendering.config import BrandingConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL import ImageFont

logger = logging.getLogger(__name__)

#: Bold faces tried in order before falling back to Pillow's bundled font.
FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)

DEFAULT_BACKGROUND = (11, 13, 19)
DEFAULT_ACCENT = (244, 63, 94)
DEFAULT_TEXT = (255, 255, 255)


def hex_to_rgb(
    value: str | None, fallback: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Parse ``#RRGGBB`` (or ``RRGGBB``) into an RGB tuple, falling back safely."""
    if not value:
        return fallback
    token = str(value).strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return fallback
    try:
        return (int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16))
    except ValueError:
        return fallback


def resolve_font(size: int, font_path: str | None = None) -> ImageFont.FreeTypeFont:
    """Load a bold font at ``size`` px, degrading to Pillow's bundled face."""

    from PIL import ImageFont

    candidates: list[str] = []
    if font_path:
        candidates.append(str(font_path))
    candidates.extend(FONT_CANDIDATES)

    for candidate in candidates:
        try:
            if candidate and Path(candidate).exists():
                return ImageFont.truetype(candidate, size)
        except OSError as exc:  # unreadable/unsupported font file
            logger.debug("Skipping unusable font %s: %s", candidate, exc)

    # Pillow >= 10.1 bundles Aileron, so this always renders text.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: fixed-size bitmap font
        return ImageFont.load_default()


def _fit_font(
    text: str, max_width: int, start_size: int, font_path: str | None
) -> ImageFont.FreeTypeFont:
    """Largest font size (step 4px) whose rendering of ``text`` fits ``max_width``."""
    size = max(16, start_size)
    while size > 16:
        font = resolve_font(size, font_path)
        try:
            if font.getbbox(text)[2] <= max_width:
                return font
        except Exception:  # pragma: no cover - defensive against odd glyphs
            return font
        size -= 4
    return resolve_font(16, font_path)


def render_cta_overlay_png(
    path: Path,
    *,
    size: tuple[int, int],
    headline: str,
    subtitle: str = "",
    accent: str = "#F43F5E",
    text_color: str = "#FFFFFF",
    font_path: str | None = None,
) -> Path:
    """Draw a transparent lower-third pill (bell + headline + subtitle)."""
    from PIL import Image, ImageDraw

    width, height = max(2, int(size[0])), max(2, int(size[1]))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    short_edge = min(width, height)
    pill_w = int(width * 0.78)
    pill_h = int(short_edge * 0.16)
    margin = int(short_edge * 0.06)
    pill_x0 = (width - pill_w) // 2
    pill_y0 = height - pill_h - margin
    pill_x1 = pill_x0 + pill_w
    pill_y1 = pill_y0 + pill_h

    # Semi-transparent dark pill with accent border.
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=pill_h // 2,
        fill=(11, 13, 19, 210),
        outline=hex_to_rgb(accent, DEFAULT_ACCENT),
        width=max(2, short_edge // 120),
    )

    accent_rgb = hex_to_rgb(accent, DEFAULT_ACCENT)
    text_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)

    # Bell icon on the left.
    bell_cx = pill_x0 + int(pill_h * 0.9)
    bell_cy = pill_y0 + pill_h // 2
    bell_r = int(pill_h * 0.32)
    draw.ellipse(
        [bell_cx - bell_r, bell_cy - bell_r, bell_cx + bell_r, bell_cy + bell_r],
        fill=accent_rgb,
    )
    # Clapper
    draw.rectangle(
        [
            bell_cx - bell_r // 3,
            bell_cy + bell_r - 2,
            bell_cx + bell_r // 3,
            bell_cy + bell_r + bell_r // 2,
        ],
        fill=accent_rgb,
    )

    # Text block.
    headline = (headline or "SUBSCRIBE").strip()
    sub = (subtitle or "").strip()
    title_font = _fit_font(headline, int(pill_w * 0.55), int(pill_h * 0.42), font_path)
    title_box = draw.textbbox((0, 0), headline, font=title_font)
    title_h = title_box[3] - title_box[1]

    sub_font = None
    sub_h = 0
    gap = int(short_edge * 0.012) if sub else 0
    if sub:
        sub_font = _fit_font(sub, int(pill_w * 0.55), int(pill_h * 0.26), font_path)
        sub_box = draw.textbbox((0, 0), sub, font=sub_font)
        sub_h = sub_box[3] - sub_box[1]

    text_block_h = title_h + (gap + sub_h if sub else 0)
    text_x = bell_cx + bell_r + int(pill_h * 0.35)
    text_y = pill_y0 + (pill_h - text_block_h) // 2
    draw.text(
        (text_x - title_box[0], text_y - title_box[1]),
        headline,
        font=title_font,
        fill=text_rgb,
    )
    if sub and sub_font:
        sub_y = text_y + title_h + gap
        sub_box = draw.textbbox((0, 0), sub, font=sub_font)
        draw.text(
            (text_x - sub_box[0], sub_y - sub_box[1]),
            sub,
            font=sub_font,
            fill=accent_rgb,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, "PNG")
    return path


def render_card_png(
    path: Path,
    *,
    size: tuple[int, int],
    title: str,
    subtitle: str = "",
    background: str = "#0B0D13",
    accent: str = "#F43F5E",
    text_color: str = "#FFFFFF",
    font_path: str | None = None,
) -> Path:
    """Draw a single branded card (dark background, accent rules, centred text)."""
    from PIL import Image, ImageDraw

    width, height = max(2, int(size[0])), max(2, int(size[1]))
    bg_rgb = hex_to_rgb(background, DEFAULT_BACKGROUND)
    accent_rgb = hex_to_rgb(accent, DEFAULT_ACCENT)
    text_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)

    canvas = Image.new("RGB", (width, height), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    short_edge = min(width, height)
    rule = max(4, short_edge // 90)
    draw.rectangle([0, 0, width, rule], fill=accent_rgb)
    draw.rectangle([0, height - rule, width, height], fill=accent_rgb)

    headline = (title or "").strip() or "SUBSCRIBE"
    sub = (subtitle or "").strip()

    title_font = _fit_font(
        headline, int(width * 0.82), int(short_edge * 0.14), font_path
    )
    title_box = draw.textbbox((0, 0), headline, font=title_font)
    title_w, title_h = title_box[2] - title_box[0], title_box[3] - title_box[1]

    block_h = title_h
    sub_font = None
    sub_w = sub_h = 0
    gap = int(short_edge * 0.05) if sub else 0
    if sub:
        sub_font = _fit_font(sub, int(width * 0.74), int(short_edge * 0.055), font_path)
        sub_box = draw.textbbox((0, 0), sub, font=sub_font)
        sub_h = sub_box[3] - sub_box[1]
        block_h += gap + sub_h

    cursor_y = (height - block_h) / 2
    draw.text(
        ((width - title_w) / 2 - title_box[0], cursor_y - title_box[1]),
        headline,
        font=title_font,
        fill=text_rgb,
    )

    if sub and sub_font:
        cursor_y += title_h + gap
        sub_box = draw.textbbox((0, 0), sub, font=sub_font)
        draw.text(
            ((width - sub_w) / 2 - sub_box[0], cursor_y - sub_box[1]),
            sub,
            font=sub_font,
            fill=accent_rgb,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, "PNG")
    return path


@dataclass
class BrandingPlan:
    """Resolved branding for one render: durations plus per-mode card files."""

    config: BrandingConfig
    intro_seconds: float = 0.0
    outro_seconds: float = 0.0
    cards: dict[str, tuple[Path | None, Path | None]] = field(default_factory=dict)
    card_dir: Path | None = None

    @property
    def active(self) -> bool:
        return (self.intro_seconds > 0 or self.outro_seconds > 0) and bool(self.cards)

    @property
    def padding_seconds(self) -> float:
        """Extra runtime added by the cards."""
        return self.intro_seconds + self.outro_seconds

    def intro_card(self, mode: str) -> Path | None:
        return self.cards.get(mode, (None, None))[0]

    def outro_card(self, mode: str) -> Path | None:
        return self.cards.get(mode, (None, None))[1]

    def describe(self, total_duration: float) -> dict[str, Any]:
        """Manifest-friendly summary, including the final file duration."""
        payload = self.config.describe()
        payload.update(
            {
                "intro_seconds": self.intro_seconds,
                "outro_seconds": self.outro_seconds,
                "padding_seconds": round(self.padding_seconds, 3),
                "total_duration_seconds": round(total_duration, 3),
            }
        )
        return payload

    def cleanup(self) -> None:
        """Remove generated card images once FFmpeg has consumed them."""
        cleanup_png_dir(self.card_dir)


def cleanup_png_dir(directory: Path | None) -> None:
    """Delete a throwaway PNG directory (branded cards, CTA overlays)."""
    if not directory or not directory.exists():
        return
    for leftover in directory.glob("*.png"):
        try:
            leftover.unlink()
        except OSError:  # pragma: no cover - best effort
            pass
    try:
        directory.rmdir()
    except OSError:  # pragma: no cover - best effort
        pass


def build_branding_plan(
    *,
    config: BrandingConfig,
    sizes: dict[str, tuple[int, int]],
    card_dir: Path,
) -> BrandingPlan | None:
    """Rasterise every card a render needs, or ``None`` when branding is off."""
    if not config.has_bookends or not sizes:
        return None

    intro_seconds = config.intro_seconds if config.has_intro else 0.0
    outro_seconds = config.outro_seconds if config.has_outro else 0.0

    plan = BrandingPlan(
        config=config,
        intro_seconds=intro_seconds,
        outro_seconds=outro_seconds,
        card_dir=card_dir,
    )

    intro_title = config.resolved_intro_title()
    outro_subtitle = config.resolved_outro_subtitle()

    for mode, (width, height) in sizes.items():
        intro_path = outro_path = None
        if intro_seconds > 0:
            intro_path = render_card_png(
                card_dir / f"{mode}_intro.png",
                size=(width, height),
                title=intro_title,
                subtitle=config.intro_subtitle,
                background=config.background_color,
                accent=config.accent_color,
                text_color=config.text_color,
                font_path=config.font_path,
            )
        if outro_seconds > 0:
            outro_path = render_card_png(
                card_dir / f"{mode}_outro.png",
                size=(width, height),
                title=config.outro_title or "SUBSCRIBE",
                subtitle=outro_subtitle,
                background=config.background_color,
                accent=config.accent_color,
                text_color=config.text_color,
                font_path=config.font_path,
            )
        plan.cards[mode] = (intro_path, outro_path)

    if not plan.active:
        plan.cleanup()
        return None

    logger.info(
        "Branding enabled: intro=%.2fs outro=%.2fs (%d card(s) generated)",
        intro_seconds,
        outro_seconds,
        len(plan.cards) * 2,
    )
    return plan


def build_card_video_filter(
    *,
    input_label: str,
    output_label: str,
    width: int,
    height: int,
    fps: float,
) -> str:
    """Normalise a still card into a segment that concat will accept."""
    return (
        f"[{input_label}]scale={width}:{height},setsar=1,"
        f"fps={_fmt_fps(fps)},format=yuv420p[{output_label}]"
    )


def build_concat_filter(
    *,
    intro_label: str | None,
    main_label: str,
    outro_label: str | None,
    output_label: str,
) -> str:
    """Concatenate whichever bookends are present around the clip segment."""
    segments = []
    if intro_label:
        segments.append(f"[{intro_label}]")
    segments.append(f"[{main_label}]")
    if outro_label:
        segments.append(f"[{outro_label}]")
    return f"{''.join(segments)}concat=n={len(segments)}:v=1:a=0[{output_label}]"


def build_branding_audio_filter(
    *,
    input_label: str,
    output_label: str,
    intro_seconds: float,
    main_seconds: float,
    outro_seconds: float,
) -> str:
    """Pad the clip audio with silence so it stays in sync behind the cards."""
    total = max(0.0, intro_seconds) + max(0.0, main_seconds) + max(0.0, outro_seconds)
    delay_ms = max(0, int(round(intro_seconds * 1000)))
    chain = []
    if delay_ms:
        chain.append(f"adelay={delay_ms}:all=1")
    chain.append("apad")
    chain.append(f"atrim=duration={total:.3f}")
    return f"[{input_label}]{','.join(chain)}[{output_label}]"


def _fmt_fps(fps: float) -> str:
    """Render a frame rate without a trailing ``.0`` so FFmpeg gets a clean value."""
    value = float(fps) if fps and fps > 0 else 30.0
    return f"{value:.6g}"
