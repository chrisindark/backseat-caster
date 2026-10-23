"""Targeted Marvel Rivals HUD Region Extractor for high-energy candidate windows.

Crops only fixed gameplay HUD areas (Center KO Banner, Top-Right Kill Feed,
Ultimate Ability Meter, Objective Banner) at low frequency (1-2 FPS) directly
in memory via FFmpeg pipes without decoding the full video frame or writing
thousands of temporary images to disk.

Supports resolution scaling (720p, 1080p, 1440p, 4K, 21:9 Ultrawide) mapped
to standard 1080p base coordinates.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from app.rendering.probe import probe_media
from app.services.highlight.audio_scanner import AudioCandidateWindow

logger = logging.getLogger(__name__)


class HUDRegion(BaseModel):
    """Specification of a gameplay HUD Region of Interest in 1080p base coordinates."""

    name: str = Field(..., description="Unique identifier for HUD region")
    x: int = Field(..., description="Base X coordinate (0-1920)")
    y: int = Field(..., description="Base Y coordinate (0-1080)")
    width: int = Field(..., description="Base width in pixels")
    height: int = Field(..., description="Base height in pixels")
    description: str = Field(default="", description="Human-readable description")


# Default Marvel Rivals HUD Geometry (1080p Normalized Coordinates)
MARVEL_RIVALS_HUD_REGIONS: dict[str, HUDRegion] = {
    "center_ko": HUDRegion(
        name="center_ko",
        x=700,
        y=230,
        width=520,
        height=140,
        description="Upper-Center Elimination / Streak Banner (e.g. TRIPLE KO, TEAM WIPE, 5 PLAYER KO STREAK)",
    ),
    "kill_feed": HUDRegion(
        name="kill_feed",
        x=1400,
        y=40,
        width=480,
        height=220,
        description="Top-Right Kill Feed",
    ),
    "ultimate_meter": HUDRegion(
        name="ultimate_meter",
        x=920,
        y=920,
        width=80,
        height=50,
        description="Bottom-Center Ultimate Ability Meter (Numeric Text)",
    ),
    "objective_banner": HUDRegion(
        name="objective_banner",
        x=710,
        y=20,
        width=500,
        height=100,
        description="Top-Center Objective / Overtime Banner",
    ),
    "right_streak": HUDRegion(
        name="right_streak",
        x=1750,
        y=480,
        width=170,
        height=120,
        description="Right-Edge Personal Elimination / Streak Badge (e.g. DOUBLE!, TRIPLE!, UNSTOPPABLE!)",
    ),
    "hero_portrait": HUDRegion(
        name="hero_portrait",
        x=780,
        y=900,
        width=120,
        height=120,
        description="Played hero portrait / character icon used for hero identification",
    ),
    "ability_row": HUDRegion(
        name="ability_row",
        x=1470,
        y=870,
        width=380,
        height=120,
        description="Bottom-Right ability icon row used for cooldown/activation tracking",
    ),
}

# HUD regions required by the Phase 3 deep visual extraction stages.
PHASE3_HUD_ROI_NAMES: tuple[str, ...] = (
    "kill_feed",
    "ultimate_meter",
    "hero_portrait",
    "ability_row",
)


class ROIFrame(BaseModel):
    """Extracted in-memory video frame of a specific HUD region."""

    timestamp: float = Field(..., description="Video timestamp in seconds")
    roi_name: str = Field(..., description="Name of the extracted HUD region")
    width: int = Field(..., description="Normalized frame width in pixels")
    height: int = Field(..., description="Normalized frame height in pixels")
    raw_rgb: bytes = Field(..., description="Raw RGB24 byte buffer")

    def get_pixel_rgb(self, x: int, y: int) -> tuple[int, int, int]:
        """Retrieve (R, G, B) tuple for given coordinates."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(
                f"Coordinates ({x}, {y}) out of bounds ({self.width}x{self.height})"
            )
        offset = (y * self.width + x) * 3
        return (
            self.raw_rgb[offset],
            self.raw_rgb[offset + 1],
            self.raw_rgb[offset + 2],
        )

    def to_ppm(self) -> bytes:
        """Convert raw RGB24 buffer into standard PPM image bytes."""
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        return header + self.raw_rgb

    def save_ppm(self, file_path: Path | str) -> Path:
        """Save raw frame as portable pixmap (.ppm) without external libraries."""
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_ppm())
        return path

    def save_png(self, file_path: Path | str) -> Path:
        """Save frame as PNG using FFmpeg pipe or Pillow if available."""
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image

            img = Image.frombytes("RGB", (self.width, self.height), self.raw_rgb)
            img.save(str(path), format="PNG")
            return path
        except ImportError:
            # Fallback to FFmpeg PPM-to-PNG pipe
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-v",
                "error",
                "-f",
                "image2pipe",
                "-vcodec",
                "ppm",
                "-i",
                "-",
                "-y",
                str(path),
            ]
            subprocess.run(cmd, input=self.to_ppm(), check=True, capture_output=True)
            return path

    def count_color_matches(
        self,
        r_min: int,
        r_max: int,
        g_min: int,
        g_max: int,
        b_min: int,
        b_max: int,
    ) -> int:
        """Fast count of pixels falling within given RGB channel bounds."""
        raw = self.raw_rgb
        total_bytes = len(raw)
        matches = 0
        for i in range(0, total_bytes, 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            if r_min <= r <= r_max and g_min <= g <= g_max and b_min <= b <= b_max:
                matches += 1
        return matches

    def color_ratio(
        self,
        r_min: int,
        r_max: int,
        g_min: int,
        g_max: int,
        b_min: int,
        b_max: int,
    ) -> float:
        """Ratio of pixels matching RGB range relative to total frame pixels (0.0 to 1.0)."""
        total_pixels = self.width * self.height
        if total_pixels == 0:
            return 0.0
        return (
            self.count_color_matches(r_min, r_max, g_min, g_max, b_min, b_max)
            / total_pixels
        )


class WindowROIExtractionResult(BaseModel):
    """Extracted ROI frames for a single action time window."""

    window_start: float = Field(..., description="Window start timestamp in seconds")
    window_end: float = Field(..., description="Window end timestamp in seconds")
    window_duration: float = Field(..., description="Window duration in seconds")
    frames_by_roi: dict[str, list[ROIFrame]] = Field(
        default_factory=dict,
        description="Extracted frames mapped by ROI region name",
    )
    total_frames: int = Field(default=0, description="Total frames extracted")


class BatchROIExtractionResult(BaseModel):
    """Aggregate result from extracting HUD ROIs across multiple candidate windows."""

    file_path: str = Field(..., description="Media file path")
    source_width: int = Field(..., description="Source video width in pixels")
    source_height: int = Field(..., description="Source video height in pixels")
    fps: float = Field(..., description="Extraction sampling frame rate")
    windows_extracted: list[WindowROIExtractionResult] = Field(
        default_factory=list,
        description="Extracted results per candidate window",
    )
    total_frames: int = Field(
        default=0, description="Total frames extracted across all windows and ROIs"
    )
    extraction_duration_seconds: float = Field(
        default=0.0, description="Wall-clock time taken for extraction"
    )


class ROIExtractorConfig(BaseModel):
    """Configuration for low-frequency HUD ROI cropping."""

    fps: float = Field(
        default=1.0,
        description="Default sampling frequency in frames per second",
    )
    adaptive_sampling: bool = Field(
        default=True,
        description="If True, dynamically adapts sampling FPS based on window audio excitement",
    )
    fps_baseline: float = Field(
        default=0.75,
        description="Baseline sampling FPS for standard candidate windows",
    )
    fps_peak: float = Field(
        default=2.0,
        description="Elevated sampling FPS for high-excitement climax windows (score >= 0.70)",
    )
    primary_rois: list[str] = Field(
        default_factory=lambda: ["center_ko", "right_streak"],
        description="Default ROI region names to extract",
    )
    phase3_rois: list[str] = Field(
        default_factory=lambda: list(PHASE3_HUD_ROI_NAMES),
        description="Additional ROI regions sampled for killfeed, ultimate, hero and ability analysis",
    )
    normalize_to_1080p: bool = Field(
        default=True,
        description="Scale cropped ROI back to standard 1080p dimensions",
    )
    custom_regions: dict[str, HUDRegion] = Field(
        default_factory=dict,
        description="Additional or overridden HUD region definitions",
    )


def compute_crop_geometry(
    region: HUDRegion, source_width: int, source_height: int
) -> tuple[int, int, int, int]:
    """
    Calculate source-scaled crop box (x, y, w, h) for a 1080p base HUD region.

    Handles 16:9 scaling (720p, 1080p, 1440p, 4K) as well as 21:9 ultrawide geometry.
    """
    aspect_ratio = source_width / max(1, source_height)

    # Standard 16:9 aspect ratio (~1.777)
    if aspect_ratio <= 1.85:
        scale_x = source_width / 1920.0
        scale_y = source_height / 1080.0

        x = int(round(region.x * scale_x))
        y = int(round(region.y * scale_y))
        w = int(round(region.width * scale_x))
        h = int(round(region.height * scale_y))
    else:
        # Ultrawide (21:9 / 32:9): height determines base vertical scale
        base_scale = source_height / 1080.0
        w = int(round(region.width * base_scale))
        h = int(round(region.height * base_scale))
        y = int(round(region.y * base_scale))

        if region.x >= 1200:
            # Right-anchored HUD element (Kill Feed)
            right_margin_1080p = 1920 - (region.x + region.width)
            right_margin = int(round(right_margin_1080p * base_scale))
            x = source_width - right_margin - w
        elif region.x <= 400:
            # Left-anchored HUD element
            x = int(round(region.x * base_scale))
        else:
            # Center-anchored HUD element (Center KO, Ultimate Meter, Objective)
            center_offset = (source_width - (1920.0 * base_scale)) / 2.0
            x = int(round(center_offset + (region.x * base_scale)))

    # Boundary safety clamping
    x = max(0, min(source_width - 2, x))
    y = max(0, min(source_height - 2, y))
    w = max(2, min(source_width - x, w))
    h = max(2, min(source_height - y, h))

    # Force even dimensions for filter graph compatibility
    if w % 2 != 0:
        w = max(2, w - 1)
    if h % 2 != 0:
        h = max(2, h - 1)

    return x, y, w, h


class ROIExtractor:
    """In-memory HUD Region of Interest video extractor."""

    def __init__(self, config: ROIExtractorConfig | None = None) -> None:
        self.config = config or ROIExtractorConfig()
        self._regions: dict[str, HUDRegion] = dict(MARVEL_RIVALS_HUD_REGIONS)
        if self.config.custom_regions:
            self._regions.update(self.config.custom_regions)

    def get_region(self, name: str) -> HUDRegion:
        """Lookup a registered HUD region by name."""
        if name not in self._regions:
            valid = list(self._regions.keys())
            raise ValueError(f"Unknown HUD region '{name}'. Available: {valid}")
        return self._regions[name]

    def register_region(self, region: HUDRegion) -> None:
        """Register or update a HUD region definition."""
        self._regions[region.name] = region

    def extract_single_roi_in_range(
        self,
        media_path: Path | str,
        start_seconds: float,
        duration_seconds: float,
        roi_name: str,
        source_width: int,
        source_height: int,
        fps: float | None = None,
    ) -> list[ROIFrame]:
        """
        Extract in-memory frames for a single HUD ROI over a given time interval.

        Uses FFmpeg fast input seeking and rawvideo pipe without temporary files.
        """
        path = Path(media_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        region = self.get_region(roi_name)
        sampling_fps = max(0.1, fps or self.config.fps)

        if duration_seconds <= 0:
            return []

        x, y, w, h = compute_crop_geometry(region, source_width, source_height)

        # Build filtergraph: fps -> crop -> normalize scale to 1080p base
        filter_parts = [f"fps={sampling_fps}", f"crop={w}:{h}:{x}:{y}"]
        out_w, out_h = region.width, region.height
        if self.config.normalize_to_1080p:
            filter_parts.append(f"scale={out_w}:{out_h}")
        else:
            out_w, out_h = w, h

        vf_str = ",".join(filter_parts)

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, start_seconds):.3f}",
            "-i",
            str(path),
            "-t",
            f"{max(0.05, duration_seconds):.3f}",
            "-vf",
            vf_str,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]

        logger.debug("Executing ROI extraction (%s): %s", roi_name, " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stderr_output: list[bytes] = []

        def _drain_stderr() -> None:
            if proc.stderr:
                stderr_output.append(proc.stderr.read())

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        frame_bytes_len = out_w * out_h * 3
        frames: list[ROIFrame] = []
        frame_idx = 0

        try:
            if proc.stdout:
                while True:
                    chunk = proc.stdout.read(frame_bytes_len)
                    if len(chunk) < frame_bytes_len:
                        break

                    f_timestamp = round(start_seconds + (frame_idx / sampling_fps), 3)
                    frames.append(
                        ROIFrame(
                            timestamp=f_timestamp,
                            roi_name=roi_name,
                            width=out_w,
                            height=out_h,
                            raw_rgb=chunk,
                        )
                    )
                    frame_idx += 1

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

        if proc.returncode != 0:
            err_text = b"".join(stderr_output).decode("utf-8", errors="replace").strip()
            logger.error("FFmpeg ROI extraction failed for %s: %s", roi_name, err_text)
            raise RuntimeError(
                f"FFmpeg ROI extraction failed for {roi_name} on {path}:\n{err_text}"
            )

        return frames

    def extract_window_rois(
        self,
        media_path: Path | str,
        start_seconds: float,
        duration_seconds: float,
        roi_names: list[str] | None = None,
        fps: float | None = None,
        source_width: int | None = None,
        source_height: int | None = None,
    ) -> WindowROIExtractionResult:
        """Extract multiple HUD ROIs for a specific action time window."""
        path = Path(media_path).resolve()
        target_rois = roi_names or self.config.primary_rois

        # Probe resolution if not provided
        if source_width is None or source_height is None:
            probe = probe_media(path)
            source_width = probe.width
            source_height = probe.height

        frames_by_roi: dict[str, list[ROIFrame]] = {}
        total = 0

        for name in target_rois:
            rois = self.extract_single_roi_in_range(
                media_path=path,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                roi_name=name,
                source_width=source_width,
                source_height=source_height,
                fps=fps,
            )
            frames_by_roi[name] = rois
            total += len(rois)

        end_seconds = round(start_seconds + duration_seconds, 3)
        return WindowROIExtractionResult(
            window_start=round(start_seconds, 3),
            window_end=end_seconds,
            window_duration=round(duration_seconds, 3),
            frames_by_roi=frames_by_roi,
            total_frames=total,
        )

    def extract_candidate_windows(
        self,
        media_path: Path | str,
        windows: list[AudioCandidateWindow],
        roi_names: list[str] | None = None,
        fps: float | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> BatchROIExtractionResult:
        """
        Batch extract HUD ROIs across a list of candidate windows (e.g. from Step 1 audio scan).
        """
        path = Path(media_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        start_time = time.perf_counter()
        probe = probe_media(path)
        source_w = probe.width
        source_h = probe.height

        target_rois = roi_names or self.config.primary_rois

        results: list[WindowROIExtractionResult] = []
        total_frames = 0
        total_windows = len(windows)

        for idx, win in enumerate(windows, 1):
            if progress_callback and total_windows > 0:
                pct = round(((idx - 1) / total_windows) * 100.0, 1)
                progress_callback(
                    pct,
                    f"Extracting HUD ROIs (window {idx}/{total_windows})",
                )

            # Adaptive sampling: elevate to fps_peak during high-energy climaxes
            if fps is not None:
                win_fps = fps
            elif self.config.adaptive_sampling:
                win_fps = (
                    self.config.fps_peak
                    if getattr(win, "score", 0.0) >= 0.70
                    else self.config.fps_baseline
                )
            else:
                win_fps = self.config.fps

            win_res = self.extract_window_rois(
                media_path=path,
                start_seconds=win.start_seconds,
                duration_seconds=win.duration_seconds,
                roi_names=target_rois,
                fps=win_fps,
                source_width=source_w,
                source_height=source_h,
            )
            results.append(win_res)
            total_frames += win_res.total_frames

        if progress_callback:
            progress_callback(100.0, "HUD ROI extraction completed")

        duration_sec = round(time.perf_counter() - start_time, 3)
        logger.info(
            "Extracted %d HUD frames across %d candidate windows in %.2fs (source: %dx%d).",
            total_frames,
            total_windows,
            duration_sec,
            source_w,
            source_h,
        )

        return BatchROIExtractionResult(
            file_path=str(path),
            source_width=source_w,
            source_height=source_h,
            fps=fps or self.config.fps,
            windows_extracted=results,
            total_frames=total_frames,
            extraction_duration_seconds=duration_sec,
        )


def extract_window_rois(
    media_path: Path | str,
    start_seconds: float,
    duration_seconds: float,
    roi_names: list[str] | None = None,
    fps: float | None = None,
    config: ROIExtractorConfig | None = None,
) -> WindowROIExtractionResult:
    """Convenience function to extract HUD ROIs for a single window."""
    extractor = ROIExtractor(config=config)
    return extractor.extract_window_rois(
        media_path=media_path,
        start_seconds=start_seconds,
        duration_seconds=duration_seconds,
        roi_names=roi_names,
        fps=fps,
    )


def extract_candidate_windows_rois(
    media_path: Path | str,
    windows: list[AudioCandidateWindow],
    roi_names: list[str] | None = None,
    fps: float | None = None,
    config: ROIExtractorConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> BatchROIExtractionResult:
    """Convenience function to extract HUD ROIs across candidate windows."""
    extractor = ROIExtractor(config=config)
    return extractor.extract_candidate_windows(
        media_path=media_path,
        windows=windows,
        roi_names=roi_names,
        fps=fps,
        progress_callback=progress_callback,
    )
