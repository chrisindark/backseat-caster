"""End-to-end tests for the in-video CTA overlay and voiceover path.

These cover the wiring that shipped without tests: the overlay must render even
when branded cards are off, sit where the preview endpoint draws it, clean up
its generated PNGs, and the voiceover must actually be audible in the mix.
"""

import json
import math
import struct
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.render_job import RenderJob
from app.models.video import Video
from app.rendering.branding import render_cta_overlay_png
from app.rendering.config import BrandingConfig, CtaConfig, RenderConfig
from app.rendering.engine import RenderEngine
from app.schemas.channel import ChannelProfileUpdate
from app.services.channel_profile import ChannelProfileService
from app.services.renders import RenderService

HEADLINE = "SUBSCRIBE & TAP THE BELL"
SUBTITLE = "Click the bell for more clips"


@pytest.fixture(scope="module")
def cta_assets(tmp_path_factory) -> dict[str, Path]:
    """4s synthetic clip (300Hz game tone) plus a 2s 440Hz 'voiceover'."""
    temp_dir = tmp_path_factory.mktemp("cta_assets")
    video = temp_dir / "gameplay.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360:d=4:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=4",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        capture_output=True,
        check=True,
    )
    narration = temp_dir / "narration.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(narration),
        ],
        capture_output=True,
        check=True,
    )
    return {"video": video, "narration": narration}


def _engine(branding: BrandingConfig, cta: CtaConfig) -> RenderEngine:
    return RenderEngine(
        RenderConfig(
            landscape_width=640,
            landscape_height=360,
            vertical_width=360,
            vertical_height=640,
            preferred_encoder="libx264",
            quality_preset="compact",
            branding=branding,
            cta=cta,
        )
    )


def _bright_rows(image_path: Path) -> list[int]:
    """Rows whose mean brightness is not black (the pill is the only light area)."""
    with Image.open(image_path) as image:
        gray = image.convert("L")
        width, height = gray.size
        rows = [
            sum(gray.crop((0, y, width, y + 1)).tobytes()) / width
            for y in range(height)
        ]
    return [y for y, value in enumerate(rows) if value > 5]


def _video_frame(video: Path, timestamp: float, target: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", str(target)],
        capture_output=True,
        check=True,
    )
    return target


def _tone_energy(
    path: Path, freq: float, start: float, duration: float = 0.6, rate: int = 48000
) -> float:
    """Goertzel magnitude for ``freq`` in a window, so tests need no numpy."""
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(rate),
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    if not samples:
        return 0.0
    coeff = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for sample in samples:
        s0 = sample + coeff * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    return math.sqrt(max(power, 0.0)) / len(samples)


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


class TestCtaOverlay:
    def test_overlay_renders_with_branded_cards_disabled(self, cta_assets, tmp_path):
        """The CTA is its own feature: no intro/outro card required."""
        branding = BrandingConfig(enabled=False, intro=False, outro=False)
        cta = CtaConfig(enabled=True, style="overlay", seconds=2.5)
        out_dir = tmp_path / "overlay_only"

        result = _engine(branding, cta).render_clip(
            source_path=cta_assets["video"],
            start_seconds=0.0,
            duration_seconds=4.0,
            output_dir=out_dir,
            clip_id="overlay_only",
            modes=["landscape"],
            branding=branding,
            overwrite=True,
        )

        assert result.branding_applied is False
        assert result.total_duration_seconds == pytest.approx(4.0, abs=0.1)

        late = _bright_rows(
            _video_frame(out_dir / "landscape.mp4", 3.4, tmp_path / "late.png")
        )
        early = _bright_rows(
            _video_frame(out_dir / "landscape.mp4", 0.5, tmp_path / "early.png")
        )
        assert late, "CTA pill missing from the final seconds of the clip"
        assert not early, "CTA pill leaked outside its overlay window"

        # Throwaway PNGs must not survive the render.
        assert not (out_dir / ".cta_overlay").exists()
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert manifest["branding"]["enabled"] is False
        assert manifest["cta"]["enabled"] is True
        assert manifest["cta"]["style"] == "overlay"
        assert manifest["cta"]["overlay"] is True
        assert manifest["cta"]["voiceover"] is False

    def test_overlay_matches_the_preview_placement(self, cta_assets, tmp_path):
        branding = BrandingConfig(enabled=False)
        cta = CtaConfig(
            enabled=True, style="overlay", seconds=2.5, headline=HEADLINE, subtitle=SUBTITLE
        )
        out_dir = tmp_path / "placement"

        _engine(branding, cta).render_clip(
            source_path=cta_assets["video"],
            start_seconds=0.0,
            duration_seconds=4.0,
            output_dir=out_dir,
            clip_id="placement",
            modes=["landscape"],
            branding=branding,
            overwrite=True,
        )

        preview = render_cta_overlay_png(
            tmp_path / "preview.png",
            size=(640, 360),
            headline=HEADLINE,
            subtitle=SUBTITLE,
            accent=branding.accent_color,
            text_color=branding.text_color,
        )
        expected = _bright_rows(preview)
        actual = _bright_rows(
            _video_frame(out_dir / "landscape.mp4", 3.4, tmp_path / "frame.png")
        )

        assert actual
        # Encoding can shift an edge by a pixel or two, but the pill must sit in
        # the same place the creator previewed.
        assert abs(min(actual) - min(expected)) <= 4
        assert abs(max(actual) - max(expected)) <= 4


