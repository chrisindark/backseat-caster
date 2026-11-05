"""Tests for branded intro/outro cards (Phase 10.5)."""

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.rendering.branding import (
    BrandingPlan,
    build_branding_audio_filter,
    build_branding_plan,
    build_card_video_filter,
    build_concat_filter,
    hex_to_rgb,
    render_card_png,
    resolve_font,
)
from app.rendering.config import BrandingConfig, RenderConfig, WatermarkConfig
from app.rendering.engine import RenderEngine


@pytest.fixture(scope="session")
def brand_assets(tmp_path_factory) -> dict[str, Path]:
    """20-second 640x360 synthetic gameplay clip with audio."""
    temp_dir = tmp_path_factory.mktemp("brand_assets")
    video_path = temp_dir / "gameplay.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=20:size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=20",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video_path),
        ],
        capture_output=True,
        check=True,
    )
    return {"video": video_path}


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


# --- Unit: colour + font helpers -------------------------------------------


def test_hex_to_rgb_accepts_common_forms():
    assert hex_to_rgb("#FF0000", (0, 0, 0)) == (255, 0, 0)
    assert hex_to_rgb("00ff00", (0, 0, 0)) == (0, 255, 0)
    assert hex_to_rgb("#0f8", (0, 0, 0)) == (0, 255, 136)


def test_hex_to_rgb_falls_back_on_garbage():
    fallback = (1, 2, 3)
    assert hex_to_rgb(None, fallback) == fallback
    assert hex_to_rgb("", fallback) == fallback
    assert hex_to_rgb("#12345", fallback) == fallback
    assert hex_to_rgb("#GGGGGG", fallback) == fallback


def test_resolve_font_always_returns_a_usable_face():
    """No font file is guaranteed, so the fallback must still render text."""
    font = resolve_font(48)
    assert font.getbbox("SUBSCRIBE")[2] > 0


def test_render_card_png_draws_branded_card_pixels(tmp_path):
    card = render_card_png(
        tmp_path / "card.png",
        size=(320, 180),
        title="SUBSCRIBE",
        subtitle="@BackseatCaster",
        background="#101010",
        accent="#FF0000",
        text_color="#FFFFFF",
    )
    assert card.exists()
    with Image.open(card) as image:
        assert image.size == (320, 180)
        # Accent rules hug the top and bottom edges, background fills the rest.
        assert image.convert("RGB").getpixel((160, 1)) == (255, 0, 0)
        assert image.convert("RGB").getpixel((160, 178)) == (255, 0, 0)
        assert image.convert("RGB").getpixel((160, 90)) == (16, 16, 16)


# --- Unit: plan construction ----------------------------------------------


def test_build_branding_plan_returns_none_when_disabled(tmp_path):
    plan = build_branding_plan(
        config=BrandingConfig(enabled=False),
        sizes={"landscape": (1920, 1080)},
        card_dir=tmp_path / "cards",
    )
    assert plan is None


def test_build_branding_plan_returns_none_when_both_cards_off(tmp_path):
    plan = build_branding_plan(
        config=BrandingConfig(enabled=True, intro=False, outro=False),
        sizes={"landscape": (1920, 1080)},
        card_dir=tmp_path / "cards",
    )
    assert plan is None


def test_build_branding_plan_builds_one_card_per_mode_and_bookend(tmp_path):
    plan = build_branding_plan(
        config=BrandingConfig(enabled=True, channel_name="@BackseatCaster"),
        sizes={"landscape": (640, 360), "third_person": (360, 640)},
        card_dir=tmp_path / "cards",
    )
    assert isinstance(plan, BrandingPlan)
    assert plan.active is True
    assert set(plan.cards) == {"landscape", "third_person"}
    for mode in ("landscape", "third_person"):
        assert plan.intro_card(mode) and plan.intro_card(mode).exists()
        assert plan.outro_card(mode) and plan.outro_card(mode).exists()
    assert plan.padding_seconds == pytest.approx(3.2)


