"""Core rendering engine orchestrating FFmpeg commands and exports."""

import functools
import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.rendering.audio import build_audio_filter_graph
from app.rendering.branding import (
    BrandingPlan,
    build_branding_audio_filter,
    build_branding_plan,
    build_card_video_filter,
    build_concat_filter,
    render_cta_overlay_png,
)
from app.rendering.config import (
    CROP_PADDING_PRESETS,
    BrandingConfig,
    DurationBudget,
    RenderConfig,
    default_render_config,
)
from app.rendering.filters import (
    build_landscape_filter,
    build_vertical_blur_filter,
    build_vertical_crop_filter,
    build_watermark_filter,
)
from app.rendering.manifest import write_manifest
from app.rendering.probe import probe_media
from app.rendering.validator import validate_render_parameters

logger = logging.getLogger(__name__)


class RenderResult(BaseModel):
    """Result of clip render operation."""

    clip_id: str
    output_dir: str
    landscape_path: str = ""
    vertical_blur_path: str = ""
    vertical_crop_path: str = ""
    manifest_path: str
    encoder_used: str
    render_duration_seconds: float
    files_created: list[str]
    local_landscape_path: str = ""
    local_vertical_blur_path: str = ""
    local_vertical_crop_path: str = ""
    local_manifest_path: str = ""
    modes: list[str] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    local_outputs: dict[str, str] = Field(default_factory=dict)
    effective_duration_seconds: float = 0.0
    requested_duration_seconds: float = 0.0
    clamped: bool = False
    quality_preset: str | None = None
    watermark_applied: bool = False
    # Branded bookends (Phase 10.5)
    total_duration_seconds: float = 0.0
    branding_applied: bool = False
    branding_intro_seconds: float = 0.0
    branding_outro_seconds: float = 0.0


