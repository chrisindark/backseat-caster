"""Manifest generator for rendered clips."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.rendering.probe import MediaProbeResult


def write_manifest(
    output_dir: Path,
    clip_id: str,
    source_probe: MediaProbeResult,
    start_seconds: float,
    duration_seconds: float,
    outputs: dict[str, dict[str, Any]],
    narration_path: Path | None = None,
    render_duration: float | None = None,
    api_prefix: str = "/api/v1",
    crop_preset: str | None = None,
    crop_blur_padding: float | None = None,
    modes: list[str] | None = None,
    normalize_audio: bool = True,
    target_lufs: float = -14.0,
    requested_duration_seconds: float | None = None,
    clamped: bool = False,
    quality_preset: str | None = None,
    watermark: dict[str, Any] | None = None,
    branding: dict[str, Any] | None = None,
) -> Path:
    """Generate and write manifest.json into the clip output directory."""
    effective_modes = modes or list(outputs.keys())
    manifest_data = {
        "clip_id": clip_id,
        "modes": effective_modes,
        "landscape_path": f"{api_prefix}/renders/{clip_id}/stream/landscape"
        if "landscape" in outputs
        else None,
        "vertical_blur_path": f"{api_prefix}/renders/{clip_id}/stream/vertical_blur"
        if "vertical_blur" in outputs
        else None,
        "vertical_crop_path": f"{api_prefix}/renders/{clip_id}/stream/vertical_crop"
        if (
            "vertical_crop" in outputs
            or any(
                m in outputs
                for m in ("third_person", "direct_crop", "cinematic", "custom")
            )
        )
        else None,
        "manifest_path": f"{api_prefix}/renders/{clip_id}/stream/manifest",
        "source_file": source_probe.file_path,
        "source": {
            "path": source_probe.file_path,
            "duration": source_probe.duration,
            "width": source_probe.width,
            "height": source_probe.height,
            "fps": source_probe.fps,
            "video_codec": source_probe.video_codec,
            "has_audio": source_probe.has_audio,
            "audio_codec": source_probe.audio_codec,
            "file_size_bytes": source_probe.file_size_bytes,
        },
        "source_metadata": {
            "duration": source_probe.duration,
            "width": source_probe.width,
            "height": source_probe.height,
            "fps": source_probe.fps,
            "video_codec": source_probe.video_codec,
            "has_audio": source_probe.has_audio,
            "audio_codec": source_probe.audio_codec,
            "file_size_bytes": source_probe.file_size_bytes,
        },
        "audio": {
            "normalization": "EBU R128" if normalize_audio else "disabled",
            "normalized": normalize_audio,
            "target_lufs": target_lufs,
            "true_peak_dbtp": -1.5 if normalize_audio else None,
            "has_narration": narration_path is not None,
        },
        "request": {
            "start_seconds": start_seconds,
            "duration_seconds": duration_seconds,
            "requested_duration_seconds": requested_duration_seconds
            if requested_duration_seconds is not None
            else duration_seconds,
            "clamped": clamped,
            "has_narration": narration_path is not None,
            "narration_file": str(narration_path) if narration_path else None,
            "crop_preset": crop_preset or "third_person",
            "crop_blur_padding": crop_blur_padding
            if crop_blur_padding is not None
            else 0.3333,
            "modes": effective_modes,
            "normalize_audio": normalize_audio,
            "target_lufs": target_lufs,
        },
        "quality_preset": quality_preset,
        "watermark": watermark or {"enabled": False},
        "branding": branding or {"enabled": False},
        "outputs": outputs,
        "created_at": datetime.now(UTC).isoformat(),
        "render_duration_seconds": round(render_duration, 2)
        if render_duration is not None
        else None,
    }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    return manifest_path