def test_build_branding_plan_skips_the_disabled_bookend(tmp_path):
    plan = build_branding_plan(
        config=BrandingConfig(enabled=True, intro=False, outro=True),
        sizes={"landscape": (640, 360)},
        card_dir=tmp_path / "cards",
    )
    assert plan is not None
    assert plan.intro_card("landscape") is None
    assert plan.outro_card("landscape") is not None
    assert plan.intro_seconds == 0.0
    assert plan.outro_seconds == pytest.approx(2.0)


# --- Unit: filter-string builders ----------------------------------------


def test_card_video_filter_normalises_stills_for_concat():
    filter_str = build_card_video_filter(
        input_label="2:v",
        output_label="brand_intro_0",
        width=1080,
        height=1920,
        fps=60.0,
    )
    assert filter_str == (
        "[2:v]scale=1080:1920,setsar=1,fps=60,format=yuv420p[brand_intro_0]"
    )


def test_concat_filter_includes_only_present_bookends():
    assert (
        build_concat_filter(
            intro_label="i", main_label="m", outro_label="o", output_label="out"
        )
        == "[i][m][o]concat=n=3:v=1:a=0[out]"
    )
    assert (
        build_concat_filter(
            intro_label=None, main_label="m", outro_label="o", output_label="out"
        )
        == "[m][o]concat=n=2:v=1:a=0[out]"
    )
    assert (
        build_concat_filter(
            intro_label="i", main_label="m", outro_label=None, output_label="out"
        )
        == "[i][m]concat=n=2:v=1:a=0[out]"
    )


def test_branding_audio_filter_delays_pads_and_trims():
    filter_str = build_branding_audio_filter(
        input_label="a_out",
        output_label="a_branded",
        intro_seconds=1.2,
        main_seconds=3.0,
        outro_seconds=2.0,
    )
    assert filter_str == "[a_out]adelay=1200:all=1,apad,atrim=duration=6.200[a_branded]"


def test_branding_audio_filter_skips_delay_without_intro():
    filter_str = build_branding_audio_filter(
        input_label="a_out",
        output_label="a_branded",
        intro_seconds=0.0,
        main_seconds=2.0,
        outro_seconds=1.0,
    )
    assert "adelay" not in filter_str
    assert "atrim=duration=3.000" in filter_str


# --- End-to-end: real FFmpeg render --------------------------------------


