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


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to a pixel width, splitting unusually long handles safely."""
    from PIL import Image, ImageDraw

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    current = ""
    for word in (text or "").split():
        if probe.textlength(word, font=font) > max_width:
            if current:
                lines.append(current)
                current = ""
            chunk = ""
            for char in word:
                if chunk and probe.textlength(chunk + char, font=font) > max_width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk += char
            current = chunk
            continue
        candidate = f"{current} {word}".strip()
        if current and probe.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def render_cta_overlay_png(
    path: Path,
    *,
    size: tuple[int, int],
    headline: str,
    subtitle: str = "",
    position: str = "bottom",
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
    if position == "upper_third":
        pill_y0 = int(height * 0.14)
    else:
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


def render_text_watermark_png(
    path: Path,
    *,
    channel_name: str,
    size: tuple[int, int] = (640, 160),
    opacity: float = 0.85,
    text_color: str = "#FFFFFF",
    font_path: str | None = None,
) -> Path:
    """Render a subtle text watermark / channel handle PNG with alpha transparency."""
    from PIL import Image, ImageDraw

    width, height = max(100, int(size[0])), max(40, int(size[1]))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    clean_text = (channel_name or "").strip()
    if not clean_text:
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, "PNG")
        return path

    font = _fit_font(clean_text, int(width * 0.85), int(height * 0.55), font_path)
    bbox = draw.textbbox((0, 0), clean_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pad_x = int(height * 0.25)
    pad_y = int(height * 0.15)
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    pill_x0 = (width - pill_w) // 2
    pill_y0 = (height - pill_h) // 2
    pill_x1 = pill_x0 + pill_w
    pill_y1 = pill_y0 + pill_h

    # Soft dark pill background for readability over light/dark gameplay
    alpha_int = max(30, min(255, int(255 * opacity * 0.7)))
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=pill_h // 2,
        fill=(11, 13, 19, alpha_int),
        outline=(255, 255, 255, max(20, int(alpha_int * 0.4))),
        width=max(1, height // 60),
    )

    text_x = pill_x0 + pad_x - bbox[0]
    text_y = pill_y0 + pad_y - bbox[1]

    # Draw text with specified opacity
    t_alpha = max(40, min(255, int(255 * opacity)))
    t_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)
    draw.text(
        (text_x, text_y),
        clean_text,
        font=font,
        fill=(t_rgb[0], t_rgb[1], t_rgb[2], t_alpha),
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, "PNG")
    return path


def render_hook_overlay_png(
    path: Path,
    *,
    size: tuple[int, int],
    text: str,
    position: str = "upper_third",
    accent: str = "#F43F5E",
    text_color: str = "#FFFFFF",
    font_path: str | None = None,
) -> Path:
    """Draw a transparent canvas with an upper-third hook caption badge.

    Keeps center 50% crosshairs and combat reticles completely untouched.
    """
    from PIL import Image, ImageDraw

    width, height = max(2, int(size[0])), max(2, int(size[1]))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    raw_text = (text or "").strip()
    if not raw_text:
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, "PNG")
        return path

    short_edge = min(width, height)
    card_w = int(width * 0.82)
    max_text_w = int(card_w * 0.88)

    # Fit font for up to 2 lines
    font_size = max(20, int(short_edge * 0.042))
    font = resolve_font(font_size, font_path)
    lines = _wrap_text(raw_text, font, max_text_w)
    if len(lines) > 2:
        # Scale font down slightly if text spills to 3+ lines
        font_size = max(16, int(font_size * 0.8))
        font = resolve_font(font_size, font_path)
        lines = _wrap_text(raw_text, font, max_text_w)[:2]

    # Measure lines
    line_metrics = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [b[3] - b[1] for b in line_metrics]
    line_widths = [b[2] - b[0] for b in line_metrics]
    line_gap = max(4, int(short_edge * 0.01))
    total_text_h = sum(line_heights) + (len(lines) - 1) * line_gap

    pad_x = max(16, int(short_edge * 0.04))
    pad_y = max(12, int(short_edge * 0.025))

    actual_card_w = min(card_w, max(line_widths) + pad_x * 2)
    card_h = total_text_h + pad_y * 2
    card_x0 = (width - actual_card_w) // 2

    if position == "top":
        card_y0 = int(height * 0.05)
    elif position == "center":
        card_y0 = int(height * 0.40)
    else:  # upper_third (default)
        card_y0 = int(height * 0.14)

    card_x1 = card_x0 + actual_card_w
    card_y1 = card_y0 + card_h

    # Card background: dark translucent container with accent glow border
    accent_rgb = hex_to_rgb(accent, DEFAULT_ACCENT)
    text_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)

    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=max(8, card_h // 5),
        fill=(11, 13, 19, 215),
        outline=accent_rgb,
        width=max(2, short_edge // 140),
    )

    # Accent indicator bar on the left edge inside the card
    bar_w = max(3, short_edge // 120)
    bar_margin = max(6, int(pad_x * 0.4))
    draw.rounded_rectangle(
        [
            card_x0 + bar_margin,
            card_y0 + pad_y // 2,
            card_x0 + bar_margin + bar_w,
            card_y1 - pad_y // 2,
        ],
        radius=bar_w // 2,
        fill=accent_rgb,
    )

    # Draw centered text lines
    curr_y = card_y0 + pad_y
    for i, line in enumerate(lines):
        bbox = line_metrics[i]
        lw = line_widths[i]
        lh = line_heights[i]
        text_x = card_x0 + (actual_card_w - lw) // 2 - bbox[0]
        text_y = curr_y - bbox[1]
        draw.text((text_x, text_y), line, font=font, fill=text_rgb)
        curr_y += lh + line_gap

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, "PNG")
    return path


def render_kill_notification_png(
    path: Path,
    *,
    size: tuple[int, int],
    label: str,
    combo: int = 1,
    position: str = "lower_third",
    accent: str = "#F43F5E",
    text_color: str = "#FFFFFF",
    font_path: str | None = None,
) -> Path:
    """Draw a transparent canvas with a restrained kill notification badge.

    Positioned in the lower-third (y ≈ 0.72 * height) or upper-third (y ≈ 0.22 * height)
    to completely avoid covering the center 50% crosshairs, killfeed, or bottom HUD.
    """
    from PIL import Image, ImageDraw

    width, height = max(2, int(size[0])), max(2, int(size[1]))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    raw_label = (label or "ELIMINATION").strip().upper()
    short_edge = min(width, height)
    pill_w = max(180, int(width * 0.58))
    pill_h = max(36, int(short_edge * 0.085))

    pill_x0 = (width - pill_w) // 2
    if position == "upper_third":
        pill_y0 = int(height * 0.22)
    else:  # lower_third (default)
        pill_y0 = int(height * 0.72)

    pill_x1 = pill_x0 + pill_w
    pill_y1 = pill_y0 + pill_h

    # Highlight colors
    accent_rgb = hex_to_rgb(accent, DEFAULT_ACCENT)
    text_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)

    # Dark translucent container with accent glow border
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=pill_h // 2,
        fill=(11, 13, 19, 220),
        outline=accent_rgb,
        width=max(2, short_edge // 160),
    )

    # Optional combo badge on the left side
    combo_badge_w = 0
    if combo > 1:
        combo_text = f"{combo}x"
        combo_font = _fit_font(
            combo_text, int(pill_h * 0.9), int(pill_h * 0.45), font_path
        )
        c_box = draw.textbbox((0, 0), combo_text, font=combo_font)
        c_w = c_box[2] - c_box[0]
        c_h = c_box[3] - c_box[1]
        combo_badge_w = max(int(pill_h * 0.8), c_w + 16)
        badge_x0 = pill_x0 + int(pill_h * 0.15)
        badge_y0 = pill_y0 + int(pill_h * 0.15)
        badge_x1 = badge_x0 + combo_badge_w
        badge_y1 = pill_y1 - int(pill_h * 0.15)

        draw.rounded_rectangle(
            [badge_x0, badge_y0, badge_x1, badge_y1],
            radius=(badge_y1 - badge_y0) // 2,
            fill=accent_rgb,
        )
        draw.text(
            (
                badge_x0 + (combo_badge_w - c_w) // 2 - c_box[0],
                badge_y0 + ((badge_y1 - badge_y0) - c_h) // 2 - c_box[1],
            ),
            combo_text,
            font=combo_font,
            fill=(255, 255, 255),
        )
    else:
        # Subtle accent dot
        dot_r = max(4, pill_h // 8)
        dot_cx = pill_x0 + int(pill_h * 0.5)
        dot_cy = pill_y0 + pill_h // 2
        draw.ellipse(
            [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
            fill=accent_rgb,
        )
        combo_badge_w = int(pill_h * 0.5)

    # Main elimination label
    avail_text_w = pill_w - combo_badge_w - int(pill_h * 0.6)
    label_font = _fit_font(raw_label, avail_text_w, int(pill_h * 0.48), font_path)
    l_box = draw.textbbox((0, 0), raw_label, font=label_font)
    l_w = l_box[2] - l_box[0]
    l_h = l_box[3] - l_box[1]

    text_x = (
        pill_x0
        + combo_badge_w
        + int(pill_h * 0.3)
        + (avail_text_w - l_w) // 2
        - l_box[0]
    )
    text_y = pill_y0 + (pill_h - l_h) // 2 - l_box[1]
    draw.text((text_x, text_y), raw_label, font=label_font, fill=text_rgb)

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
    opacity: float = 0.85,
    kind: str = "intro",
) -> Path:
    """Draw a single branded card (translucent/opaque background, accent rules, centred text)."""
    from PIL import Image, ImageDraw

    width, height = max(2, int(size[0])), max(2, int(size[1]))
    bg_rgb = hex_to_rgb(background, DEFAULT_BACKGROUND)
    accent_rgb = hex_to_rgb(accent, DEFAULT_ACCENT)
    text_rgb = hex_to_rgb(text_color, DEFAULT_TEXT)

    # Use RGBA canvas so background opacity lets underlying gameplay show through
    bg_alpha = max(0, min(255, int(round(255 * opacity))))
    canvas = Image.new(
        "RGBA", (width, height), (bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_alpha)
    )
    draw = ImageDraw.Draw(canvas)

    short_edge = min(width, height)
    rule = max(4, short_edge // 90)
    # Accent rules stay crisp with full opacity
    draw.rectangle(
        [0, 0, width, rule], fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 255)
    )
    draw.rectangle(
        [0, height - rule, width, height],
        fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 255),
    )

    fallback_title = "SUBSCRIBE" if kind == "outro" else "HIGHLIGHTS"
    headline = (title or "").strip() or fallback_title
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
        sub_w = sub_box[2] - sub_box[0]
        sub_h = sub_box[3] - sub_box[1]
        block_h += gap + sub_h

    cursor_y = (height - block_h) / 2
    draw.text(
        ((width - title_w) / 2 - title_box[0], cursor_y - title_box[1]),
        headline,
        font=title_font,
        fill=(text_rgb[0], text_rgb[1], text_rgb[2], 255),
    )

    if sub and sub_font:
        cursor_y += title_h + gap
        draw.text(
            ((width - sub_w) / 2 - sub_box[0], cursor_y - sub_box[1]),
            sub,
            font=sub_font,
            fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 255),
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
        """Extra runtime added by the cards. In overlay mode, cards sit on gameplay without adding runtime."""
        if self.config.style == "overlay":
            return 0.0
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
                "opacity": self.config.opacity,
                "style": self.config.style,
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
                opacity=config.opacity,
                kind="intro",
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
                opacity=config.opacity,
                kind="outro",
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
