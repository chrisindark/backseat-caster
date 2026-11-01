"""Tests for Milestone 2: Gameplay overlays and subtle branding.

Tests:
1. Hook overlay image rasterisation (upper_third, top, center)
2. Text watermark fallback image rasterisation
3. Watermark filter time gating (start_seconds, end_seconds)
4. In-video CTA pill positioning (bottom, upper_third)
5. End-to-end synthetic render with hook, watermark timing, and CTA overlay
6. Frame extraction and inspection at key lifecycle timestamps
7. Channel profile schema & API integration for hook and CTA position
"""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.rendering.branding import (
    render_cta_overlay_png,
    render_hook_overlay_png,
    render_text_watermark_png,
)
from app.rendering.config import (
    CtaConfig,
    HookConfig,
    RenderConfig,
    WatermarkConfig,
)
from app.rendering.engine import RenderEngine
from app.rendering.filters import build_watermark_filter


def test_render_hook_overlay_upper_third(tmp_path: Path):
    """Hook overlay produces an RGBA PNG with badge in upper third."""
    out_path = tmp_path / "hook.png"
    result = render_hook_overlay_png(
        out_path,
        size=(1080, 1920),
        text="CLUTCH 1v3 VICTORY",
        position="upper_third",
    )
    assert result.exists()
    with Image.open(result) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
        # Bounding box of non-zero alpha should be in upper third (y between 150 and 600)
        bbox = img.getbbox()
        assert bbox is not None
        y0, y1 = bbox[1], bbox[3]
        assert y0 >= 180  # leaves top clear
        assert y1 <= 650  # well above center crosshairs at 960


def test_render_hook_overlay_multiline(tmp_path: Path):
    """Long hook captions wrap cleanly into at most 2 lines."""
    out_path = tmp_path / "hook_multi.png"
    result = render_hook_overlay_png(
        out_path,
        size=(1080, 1920),
        text="WATCH TILL THE END FOR THE CRAZIEST FLICK SHOT EVER SEEN IN TOURNAMENT PLAY",
        position="upper_third",
    )
    assert result.exists()
    with Image.open(result) as img:
        bbox = img.getbbox()
        assert bbox is not None
        # Height of badge should stay reasonable (< 350px)
        assert (bbox[3] - bbox[1]) < 350


def test_render_text_watermark(tmp_path: Path):
    """Text watermark produces a compact translucent handle graphic."""
    out_path = tmp_path / "handle.png"
    result = render_text_watermark_png(
        out_path,
        channel_name="@BackseatCaster",
        size=(640, 160),
        opacity=0.75,
    )
    assert result.exists()
    with Image.open(result) as img:
        assert img.size == (640, 160)
        assert img.mode == "RGBA"
        bbox = img.getbbox()
        assert bbox is not None
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]


def test_render_cta_overlay_positions(tmp_path: Path):
    """CTA pill renders at bottom by default and upper_third when requested."""
    bottom_path = tmp_path / "cta_bottom.png"
    render_cta_overlay_png(
        bottom_path,
        size=(1080, 1920),
        headline="SUBSCRIBE",
        position="bottom",
    )
    upper_path = tmp_path / "cta_upper.png"
    render_cta_overlay_png(
        upper_path,
        size=(1080, 1920),
        headline="SUBSCRIBE",
        position="upper_third",
    )

    with Image.open(bottom_path) as b_img, Image.open(upper_path) as u_img:
        b_box = b_img.getbbox()
        u_box = u_img.getbbox()
        assert b_box is not None and u_box is not None
        # Bottom pill should be near bottom (y0 > 1400)
        assert b_box[1] > 1400
        # Upper third pill should be near top (y0 < 600)
        assert u_box[1] < 600


def test_build_watermark_filter_time_gating():
    """Watermark filter builder properly handles start_seconds and end_seconds."""
    # 1. Full-clip watermark (no timing)
    f_full = build_watermark_filter(
        watermark_input="1:v",
        main_input="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
    )
    assert "enable=" not in f_full

    # 2. Bounded window
    f_between = build_watermark_filter(
        watermark_input="1:v",
        main_input="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
        start_seconds=1.5,
        end_seconds=7.5,
    )
    assert "enable='between(t,1.500,7.500)'" in f_between

    # 3. Start only
    f_start = build_watermark_filter(
        watermark_input="1:v",
        main_input="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
        start_seconds=2.0,
    )
    assert "enable='gte(t,2.000)'" in f_start

    # 4. End only
    f_end = build_watermark_filter(
        watermark_input="1:v",
        main_input="v_in",
        output_label="v_out",
        width=1080,
        height=1920,
        end_seconds=5.0,
    )
    assert "enable='lte(t,5.000)'" in f_end


@pytest.fixture
def synthetic_video(tmp_path: Path) -> Path:
    """Generate a 10s synthetic 1280x720 video with test audio."""
    video_path = tmp_path / "synthetic_gameplay.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=10",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(video_path),
    ]
    subprocess.run(
        cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return video_path


def test_end_to_end_render_with_overlays(synthetic_video: Path, tmp_path: Path):
    """End-to-end clip render with text watermark, upper-third hook, and CTA overlay."""
    out_dir = tmp_path / "renders" / "clip_overlay_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = RenderConfig(
        preferred_encoder="libx264",
        quality_preset="high",
        watermark=WatermarkConfig(
            enabled=True,
            channel_name="@ProGamer",
            position="top_left",
            opacity=0.75,
            start_seconds=1.0,
            end_seconds=8.0,
        ),
        hook=HookConfig(
            enabled=True,
            text="INSANE 3K IN OVERTIME",
            duration_seconds=2.0,
            position="upper_third",
        ),
        cta=CtaConfig(
            enabled=True,
            style="overlay",
            seconds=2.5,
            position="bottom",
            headline="SUBSCRIBE FOR DAILY CLIPS",
        ),
    )

    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=synthetic_video,
        start_seconds=0.0,
        duration_seconds=10.0,
        output_dir=out_dir,
        clip_id="test_overlay_123",
        modes=["vertical_blur", "landscape"],
    )

    assert result.clip_id == "test_overlay_123"
    assert result.watermark_applied is True
    assert "vertical_blur" in result.outputs
    assert "landscape" in result.outputs

    # Verify manifest details
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())

    assert manifest["hook"]["enabled"] is True
    assert manifest["hook"]["text"] == "INSANE 3K IN OVERTIME"
    assert manifest["watermark"]["enabled"] is True
    assert manifest["watermark"]["channel_name"] == "@ProGamer"
    assert manifest["watermark"]["start_seconds"] == 1.0
    assert manifest["watermark"]["end_seconds"] == 8.0
    assert manifest["cta"]["enabled"] is True
    assert manifest["cta"]["overlay"] is True

    # Frame inspection: extract frames at t=1.0s, t=5.0s, and t=9.0s
    vert_video = out_dir / "vertical_blur.mp4"
    assert vert_video.exists()
    f_1s = tmp_path / "frame_1s.png"
    f_5s = tmp_path / "frame_5s.png"
    f_9s = tmp_path / "frame_9s.png"

    for t_sec, f_path in [(1.0, f_1s), (5.0, f_5s), (9.0, f_9s)]:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t_sec:.1f}",
            "-i",
            str(vert_video),
            "-vframes",
            "1",
            str(f_path),
        ]
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        assert f_path.exists()
        with Image.open(f_path) as img:
            assert img.size == (1080, 1920)
