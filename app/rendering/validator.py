"""Input and boundary validation for clip rendering requests."""

from pathlib import Path
from typing import Optional
from app.rendering.probe import MediaProbeResult


class ValidationError(ValueError):
    """Raised when render parameters violate validation constraints."""

    pass


def validate_render_parameters(
    probe: MediaProbeResult,
    start_seconds: float,
    duration_seconds: float,
    output_dir: Path,
    narration_path: Optional[Path] = None,
    overwrite: bool = False,
):
    """Validate render parameters against media probe and filesystem state."""
    if start_seconds < 0:
        raise ValidationError(
            f"Invalid start time: {start_seconds}s. Start time must be >= 0."
        )

    if duration_seconds <= 0:
        raise ValidationError(
            f"Invalid duration: {duration_seconds}s. Duration must be strictly positive."
        )

    # Check bounds against source video duration (allowing 0.25s tolerance for audio/video container drift)
    requested_end = start_seconds + duration_seconds
    if requested_end > probe.duration + 0.25:
        raise ValidationError(
            f"Requested clip window ({start_seconds}s to {requested_end:.2f}s) "
            f"exceeds source video duration ({probe.duration:.2f}s)."
        )

    # Validate narration audio if provided
    if narration_path:
        narr_file = Path(narration_path).resolve()
        if not narr_file.exists():
            raise ValidationError(f"Narration audio file does not exist: {narr_file}")
        if narr_file.stat().st_size == 0:
            raise ValidationError(f"Narration audio file is empty: {narr_file}")

    # Check overwrite safety
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and not overwrite:
        existing_outputs = [
            output_dir / "landscape.mp4",
            output_dir / "vertical_blur.mp4",
            output_dir / "vertical_crop.mp4",
        ]
        found = [str(f.name) for f in existing_outputs if f.exists()]
        if found:
            raise ValidationError(
                f"Output directory {output_dir} already contains rendered files: {', '.join(found)}. "
                f"Specify overwrite=True or --overwrite to replace existing renders."
            )