@functools.lru_cache(maxsize=1)
def detect_available_encoders() -> list[str]:
    """Inspect ffmpeg for available H.264 video encoders."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
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

    def _duration_budget(self, *, bookend_seconds: float = 0.0) -> DurationBudget:
        """Upload budget for this render (ceiling minus the cards it adds)."""
        return DurationBudget(
            max_seconds=self.config.max_total_seconds,
            bookend_seconds=bookend_seconds,
        )

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
            capture_output=True,
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
        targets: dict[str, Path] | Path,
        crop_blur_padding: float = 0.3333,
        audio_filter: str | None = None,
        audio_label: str = "[a_out]",
        encoder_flags: list[str] | None = None,
        narration_path: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        branding_plan: BrandingPlan | None = None,
        source_fps: float = 30.0,
        *args,
        **kwargs,
    ):
        """
        Execute a unified, single-pass FFmpeg command rendering all requested
        targets simultaneously. Eliminates redundant decoding and audio mixing passes.
        """
        # Backward-compatibility check: if positional arguments passed old Path objects
        if isinstance(targets, Path):
            landscape_out = targets
            vert_blur_out = (
                crop_blur_padding if isinstance(crop_blur_padding, Path) else args[0]
            )
            vert_crop_out = audio_filter if isinstance(audio_filter, Path) else args[1]
            actual_padding = (
                audio_label if isinstance(audio_label, (int, float)) else args[2]
            )
            actual_audio_filter = (
                encoder_flags if isinstance(encoder_flags, str) else args[3]
            )
            actual_audio_label = (
                narration_path if isinstance(narration_path, str) else args[4]
            )
            actual_encoder_flags = (
                progress_callback if isinstance(progress_callback, list) else args[5]
            )
            actual_narration = kwargs.get("narration_path")
            actual_callback = kwargs.get("progress_callback")

            target_dict = {
                "landscape": landscape_out,
                "vertical_blur": vert_blur_out,
                "vertical_crop": vert_crop_out,
            }
            return self._render_all_targets_single_pass(
                source_path=source_path,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                targets=target_dict,
                crop_blur_padding=float(actual_padding),
                audio_filter=actual_audio_filter,
                audio_label=actual_audio_label,
                encoder_flags=actual_encoder_flags or [],
                narration_path=actual_narration,
                progress_callback=actual_callback,
            )

        target_dict = targets
        encoder_flags = encoder_flags or []
        for out_file in target_dict.values():
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

        modes = list(target_dict.keys())
        n_targets = len(modes)

        # Branded bookends: each card is a still image looped for its duration and
        # appended as an extra input, so one pass still renders every target.
        branding_active = bool(branding_plan and branding_plan.active)
        card_inputs: dict[str, tuple[int | None, int | None]] = {}
        progress_duration = duration_seconds
        next_input_index = 1 + (1 if narration_path else 0)
        if branding_active and branding_plan is not None:
            for mode_name in modes:
                intro_card = branding_plan.intro_card(mode_name)
                outro_card = branding_plan.outro_card(mode_name)
                intro_idx: int | None = None
                outro_idx: int | None = None
                if intro_card:
                    cmd.extend(
                        [
                            "-loop",
                            "1",
                            "-t",
                            f"{branding_plan.intro_seconds:.3f}",
                            "-i",
                            str(intro_card),
                        ]
                    )
                    intro_idx = next_input_index
                    next_input_index += 1
                if outro_card:
                    cmd.extend(
                        [
                            "-loop",
                            "1",
                            "-t",
                            f"{branding_plan.outro_seconds:.3f}",
                            "-i",
                            str(outro_card),
                        ]
                    )
                    outro_idx = next_input_index
                    next_input_index += 1
                card_inputs[mode_name] = (intro_idx, outro_idx)
            progress_duration = duration_seconds + branding_plan.padding_seconds

        # CTA in-video overlay (Mode A): a transparent lower-third pill shown
        # for the last `cta_seconds` of the gameplay segment.
        cta_overlay_active = (
            bool(self.config.cta.enabled) and self.config.cta.style == "overlay"
        )
        overlay_inputs: dict[str, int] = {}
        overlay_dir: Path | None = None
        if cta_overlay_active:
            _out_dir = (
                list(targets.values())[0].parent
                if isinstance(targets, dict) and targets
                else None
            )
            if _out_dir is None:
                _out_dir = Path(".")
            overlay_dir = _out_dir / ".cta_overlay"
            overlay_dir.mkdir(parents=True, exist_ok=True)
            overlay_seconds = float(self.config.cta.seconds)
            for mode_name in modes:
                is_landscape = mode_name == "landscape"
                ow = (
                    self.config.landscape_width
                    if is_landscape
                    else self.config.vertical_width
                )
                oh = (
                    self.config.landscape_height
                    if is_landscape
                    else self.config.vertical_height
                )
                overlay_path = render_cta_overlay_png(
                    overlay_dir / f"{mode_name}_cta.png",
                    size=(ow, oh),
                    headline=self.config.cta.headline,
                    subtitle=self.config.cta.subtitle,
                    accent=self.config.branding.accent_color,
                    text_color=self.config.branding.text_color,
                    font_path=self.config.branding.font_path,
                )
                cmd.extend(
                    [
                        "-loop",
                        "1",
                        "-t",
                        f"{overlay_seconds:.3f}",
                        "-i",
                        str(overlay_path),
                    ]
                )
                overlay_inputs[mode_name] = next_input_index
                next_input_index += 1

        # Tier 3: channel watermark. One still-image input per target keeps the
        # single-pass render intact and lets each output scale the logo for its
        # own orientation.
        watermark_active = bool(self.config.watermark.active)
        watermark_inputs: dict[str, int] = {}
        if watermark_active and self.config.watermark.path:
            # The logo only covers the gameplay segment (not the branded cards),
            # so its input length stays tied to the clip window. Looping it for
            # the composed length instead would make `overlay` extend the main
            # stream and silently lengthen every output.
            logo_duration = max(0.1, duration_seconds)
            for mode_name in modes:
                cmd.extend(
                    [
                        "-loop",
                        "1",
                        "-t",
                        f"{logo_duration:.3f}",
                        "-i",
                        str(self.config.watermark.path),
                    ]
                )
                watermark_inputs[mode_name] = next_input_index
                next_input_index += 1

        # Build filtergraph:
        filter_parts = []

        # 1. Video splitting if n_targets > 1
        if n_targets > 1:
            split_labels = "".join(f"[v_in_{i}]" for i in range(n_targets))
            filter_parts.append(f"[0:v]split={n_targets}{split_labels}")

        for i, mode in enumerate(modes):
            v_in = f"v_in_{i}" if n_targets > 1 else "0:v"
            v_out = f"v_out_{i}"
            p = f"v_{i}"

            if mode == "landscape":
                filter_parts.append(
                    build_landscape_filter(
                        width=self.config.landscape_width,
                        height=self.config.landscape_height,
                        input_label=v_in,
                        output_label=v_out,
                    )
                )
            elif mode == "vertical_blur":
                filter_parts.append(
                    build_vertical_blur_filter(
                        width=self.config.vertical_width,
                        height=self.config.vertical_height,
                        input_label=v_in,
                        output_label=v_out,
                        prefix=p,
                    )
                )
            elif mode == "third_person":
                filter_parts.append(
                    build_vertical_crop_filter(
                        width=self.config.vertical_width,
                        height=self.config.vertical_height,
                        blur_padding=0.3333,
                        input_label=v_in,
                        output_label=v_out,
                        prefix=p,
                    )
                )
            elif mode == "direct_crop":
                filter_parts.append(
                    build_vertical_crop_filter(
                        width=self.config.vertical_width,
                        height=self.config.vertical_height,
                        blur_padding=0.0,
                        input_label=v_in,
                        output_label=v_out,
                        prefix=p,
                    )
                )
            elif mode == "cinematic":
                filter_parts.append(
                    build_vertical_crop_filter(
                        width=self.config.vertical_width,
                        height=self.config.vertical_height,
                        blur_padding=0.25,
                        input_label=v_in,
                        output_label=v_out,
                        prefix=p,
                    )
                )
            elif mode == "custom" or mode == "vertical_crop":
                filter_parts.append(
                    build_vertical_crop_filter(
                        width=self.config.vertical_width,
                        height=self.config.vertical_height,
                        blur_padding=crop_blur_padding,
                        input_label=v_in,
                        output_label=v_out,
                        prefix=p,
                    )
                )
            else:
                filter_parts.append(
                    build_landscape_filter(
                        width=self.config.landscape_width,
                        height=self.config.landscape_height,
                        input_label=v_in,
                        output_label=v_out,
                    )
                )

        # 1b. Apply the channel watermark, then wrap each target in its
        # branded cards when enabled.
        video_map_labels: list[str] = []
        for i, mode_name in enumerate(modes):
            v_out = f"v_out_{i}"
            v_composed = v_out
            if watermark_active and mode_name in watermark_inputs:
                is_landscape_mode = mode_name == "landscape"
                wm_width = (
                    self.config.landscape_width
                    if is_landscape_mode
                    else self.config.vertical_width
                )
                wm_height = (
                    self.config.landscape_height
                    if is_landscape_mode
                    else self.config.vertical_height
                )
                v_composed = f"v_wm_{i}"
                filter_parts.append(
                    build_watermark_filter(
                        watermark_input=f"{watermark_inputs[mode_name]}:v",
                        main_input=v_out,
                        output_label=v_composed,
                        width=wm_width,
                        height=wm_height,
                        position=self.config.watermark.position,
                        opacity=self.config.watermark.opacity,
                        scale=self.config.watermark.scale,
                        margin=self.config.watermark.margin,
                        prefix=f"wm_{i}",
                    )
                )

            if not branding_active:
                video_map_labels.append(v_composed)
                continue

            intro_idx, outro_idx = card_inputs.get(mode_name, (None, None))
            is_landscape = mode_name == "landscape"
            card_w = (
                self.config.landscape_width
                if is_landscape
                else self.config.vertical_width
            )
            card_h = (
                self.config.landscape_height
                if is_landscape
                else self.config.vertical_height
            )

            intro_label: str | None = None
            outro_label: str | None = None
            if intro_idx is not None:
                intro_label = f"brand_intro_{i}"
                filter_parts.append(
                    build_card_video_filter(
                        input_label=f"{intro_idx}:v",
                        output_label=intro_label,
                        width=card_w,
                        height=card_h,
                        fps=source_fps,
                    )
                )
            if outro_idx is not None:
                outro_label = f"brand_outro_{i}"
                filter_parts.append(
                    build_card_video_filter(
                        input_label=f"{outro_idx}:v",
                        output_label=outro_label,
                        width=card_w,
                        height=card_h,
                        fps=source_fps,
                    )
                )

            # CTA in-video overlay: composite the lower-third pill onto the
            # gameplay segment for the last `cta_seconds` of the clip.
            cta_overlay_idx = overlay_inputs.get(mode_name)
            if cta_overlay_idx is not None:
                start_time = max(0.0, duration_seconds - float(self.config.cta.seconds))
                overlay_label = f"v_cta_overlay_{i}"
                filter_parts.append(
                    f"[{v_composed}][{cta_overlay_idx}:v]overlay="
                    f"(W-w)/2:H-h-{max(8, oh // 20)}:"
                    f"enable='between(t,{start_time:.3f},{duration_seconds:.3f})'"
                    f"[{overlay_label}]"
                )
                v_composed = overlay_label

            # concat refuses links whose SAR differs, and the crop/blur filters
            # inherit the source's (often non-square) sample aspect ratio while
            # the cards are forced to 1:1. Normalise the clip segment to match.
            main_label = f"v_brand_main_{i}"
            filter_parts.append(f"[{v_composed}]setsar=1[{main_label}]")

            final_label = f"v_final_{i}"
            filter_parts.append(
                build_concat_filter(
                    intro_label=intro_label,
                    main_label=main_label,
                    outro_label=outro_label,
                    output_label=final_label,
                )
            )
            video_map_labels.append(final_label)

        # 2. Audio mixing & splitting into n_targets streams
        clean_audio_label = audio_label.strip("[]") if audio_filter else "0:a"
        if audio_filter:
            filter_parts.append(audio_filter)

        # Branded cards carry no audio, so pad the clip audio with silence to keep
        # lip-sync aligned behind the intro and the outro.
        if branding_active and branding_plan is not None and audio_filter:
            filter_parts.append(
                build_branding_audio_filter(
                    input_label=clean_audio_label,
                    output_label="a_branded",
                    intro_seconds=branding_plan.intro_seconds,
                    main_seconds=duration_seconds,
                    outro_seconds=branding_plan.outro_seconds,
                )
            )
            clean_audio_label = "a_branded"

        if n_targets > 1:
            asplit_labels = "".join(f"[a_out_{i}]" for i in range(n_targets))
            filter_parts.append(
                f"[{clean_audio_label}]asplit={n_targets}{asplit_labels}"
            )
        else:
            filter_parts.append(f"[{clean_audio_label}]anull[a_out_0]")

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

        # Map each target format to output file
        for i, mode in enumerate(modes):
            target_file = target_dict[mode]
            cmd.extend(
                [
                    "-map",
                    f"[{video_map_labels[i]}]",
                    "-map",
                    f"[a_out_{i}]",
                ]
            )
            cmd.extend(encoder_flags)
            cmd.extend(audio_flags)
            cmd.append(str(target_file))

        logger.info(
            "Executing single-pass multi-target render command for %d formats: [%s]",
            n_targets,
            ", ".join(target_dict.keys()),
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
        try:
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if (
                        line.startswith("out_time_us=")
                        and progress_callback
                        and progress_duration > 0
                    ):
                        val = line.split("=", 1)[1].strip()
                        if val.lstrip("-").isdigit():
                            elapsed_s = int(val) / 1_000_000.0
                            fraction = min(1.0, max(0.0, elapsed_s / progress_duration))
                            current_pct = round(20.0 + (fraction * 65.0), 1)
                            if (
                                current_pct - last_reported_pct >= 5.0
                                or current_pct >= 85.0
                            ):
                                last_reported_pct = current_pct
                                progress_callback(
                                    current_pct,
                                    f"Rendering {n_targets} format(s) (single-pass {int(fraction * 100)}%)",
                                )

            proc.wait()
        except BaseException:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
                    proc.wait()
            raise
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass
            err_thread.join(timeout=2.0)

        err_msg = "".join(stderr_output).strip()

        if proc.returncode != 0:
            logger.error("FFmpeg single-pass render failed:\n%s", err_msg)
            raise RuntimeError(
                f"FFmpeg failed while rendering variants in single-pass:\n{err_msg}"
            )

        for mode, target_file in target_dict.items():
            if not target_file.exists() or target_file.stat().st_size == 0:
                raise RuntimeError(
                    f"Render failed to create valid output file for '{mode}': {target_file}"
                )

    def render_clip(
        self,
        source_path: Path | str,
        start_seconds: float,
        duration_seconds: float,
        output_dir: Path | str,
        clip_id: str | None = None,
        narration_path: Path | str | None = None,
        narration_start_seconds: float = 0.0,
        audio_total_seconds: float | None = None,
        overwrite: bool = False,
        crop_preset: str | None = None,
        crop_blur_padding: float | None = None,
        modes: list[str] | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        normalize_audio: bool | None = None,
        target_lufs: float | None = None,
        clamp_to_duration: bool | None = None,
        branding: BrandingConfig | None = None,
    ) -> RenderResult:
        """
        Render a gameplay video window into selected high-fidelity exports in a single pass.
        Supports any combination of the 6 clipping modes:
        - landscape (1920x1080 16:9 master)
        - vertical_blur (1080x1920 9:16 blurred background)
        - third_person (1080x1920 9:16 33.3% padded crop)
        - direct_crop (1080x1920 9:16 full center crop)
        - cinematic (1080x1920 9:16 25% padded crop)
        - custom (1080x1920 9:16 custom blur padding)
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

        # 2. Validate parameters & overwrite safety (with optional duration clamping)
        should_clamp = (
            clamp_to_duration
            if clamp_to_duration is not None
            else self.config.clamp_to_duration
        )
        effective_duration = validate_render_parameters(
            probe=probe,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            output_dir=out_directory,
            narration_path=narr_file,
            overwrite=overwrite,
            modes=modes,
            clamp_duration=should_clamp,
            min_duration=self.config.min_clip_duration,
        )
        is_clamped = abs(effective_duration - duration_seconds) > 0.001

        # 3. Select encoder with studio quality settings
        encoder_name, encoder_flags = select_encoder(self.config)
        logger.info(
            "Selected video encoder: %s (flags: %s)", encoder_name, encoder_flags
        )

        # 4. Construct Audio Filter Graph
        effective_normalize_audio = (
            normalize_audio
            if normalize_audio is not None
            else self.config.normalize_audio
        )
        effective_target_lufs = (
            target_lufs if target_lufs is not None else self.config.target_lufs
        )

        audio_filter, audio_label = build_audio_filter_graph(
            start_seconds=0,
            duration_seconds=effective_duration,
            has_source_audio=probe.has_audio,
            has_narration=narr_file is not None,
            narration_start_seconds=narration_start_seconds,
            audio_total_seconds=audio_total_seconds,
            ducked_game_gain=self.config.ducked_game_gain,
            narration_gain=self.config.narration_gain,
            limiter_enabled=self.config.limiter_enabled,
            normalize_audio=effective_normalize_audio,
            target_lufs=effective_target_lufs,
            loudnorm_true_peak=self.config.loudnorm_true_peak,
            loudnorm_lra=self.config.loudnorm_lra,
        )

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

        # Resolve modes to render
        if not modes:
            modes = [crop_preset or effective_preset or "third_person"]

        normalized_modes: list[str] = []
        for m in modes:
            if m not in normalized_modes and m in (
                "landscape",
                "vertical_blur",
                "third_person",
                "direct_crop",
                "cinematic",
                "custom",
                "vertical_crop",
            ):
                normalized_modes.append(m)

        if not normalized_modes:
            normalized_modes = [effective_preset or "third_person"]

        # Build output targets dictionary
        targets: dict[str, Path] = {
            m: out_directory / f"{m}.mp4" for m in normalized_modes
        }

        # 4b. Rasterise branded intro/outro cards for every target size
        effective_branding = branding if branding is not None else self.config.branding
        card_sizes: dict[str, tuple[int, int]] = {}
        for m in normalized_modes:
            is_landscape_mode = m == "landscape"
            card_sizes[m] = (
                self.config.landscape_width
                if is_landscape_mode
                else self.config.vertical_width,
                self.config.landscape_height
                if is_landscape_mode
                else self.config.vertical_height,
            )

        branding_plan = (
            build_branding_plan(
                config=effective_branding,
                sizes=card_sizes,
                card_dir=out_directory / ".branding_cards",
            )
            if effective_branding is not None
            else None
        )

        total_duration = effective_duration + (
            branding_plan.padding_seconds if branding_plan else 0.0
        )

        duration_budget = self._duration_budget(
            bookend_seconds=branding_plan.padding_seconds if branding_plan else 0.0
        )
        if branding_plan is not None and not duration_budget.fits(effective_duration):
            logger.warning(
                "Branded clip exceeds the upload ceiling: %s",
                duration_budget.over_ceiling_message(effective_duration),
            )

        # 5. Execute Single-Pass Multi-Target Render
        if progress_callback:
            progress_callback(
                20.0, f"Rendering {len(normalized_modes)} format(s) (single-pass)"
            )

        try:
            self._render_all_targets_single_pass(
                source_path=source_file,
                start_seconds=start_seconds,
                duration_seconds=effective_duration,
                targets=targets,
                crop_blur_padding=effective_crop_padding,
                audio_filter=audio_filter,
                audio_label=audio_label,
                encoder_flags=encoder_flags,
                narration_path=narr_file,
                progress_callback=progress_callback,
                branding_plan=branding_plan,
                source_fps=probe.fps or 30.0,
            )
        finally:
            if branding_plan is not None:
                branding_plan.cleanup()
            _overlay_dir = locals().get("overlay_dir")
            if _overlay_dir is not None and _overlay_dir.exists():
                for leftover in _overlay_dir.glob("*.png"):
                    try:
                        leftover.unlink()
                    except OSError:
                        pass
                try:
                    _overlay_dir.rmdir()
                except OSError:
                    pass

        api_prefix = self.config.api_prefix
        outputs_meta: dict[str, dict[str, Any]] = {}
        files_created: list[str] = []

        for m in normalized_modes:
            target_out = targets[m]
            is_landscape = m == "landscape"
            w = (
                self.config.landscape_width
                if is_landscape
                else self.config.vertical_width
            )
            h = (
                self.config.landscape_height
                if is_landscape
                else self.config.vertical_height
            )

            meta: dict[str, Any] = {
                "path": f"{api_prefix}/renders/{clip_id}/stream/{m}",
                "file_path": str(target_out),
                "width": w,
                "height": h,
                "duration": total_duration,
                "size_bytes": target_out.stat().st_size,
                "encoder": encoder_name,
            }
            if m in (
                "third_person",
                "direct_crop",
                "cinematic",
                "custom",
                "vertical_crop",
            ):
                meta["crop_preset"] = m if m != "vertical_crop" else effective_preset
                meta["crop_blur_padding"] = (
                    CROP_PADDING_PRESETS.get(m, effective_crop_padding)
                    if m != "custom"
                    else effective_crop_padding
                )

            outputs_meta[m] = meta
            files_created.append(str(target_out))

        # Backward compatibility: ensure vertical_crop.mp4 exists on disk if any crop mode was created
        vert_crop_out = out_directory / "vertical_crop.mp4"
        primary_crop_mode = None
        for cand in (
            "third_person",
            "direct_crop",
            "cinematic",
            "custom",
            "vertical_crop",
        ):
            if cand in normalized_modes:
                primary_crop_mode = cand
                break

        if primary_crop_mode and not vert_crop_out.exists():
            try:
                os.link(targets[primary_crop_mode], vert_crop_out)
            except OSError:
                shutil.copyfile(targets[primary_crop_mode], vert_crop_out)
            files_created.append(str(vert_crop_out))
            if "vertical_crop" not in outputs_meta:
                outputs_meta["vertical_crop"] = {
                    **outputs_meta[primary_crop_mode],
                    "path": f"{api_prefix}/renders/{clip_id}/stream/vertical_crop",
                    "file_path": str(vert_crop_out),
                }

        # 6. Write Manifest
        if progress_callback:
            progress_callback(90.0, "Generating audit manifest")

        end_time_perf = time.perf_counter()
        render_duration = end_time_perf - start_time_perf
        manifest_file = write_manifest(
            output_dir=out_directory,
            clip_id=clip_id,
            source_probe=probe,
            start_seconds=start_seconds,
            duration_seconds=effective_duration,
            outputs=outputs_meta,
            narration_path=narr_file,
            render_duration=render_duration,
            api_prefix=api_prefix,
            crop_preset=effective_preset,
            crop_blur_padding=effective_crop_padding,
            modes=normalized_modes,
            normalize_audio=effective_normalize_audio,
            target_lufs=effective_target_lufs,
            requested_duration_seconds=duration_seconds,
            clamped=is_clamped,
            quality_preset=self.config.quality_preset,
            watermark=self.config.watermark.describe(),
            branding=(
                branding_plan.describe(total_duration)
                if branding_plan is not None
                else effective_branding.describe()
                if effective_branding is not None
                else {"enabled": False}
            ),
            duration_budget=duration_budget.describe_composed(total_duration),
        )
        files_created.append(str(manifest_file))

        if progress_callback:
            progress_callback(100.0, "Completed")

        logger.info(
            "Successfully completed clip render %s (%d formats) in %.2fs (single-pass multi-target)",
            clip_id,
            len(normalized_modes),
            render_duration,
        )

        land_file = targets.get("landscape")
        blur_file = targets.get("vertical_blur")
        crop_file = targets.get("vertical_crop") or (
            vert_crop_out if vert_crop_out.exists() else None
        )

        landscape_stream = (
            f"{api_prefix}/renders/{clip_id}/stream/landscape" if land_file else ""
        )
        vertical_blur_stream = (
            f"{api_prefix}/renders/{clip_id}/stream/vertical_blur" if blur_file else ""
        )
        vertical_crop_stream = (
            f"{api_prefix}/renders/{clip_id}/stream/vertical_crop"
            if crop_file
            else (
                f"{api_prefix}/renders/{clip_id}/stream/{primary_crop_mode}"
                if primary_crop_mode
                else ""
            )
        )

        stream_outputs = {
            m: f"{api_prefix}/renders/{clip_id}/stream/{m}" for m in normalized_modes
        }
        local_outputs = {m: str(targets[m]) for m in normalized_modes}

        return RenderResult(
            clip_id=clip_id,
            output_dir=str(out_directory),
            landscape_path=landscape_stream,
            vertical_blur_path=vertical_blur_stream,
            vertical_crop_path=vertical_crop_stream,
            manifest_path=f"{api_prefix}/renders/{clip_id}/stream/manifest",
            encoder_used=encoder_name,
            render_duration_seconds=render_duration,
            files_created=files_created,
            local_landscape_path=str(land_file) if land_file else "",
            local_vertical_blur_path=str(blur_file) if blur_file else "",
            local_vertical_crop_path=str(crop_file) if crop_file else "",
            local_manifest_path=str(manifest_file),
            modes=normalized_modes,
            outputs=stream_outputs,
            local_outputs=local_outputs,
            effective_duration_seconds=effective_duration,
            requested_duration_seconds=duration_seconds,
            clamped=is_clamped,
            quality_preset=self.config.quality_preset,
            watermark_applied=self.config.watermark.active,
            total_duration_seconds=total_duration,
            branding_applied=branding_plan is not None,
            branding_intro_seconds=branding_plan.intro_seconds
            if branding_plan
            else 0.0,
            branding_outro_seconds=branding_plan.outro_seconds
            if branding_plan
            else 0.0,
        )