class TestBrandedRender:
    def _engine(self, branding: BrandingConfig) -> RenderEngine:
        return RenderEngine(
            RenderConfig(
                landscape_width=640,
                landscape_height=360,
                vertical_width=360,
                vertical_height=640,
                quality_preset="compact",
                preferred_encoder="libx264",
                branding=branding,
            )
        )

    def test_render_adds_intro_and_outro_and_cleans_cards(self, brand_assets, tmp_path):
        branding = BrandingConfig(
            enabled=True,
            channel_name="@BackseatCaster",
            intro_seconds=1.0,
            outro_seconds=1.5,
        )
        out_dir = tmp_path / "branded"
        result = self._engine(branding).render_clip(
            source_path=brand_assets["video"],
            start_seconds=0.0,
            duration_seconds=2.0,
            output_dir=out_dir,
            clip_id="branded",
            modes=["landscape"],
            branding=branding,
        )

        assert result.branding_applied is True
        assert result.branding_intro_seconds == pytest.approx(1.0)
        assert result.branding_outro_seconds == pytest.approx(1.5)
        assert result.total_duration_seconds == pytest.approx(4.5)

        duration = _probe_duration(out_dir / "landscape.mp4")
        assert duration == pytest.approx(4.5, abs=0.2)

        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert manifest["branding"]["intro"] is True
        assert manifest["branding"]["outro"] is True
        assert manifest["branding"]["padding_seconds"] == pytest.approx(2.5)
        assert manifest["outputs"]["landscape"]["duration"] == pytest.approx(4.5)
        # Card PNGs are throwaway intermediates, not deliverables.
        assert not (out_dir / ".branding_cards").exists()

    def test_render_without_branding_is_untouched(self, brand_assets, tmp_path):
        out_dir = tmp_path / "plain"
        result = self._engine(BrandingConfig(enabled=False)).render_clip(
            source_path=brand_assets["video"],
            start_seconds=0.0,
            duration_seconds=2.0,
            output_dir=out_dir,
            clip_id="plain",
            modes=["landscape"],
        )

        assert result.branding_applied is False
        assert result.total_duration_seconds == pytest.approx(2.0)
        assert _probe_duration(out_dir / "landscape.mp4") == pytest.approx(2.0, abs=0.2)
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert manifest["branding"]["enabled"] is False
        assert manifest["branding"]["intro"] is False

    def test_branding_composes_with_watermark_and_vertical_modes(
        self, brand_assets, tmp_path
    ):
        """Cards, crop geometry, sample aspect ratio and the logo must coexist.

        The crop/blur filters inherit a non-square SAR and the watermark is a
        separate still input, so this is the combination most likely to break
        `concat` (mismatched SAR) or silently lengthen the output (the logo
        loop running past the clip window).
        """
        logo = tmp_path / "logo.png"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=64x64:d=1",
                "-frames:v",
                "1",
                str(logo),
            ],
            capture_output=True,
            check=True,
        )

        branding = BrandingConfig(
            enabled=True, channel_name="@BackseatCaster", intro_seconds=0.8
        )
        engine = RenderEngine(
            RenderConfig(
                landscape_width=640,
                landscape_height=360,
                vertical_width=360,
                vertical_height=640,
                quality_preset="compact",
                preferred_encoder="libx264",
                branding=branding,
                watermark=WatermarkConfig(enabled=True, path=str(logo)),
            )
        )
        out_dir = tmp_path / "combo"
        result = engine.render_clip(
            source_path=brand_assets["video"],
            start_seconds=0.0,
            duration_seconds=2.0,
            output_dir=out_dir,
            clip_id="combo",
            modes=["landscape", "third_person", "vertical_blur"],
        )

        assert result.branding_applied is True
        assert result.watermark_applied is True
        assert result.total_duration_seconds == pytest.approx(4.8)
        for mode in ("landscape", "third_person", "vertical_blur"):
            # 2.0s clip + 0.8s intro + 2.0s outro, identical for every format.
            assert _probe_duration(out_dir / f"{mode}.mp4") == pytest.approx(
                4.8, abs=0.2
            )


# --- Service wiring: the real render-job path picks branding up --------------


