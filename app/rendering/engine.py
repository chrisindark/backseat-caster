"""Core rendering engine orchestrating FFmpeg commands and exports."""

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.rendering.audio import build_audio_filter_graph
from app.rendering.config import (
    CROP_PADDING_PRESETS,
    RenderConfig,
    default_render_config,
)
from app.rendering.filters import (
    build_landscape_filter,
    build_vertical_blur_filter,
    build_vertical_crop_filter,
)
from app.rendering.manifest import write_manifest
from app.rendering.probe import probe_media
from app.rendering.validator import validate_render_parameters

logger = logging.getLogger(__name__)


class RenderResult(BaseModel):
    """Result of clip render operation."""

    clip_id: str
    output_dir: str
    landscape_path: str
    vertical_blur_path: str
    vertical_crop_path: str
    manifest_path: str
    encoder_used: str
    render_duration_seconds: float
    files_created: list[str]
    local_landscape_path: str = ""
    local_vertical_blur_path: str = ""
    local_vertical_crop_path: str = ""
    local_manifest_path: str = ""


def detect_available_encoders() -> list[str]:
    """Inspect ffmpeg for available H.264 video encoders."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        encoders = []
        if "h264_videotoolbox" in proc.stdout:
            encoders.append("h264_videotoolbox")
        if "libx264" in proc.stdout:
            encoders.append("libx264")
        return encoders
    except Exception as e:
        logger.warning("Failed to query FFmpeg encoders: %s", e)
        return ["libx264"]


def select_encoder(config: RenderConfig) -> tuple[str, list[str]]:
    """
    Select optimal video encoder and high-quality encoding parameters.
    Guarantees broadcast/studio visual quality without pixelation.
    """
    available = detect_available_encoders()

    # Determine encoder
    if (
        config.preferred_encoder == "h264_videotoolbox"
        and "h264_videotoolbox" in available
    ):
        chosen = "h264_videotoolbox"
    elif config.preferred_encoder == "libx264" and "libx264" in available:
        chosen = "libx264"
    elif config.preferred_encoder == "auto":
        chosen = "h264_videotoolbox" if "h264_videotoolbox" in available else "libx264"
    else:
        chosen = "libx264" if "libx264" in available else "h264"

    # Assemble high-fidelity encoder flags
    if chosen == "h264_videotoolbox":
        flags = [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            config.videotoolbox_bitrate,
            "-maxrate",
            config.videotoolbox_maxrate,
            "-bufsize",
            config.videotoolbox_bufsize,
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        # libx264 studio quality
        flags = [
            "-c:v",
            "libx264",
            "-crf",
            str(config.libx264_crf),
            "-preset",
            config.libx264_preset,
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
        ]

    return chosen, flags


class RenderEngine:
    """Orchestrator for rendering landscape, vertical-blur, and vertical-crop clips."""

    def __init__(self, config: RenderConfig | None = None):
        self.config = config or default_render_config

    def _render_single_target(
        self,
        source_path: Path,
        start_seconds: float,
        duration_seconds: float,
        output_file: Path,
        video_filter: str,
        audio_filter: str | None,
        audio_label: str,
        encoder_flags: list[str],
        narration_path: Path | None = None,
    ):
        """Execute FFmpeg render command for a single target layout."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["ffmpeg", "-y"]  # Overwrite temp/individual target if invoked

        # Accurate input seeking on source video
        cmd.extend(
            [
                "-accurate_seek",
                "-ss",
                str(start_seconds),
                "-t",
                str(duration_seconds),
                "-i",
                str(source_path),
            ]
        )

        # If narration audio is provided, attach as input 1
        if narration_path:
            cmd.extend(
                [
                    "-i",
                    str(narration_path),
                ]
            )

        # Filter complex graph
        # Since input is already trimmed with -ss and -t, we apply video filter + audio filter
        full_filter_parts = []
        if video_filter.startswith("[0:v]"):
            full_filter_parts.append(video_filter)
            v_map = "[v_out]"
        else:
            full_filter_parts.append(f"[0:v]{video_filter}[v_out]")
            v_map = "[v_out]"

        if audio_filter:
            full_filter_parts.append(audio_filter)
            a_map = audio_label
        else:
            a_map = "0:a?"

        filter_complex_str = ";".join(full_filter_parts)

        cmd.extend(
            [
                "-filter_complex",
                filter_complex_str,
                "-map",
                v_map,
                "-map",
                a_map,
            ]
        )

        # Video encoding flags
        cmd.extend(encoder_flags)

        # Audio encoding flags (high-fidelity AAC)
        cmd.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                self.config.audio_bitrate,
                "-ar",
                str(self.config.audio_sample_rate),
            ]
        )

        # Output file
        cmd.append(str(output_file))

        logger.info(
            "Executing render command for %s: %s",
            output_file.name,
            " ".join(cmd[:12]) + " ...",
        )
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0:
            logger.error("FFmpeg render failed for %s:\n%s", output_file, proc.stderr)
            raise RuntimeError(
                f"FFmpeg failed while rendering {output_file.name}:\n{proc.stderr.strip()}"
            )

        if not output_file.exists() or output_file.stat().st_size == 0:
            raise RuntimeError(
                f"Render failed to create valid output file: {output_file}"
            )

    def _render_all_targets_single_pass(
        self,
        source_path: Path,
        start_seconds: float,
        duration_seconds: float,
        landscape_output: Path,
        vert_blur_output: Path,
        vert_crop_output: Path,
        crop_blur_padding: float,
        audio_filter: str | None,
        audio_label: str,
        encoder_flags: list[str],
        narration_path: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ):
        """
        Execute a unified, single-pass FFmpeg command rendering landscape,
        vertical_blur, and vertical_crop simultaneously.

        Eliminates 3x redundant decoding and audio mixing passes.
        """
        for out_file in (landscape_output, vert_blur_output, vert_crop_output):
            out_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-nostats",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
        ]

        # Accurate input seeking on source video
        cmd.extend(
            [
                "-accurate_seek",
                "-ss",
                str(start_seconds),
                "-t",
                str(duration_seconds),
                "-i",
                str(source_path),
            ]
        )

        # If narration audio is provided, attach as input 1
        if narration_path:
            cmd.extend(
                [
                    "-i",
                    str(narration_path),
                ]
            )

        # Build filtergraph:
        # 1. Split source video into 3 branches
        filter_parts = [
            "[0:v]split=3[v_in_land][v_in_blur][v_in_crop]",
            build_landscape_filter(
                width=self.config.landscape_width,
                height=self.config.landscape_height,
                input_label="v_in_land",
                output_label="v_out_land",
            ),
            build_vertical_blur_filter(
                width=self.config.vertical_width,
                height=self.config.vertical_height,
                input_label="v_in_blur",
                output_label="v_out_blur",
                prefix="v_b",
            ),
            build_vertical_crop_filter(
                width=self.config.vertical_width,
                height=self.config.vertical_height,
                blur_padding=crop_blur_padding,
                input_label="v_in_crop",
                output_label="v_out_crop",
                prefix="v_c",
            ),
        ]

        # 2. Audio mixing & splitting into 3 target streams
        if audio_filter:
            filter_parts.append(audio_filter)
            clean_audio_label = audio_label.strip("[]")
            filter_parts.append(
                f"[{clean_audio_label}]asplit=3[a_out_land][a_out_blur][a_out_crop]"
            )
        else:
            filter_parts.append("[0:a]asplit=3[a_out_land][a_out_blur][a_out_crop]")

        filter_complex_str = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex_str])

        audio_flags = [
            "-c:a",
            "aac",
            "-b:a",
            self.config.audio_bitrate,
            "-ar",
            str(self.config.audio_sample_rate),
        ]

        # Target 1: Landscape (1920x1080)
        cmd.extend(["-map", "[v_out_land]", "-map", "[a_out_land]"])
        cmd.extend(encoder_flags)
        cmd.extend(audio_flags)
        cmd.append(str(landscape_output))

        # Target 2: Vertical Blur (1080x1920)
        cmd.extend(["-map", "[v_out_blur]", "-map", "[a_out_blur]"])
        cmd.extend(encoder_flags)
        cmd.extend(audio_flags)
        cmd.append(str(vert_blur_output))

        # Target 3: Vertical Crop (1080x1920)
        cmd.extend(["-map", "[v_out_crop]", "-map", "[a_out_crop]"])
        cmd.extend(encoder_flags)
        cmd.extend(audio_flags)
        cmd.append(str(vert_crop_output))

        logger.info(
            "Executing single-pass multi-target render command for [%s, %s, %s]",
            landscape_output.name,
            vert_blur_output.name,
            vert_crop_output.name,
        )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stderr_output: list[str] = []

        def _drain_stderr():
            if proc.stderr:
                stderr_output.append(proc.stderr.read())

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        last_reported_pct = 20.0
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if (
                    line.startswith("out_time_us=")
                    and progress_callback
                    and duration_seconds > 0
                ):
                    val = line.split("=", 1)[1].strip()
                    if val.lstrip("-").isdigit():
                        elapsed_s = int(val) / 1_000_000.0
                        fraction = min(1.0, max(0.0, elapsed_s / duration_seconds))
                        current_pct = round(20.0 + (fraction * 65.0), 1)
                        if (
                            current_pct - last_reported_pct >= 5.0
                            or current_pct >= 85.0
                        ):
                            last_reported_pct = current_pct
                            progress_callback(
                                current_pct,
                                f"Rendering 3 formats (single-pass {int(fraction * 100)}%)",
                            )

        proc.wait()
        err_thread.join(timeout=2.0)
        err_msg = "".join(stderr_output).strip()

        if proc.returncode != 0:
            logger.error("FFmpeg single-pass render failed:\n%s", err_msg)
            raise RuntimeError(
                f"FFmpeg failed while rendering variants in single-pass:\n{err_msg}"
            )

        for target_file in (landscape_output, vert_blur_output, vert_crop_output):
            if not target_file.exists() or target_file.stat().st_size == 0:
                raise RuntimeError(
                    f"Render failed to create valid output file: {target_file}"
                )

    def render_clip(
        self,
        source_path: Path | str,
        start_seconds: float,
        duration_seconds: float,
        output_dir: Path | str,
        clip_id: str | None = None,
        narration_path: Path | str | None = None,
        overwrite: bool = False,
        crop_preset: str | None = None,
        crop_blur_padding: float | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> RenderResult:
        """
        Render a gameplay video window into 3 studio-quality exports in a single pass:
        1. landscape.mp4 (1920x1080 16:9)
        2. vertical_blur.mp4 (1080x1920 9:16 blurred top/bottom)
        3. vertical_crop.mp4 (1080x1920 9:16 center cropped)
        + manifest.json
        """
        start_time_perf = time.perf_counter()
        source_file = Path(source_path).resolve()
        out_directory = Path(output_dir).resolve()
        narr_file = Path(narration_path).resolve() if narration_path else None

        if not clip_id:
            clip_id = f"clip_{int(time.time())}_{source_file.stem}"

        out_directory.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(5.0, "Analyzing source media")

        # 1. Probe source video
        probe = probe_media(source_file)

        # 2. Validate parameters & overwrite safety
        validate_render_parameters(
            probe=probe,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            output_dir=out_directory,
            narration_path=narr_file,
            overwrite=overwrite,
        )

        # 3. Select encoder with studio quality settings
        encoder_name, encoder_flags = select_encoder(self.config)
        logger.info(
            "Selected video encoder: %s (flags: %s)", encoder_name, encoder_flags
        )

        # 4. Construct Audio Filter Graph
        audio_filter, audio_label = build_audio_filter_graph(
            start_seconds=0,
            duration_seconds=duration_seconds,
            has_source_audio=probe.has_audio,
            has_narration=narr_file is not None,
            ducked_game_gain=self.config.ducked_game_gain,
            narration_gain=self.config.narration_gain,
            limiter_enabled=self.config.limiter_enabled,
        )

        outputs_meta: dict[str, dict[str, Any]] = {}
        files_created: list[str] = []

        # 5. Output file paths
        landscape_out = out_directory / "landscape.mp4"
        vert_blur_out = out_directory / "vertical_blur.mp4"
        vert_crop_out = out_directory / "vertical_crop.mp4"

        # Resolve vertical crop layout preset and padding
        if crop_blur_padding is not None:
            effective_crop_padding = max(0.0, min(0.6, float(crop_blur_padding)))
            effective_preset = crop_preset or "custom"
        elif crop_preset and crop_preset in CROP_PADDING_PRESETS:
            effective_crop_padding = CROP_PADDING_PRESETS[crop_preset]
            effective_preset = crop_preset
        else:
            effective_crop_padding = self.config.crop_blur_padding
            effective_preset = self.config.crop_preset

        # 6. Execute Single-Pass Multi-Target Render
        if progress_callback:
            progress_callback(20.0, "Rendering 3 formats (single-pass)")

        self._render_all_targets_single_pass(
            source_path=source_file,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            landscape_output=landscape_out,
            vert_blur_output=vert_blur_out,
            vert_crop_output=vert_crop_out,
            crop_blur_padding=effective_crop_padding,
            audio_filter=audio_filter,
            audio_label=audio_label,
            encoder_flags=encoder_flags,
            narration_path=narr_file,
            progress_callback=progress_callback,
        )

        api_prefix = self.config.api_prefix
        outputs_meta["landscape"] = {
            "path": f"{api_prefix}/renders/{clip_id}/stream/landscape",
            "file_path": str(landscape_out),
            "width": self.config.landscape_width,
            "height": self.config.landscape_height,
            "duration": duration_seconds,
            "size_bytes": landscape_out.stat().st_size,
            "encoder": encoder_name,
        }
        files_created.append(str(landscape_out))

        outputs_meta["vertical_blur"] = {
            "path": f"{api_prefix}/renders/{clip_id}/stream/vertical_blur",
            "file_path": str(vert_blur_out),
            "width": self.config.vertical_width,
            "height": self.config.vertical_height,
            "duration": duration_seconds,
            "size_bytes": vert_blur_out.stat().st_size,
            "encoder": encoder_name,
        }
        files_created.append(str(vert_blur_out))

        outputs_meta["vertical_crop"] = {
            "path": f"{api_prefix}/renders/{clip_id}/stream/vertical_crop",
            "file_path": str(vert_crop_out),
            "width": self.config.vertical_width,
            "height": self.config.vertical_height,
            "duration": duration_seconds,
            "size_bytes": vert_crop_out.stat().st_size,
            "encoder": encoder_name,
            "crop_preset": effective_preset,
            "crop_blur_padding": effective_crop_padding,
        }
        files_created.append(str(vert_crop_out))

        # 7. Write Manifest
        if progress_callback:
            progress_callback(90.0, "Generating audit manifest")

        end_time_perf = time.perf_counter()
        render_duration = end_time_perf - start_time_perf
        manifest_file = write_manifest(
            output_dir=out_directory,
            clip_id=clip_id,
            source_probe=probe,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            outputs=outputs_meta,
            narration_path=narr_file,
            render_duration=render_duration,
            api_prefix=api_prefix,
            crop_preset=effective_preset,
            crop_blur_padding=effective_crop_padding,
        )
        files_created.append(str(manifest_file))

        if progress_callback:
            progress_callback(100.0, "Completed")

        logger.info(
            "Successfully completed clip render %s in %.2fs (single-pass multi-target)",
            clip_id,
            render_duration,
        )
        return RenderResult(
            clip_id=clip_id,
            output_dir=str(out_directory),
            landscape_path=f"{api_prefix}/renders/{clip_id}/stream/landscape",
            vertical_blur_path=f"{api_prefix}/renders/{clip_id}/stream/vertical_blur",
            vertical_crop_path=f"{api_prefix}/renders/{clip_id}/stream/vertical_crop",
            manifest_path=f"{api_prefix}/renders/{clip_id}/stream/manifest",
            encoder_used=encoder_name,
            render_duration_seconds=render_duration,
            files_created=files_created,
            local_landscape_path=str(landscape_out),
            local_vertical_blur_path=str(vert_blur_out),
            local_vertical_crop_path=str(vert_crop_out),
            local_manifest_path=str(manifest_file),
        )