class TestCtaVoiceover:
    def test_narration_is_audible_after_its_start_time(self, cta_assets, tmp_path):
        """Regression: the narration feeds sidechain and mix, so it must be split."""
        branding = BrandingConfig(enabled=False)
        out_dir = tmp_path / "narration"

        _engine(branding, CtaConfig()).render_clip(
            source_path=cta_assets["video"],
            start_seconds=0.0,
            duration_seconds=4.0,
            output_dir=out_dir,
            clip_id="narration",
            modes=["landscape"],
            narration_path=cta_assets["narration"],
            narration_start_seconds=1.5,
            audio_total_seconds=4.0,
            branding=branding,
            overwrite=True,
        )

        output = out_dir / "landscape.mp4"
        before = _tone_energy(output, 440, 0.4)
        during = _tone_energy(output, 440, 2.2)
        assert during > 100, f"voiceover not audible in the mix (energy={during:.1f})"
        assert during > before * 10

    def test_profile_cta_voiceover_renders_without_cards(
        self, monkeypatch, cta_assets, tmp_path
    ):
        """The channel profile alone (cards off) must produce an audible CTA."""
        from app.services.tts import TTSService

        captured: dict[str, object] = {}

        def fake_generate(cls, **kwargs):
            captured.update(kwargs)
            return cta_assets["narration"]

        monkeypatch.setattr(
            TTSService, "generate_cta_audio", classmethod(fake_generate)
        )
        monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path / "renders"))

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            ChannelProfileService.update(
                session,
                ChannelProfileUpdate(
                    branding_enabled=False,
                    branding_intro=False,
                    branding_outro=False,
                    cta_enabled=True,
                    cta_style="overlay",
                    cta_seconds=3.0,
                    max_clip_seconds=90.0,
                ),
            )
            session.add(
                Video(
                    id="cta_vod",
                    title="CTA VOD",
                    duration=4,
                    duration_formatted="0:04",
                    channel_name="Test",
                    channel_id="UC_test",
                    channel_url="https://youtube.com/@test",
                    webpage_url="https://youtube.com/watch?v=cta",
                    is_downloaded=True,
                    download_status="completed",
                    local_file_path=str(cta_assets["video"]),
                )
            )
            session.add(
                RenderJob(
                    id="cta_job",
                    clip_id="cta_job",
                    video_id="cta_vod",
                    status="pending",
                    progress=0.0,
                    start_seconds=0.0,
                    duration_seconds=3.0,
                    crop_preset="landscape",
                    modes="landscape",
                    encoder="libx264",
                )
            )
            session.commit()

            result = RenderService.execute_render_job("cta_job", db_session=session)
            assert result["status"] == "completed", result

            clip_dir = tmp_path / "renders" / "cta_job"
            output = clip_dir / "landscape.mp4"
            assert _probe_duration(output) == pytest.approx(3.0, abs=0.2)
            # Clip window (3s) is smaller than cta_seconds (3.0), so the audio
            # window is the clip itself.
            assert captured.get("max_seconds") == pytest.approx(3.0)
            assert _tone_energy(output, 440, 0.2) > 100

            rows = _bright_rows(
                _video_frame(output, 2.6, tmp_path / "late.png")
            )
            assert rows
            assert not (clip_dir / ".cta_overlay").exists()

            manifest = json.loads((clip_dir / "manifest.json").read_text())
            assert manifest["cta"]["style"] == "overlay"
            assert manifest["cta"]["voiceover"] is True
            assert manifest["cta"]["voiceover_start_seconds"] == pytest.approx(0.0)
            assert manifest["cta"]["speech_text"]
        finally:
            session.close()
            Base.metadata.drop_all(bind=engine)