def test_execute_render_job_applies_configured_branding(
    monkeypatch, brand_assets, tmp_path
):
    """Branding comes from the channel profile inside the job, not per request."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.config import settings
    from app.database import Base
    from app.models.render_job import RenderJob
    from app.models.video import Video
    from app.schemas.channel import ChannelProfileUpdate
    from app.services.channel_profile import ChannelProfileService
    from app.services.renders import RenderService
    from app.services.tts import TTSService

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path / "renders"))
        cta_audio = TTSService._silent_wav(4.0, tmp_path / "cta.wav")
        monkeypatch.setattr(
            TTSService,
            "generate_cta_audio",
            staticmethod(lambda speech_text, **kwargs: cta_audio),
        )

        # The creator turns bookends on in the channel profile.
        ChannelProfileService.update(
            session,
            ChannelProfileUpdate(
                channel_name="@BackseatCaster",
                branding_enabled=True,
                branding_intro_seconds=1.0,
                branding_outro_seconds=2.0,
                branding_style="bookend",
                max_clip_seconds=15.0,
                cta_enabled=True,
                cta_style="outro_card",
                cta_seconds=4.5,
            ),
        )

        video = Video(
            id="brand_vod",
            title="Branded VOD",
            duration=20,
            duration_formatted="0:20",
            channel_name="Test",
            channel_id="UC_test",
            channel_url="https://youtube.com/@test",
            webpage_url="https://youtube.com/watch?v=brand",
            is_downloaded=True,
            download_status="completed",
            local_file_path=str(brand_assets["video"]),
        )
        session.add(video)
        session.add(
            RenderJob(
                id="brand_job",
                clip_id="brand_job",
                video_id="brand_vod",
                status="pending",
                progress=0.0,
                start_seconds=0.0,
                duration_seconds=12.0,
                crop_preset="direct_crop",
                modes="landscape",
                encoder="libx264",
            )
        )
        session.commit()

        out = RenderService.execute_render_job("brand_job", db_session=session)
        assert out["status"] == "completed", out

        clip_dir = tmp_path / "renders" / "brand_job"
        assert _probe_duration(clip_dir / "landscape.mp4") == pytest.approx(
            15.0, abs=0.25
        )
        rendered_job = session.query(RenderJob).filter_by(id="brand_job").one()
        assert rendered_job.duration_seconds == pytest.approx(10.0)
        manifest = json.loads((clip_dir / "manifest.json").read_text())
        assert manifest["branding"]["enabled"] is True
        assert manifest["branding"]["channel_name"] == "@BackseatCaster"
        assert manifest["branding"]["intro_seconds"] == pytest.approx(1.0)
        assert manifest["branding"]["outro_seconds"] == pytest.approx(4.0)
        assert manifest["branding"]["padding_seconds"] == pytest.approx(5.0)
        assert manifest["cta"]["voiceover"] is True
        assert manifest["duration_budget"]["composed_seconds"] == pytest.approx(15.0)
        assert manifest["duration_budget"]["uploadable"] is True
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_render_card_png_opacity(tmp_path: Path):
    """Verify render_card_png respects opacity on the background while keeping accents crisp."""
    # 75% opacity
    card_75 = tmp_path / "card_75.png"
    render_card_png(
        card_75,
        size=(640, 360),
        title="NIGHTOWL",
        subtitle="Highlights",
        opacity=0.75,
        kind="intro",
    )
    img = Image.open(card_75)
    assert img.mode == "RGBA"
    # Background sample (middle left where no text or rule is drawn)
    bg_pixel = img.getpixel((20, 180))
    # Alpha should be around int(255 * 0.75) = 191
    assert 180 <= bg_pixel[3] <= 200

    # 0% opacity (transparent backdrop)
    card_0 = tmp_path / "card_0.png"
    render_card_png(
        card_0,
        size=(640, 360),
        title="NIGHTOWL",
        subtitle="Highlights",
        opacity=0.0,
        kind="intro",
    )
    img_0 = Image.open(card_0)
    assert img_0.getpixel((20, 180))[3] == 0

    # Top accent rule is always fully opaque (alpha = 255)
    rule_pixel = img_0.getpixel((320, 2))
    assert rule_pixel[3] == 255


def test_branding_plan_overlay_vs_bookend_padding(tmp_path: Path):
    """Verify overlay style does not add runtime padding, while bookend style adds card lengths."""
    # Overlay style -> padding_seconds is 0.0
    overlay_plan = build_branding_plan(
        config=BrandingConfig(
            enabled=True,
            style="overlay",
            opacity=0.75,
            intro_seconds=1.2,
            outro_seconds=2.0,
        ),
        sizes={"landscape": (640, 360)},
        card_dir=tmp_path / "overlay_cards",
    )
    assert overlay_plan is not None
    assert overlay_plan.padding_seconds == 0.0
    desc = overlay_plan.describe(total_duration=10.0)
    assert desc["style"] == "overlay"
    assert desc["opacity"] == 0.75
    assert desc["padding_seconds"] == 0.0
    assert desc["total_duration_seconds"] == 10.0

    # Bookend style -> padding_seconds is 1.2 + 2.0 = 3.2
    bookend_plan = build_branding_plan(
        config=BrandingConfig(
            enabled=True,
            style="bookend",
            intro_seconds=1.2,
            outro_seconds=2.0,
        ),
        sizes={"landscape": (640, 360)},
        card_dir=tmp_path / "bookend_cards",
    )
    assert bookend_plan is not None
    assert bookend_plan.padding_seconds == pytest.approx(3.2)


def test_render_overlay_branding_shows_gameplay_behind_cards(
    brand_assets: dict[str, Path], tmp_path: Path
):
    """Verify in-video overlay mode keeps gameplay moving behind translucent cards."""
    out_dir = tmp_path / "overlay_render"
    config = RenderConfig(
        landscape_width=640,
        landscape_height=360,
        vertical_width=360,
        vertical_height=640,
        modes=["landscape"],
        preferred_encoder="libx264",
        output_directory=str(out_dir),
        branding=BrandingConfig(
            enabled=True,
            style="overlay",
            opacity=0.70,
            intro=True,
            outro=True,
            intro_seconds=1.0,
            outro_seconds=1.0,
            intro_title="MATCH HIGHLIGHTS",
            outro_title="SUBSCRIBE",
        ),
    )
    engine = RenderEngine(config=config)
    result = engine.render_clip(
        source_path=brand_assets["video"],
        output_dir=out_dir,
        start_seconds=0.0,
        duration_seconds=3.0,
        clip_id="overlay_clip",
    )
    assert result.clip_id == "overlay_clip"
    out_file = out_dir / "landscape.mp4"
    assert out_file.exists()

    # In overlay mode, duration is NOT expanded by 2.0s of bookends
    duration = _probe_duration(out_file)
    assert 2.8 <= duration <= 3.2

    # Inspect frames with OpenCV
    cap_src = cv2.VideoCapture(str(brand_assets["video"]))
    cap_out = cv2.VideoCapture(str(out_file))

    # At t=0.5s (during intro card):
    cap_src.set(cv2.CAP_PROP_POS_MSEC, 500)
    cap_out.set(cv2.CAP_PROP_POS_MSEC, 500)
    ret1, f_src = cap_src.read()
    ret2, f_out = cap_out.read()
    assert ret1 and ret2

    # In background area of intro card (e.g. y in [100, 200], x in [50, 200]):
    # The output frame is NOT solid dark (#0B0D13 -> [19, 13, 11] in BGR)
    # The gameplay colors/motion are blended through at 70% opacity
    region_out = f_out[100:200, 50:200]
    region_src = f_src[100:200, 50:200]
    # Check that pixels are not clamped to pure static background color
    assert np.std(region_out) > 5.0, (
        "Card background is completely flat/solid, expected gameplay variation"
    )
    # Check difference with bare source reflects the overlay presence
    diff_intro = float(
        np.mean(np.abs(region_out.astype(float) - region_src.astype(float)))
    )
    assert diff_intro > 10.0, "Overlay was not detected during intro window"

    # At t=2.0s (outside intro and outro windows, clip is 3.0s, outro is last 1.0s [2.0-3.0s]):
    # Sample at t=1.5s (clean middle gameplay):
    cap_src.set(cv2.CAP_PROP_POS_MSEC, 1500)
    cap_out.set(cv2.CAP_PROP_POS_MSEC, 1500)
    ret3, f_src_mid = cap_src.read()
    ret4, f_out_mid = cap_out.read()
    assert ret3 and ret4
    diff_mid = float(
        np.mean(
            np.abs(
                f_out_mid[100:200, 50:200].astype(float)
                - f_src_mid[100:200, 50:200].astype(float)
            )
        )
    )
    # In middle window without cards, output matches source
    assert diff_mid < 1.0, f"Expected clean gameplay at t=1.5s, diff was {diff_mid}"

    cap_src.release()
    cap_out.release()

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["branding"]["enabled"] is True
    assert manifest["branding"]["style"] == "overlay"
    assert manifest["branding"]["opacity"] == 0.70
    assert manifest["branding"]["padding_seconds"] == 0.0
