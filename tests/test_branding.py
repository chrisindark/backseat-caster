"""Tests for branded intro/outro cards (Phase 10.5)."""

import json
import subprocess
from pathlib import Path

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
    """3-second 640x360 synthetic gameplay clip with audio."""
    temp_dir = tmp_path_factory.mktemp("brand_assets")
    video_path = temp_dir / "gameplay.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=3:size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
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


def test_render_card_png_draws_exact_pixels(tmp_path):
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

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path / "renders"))

        # The creator turns bookends on in the channel profile.
        ChannelProfileService.update(
            session,
            ChannelProfileUpdate(
                channel_name="@BackseatCaster",
                branding_enabled=True,
                branding_intro_seconds=1.0,
                branding_outro_seconds=2.0,
            ),
        )

        video = Video(
            id="brand_vod",
            title="Branded VOD",
            duration=3,
            duration_formatted="0:03",
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
                duration_seconds=2.0,
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
            5.0, abs=0.25
        )
        manifest = json.loads((clip_dir / "manifest.json").read_text())
        assert manifest["branding"]["enabled"] is True
        assert manifest["branding"]["channel_name"] == "@BackseatCaster"
        assert manifest["branding"]["intro_seconds"] == pytest.approx(1.0)
        assert manifest["branding"]["outro_seconds"] == pytest.approx(2.0)
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
