"""Input and boundary validation for clip rendering requests."""

import logging
from pathlib import Path

from app.rendering.probe import MediaProbeResult

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when render parameters violate validation constraints."""


def validate_render_parameters(
    probe: MediaProbeResult,
    start_seconds: float,
    duration_seconds: float,
    output_dir: Path,
    narration_path: Path | None = None,
    overwrite: bool = False,
    modes: list[str] | None = None,
    clamp_duration: bool = False,
    min_duration: float = 0.5,
) -> float:
    """
    Validate render parameters against media probe and filesystem state.

    If clamp_duration is True, durations exceeding source video bounds are clamped
    to the remaining media length (down to min_duration).
    Returns the effective duration in seconds.
    """
    if start_seconds < 0:
        raise ValidationError(
            f"Invalid start time: {start_seconds}s. Start time must be >= 0."
        )

    if duration_seconds <= 0:
        raise ValidationError(
            f"Invalid duration: {duration_seconds}s. Duration must be strictly positive."
        )

    if start_seconds >= probe.duration:
        raise ValidationError(
            f"Requested start time ({start_seconds:.2f}s) exceeds source video duration ({probe.duration:.2f}s)."
        )

    # Check bounds against source video duration (allowing 0.25s tolerance for audio/video container drift)
    requested_end = start_seconds + duration_seconds
    effective_duration = duration_seconds
    if requested_end > probe.duration + 0.25:
        if clamp_duration:
            effective_duration = max(0.0, probe.duration - start_seconds)
            if effective_duration < min_duration:
                raise ValidationError(
                    f"Requested clip window ({start_seconds:.2f}s to {requested_end:.2f}s) "
                    f"exceeds source video duration ({probe.duration:.2f}s), and remaining duration "
                    f"({effective_duration:.2f}s) is shorter than minimum allowable ({min_duration:.2f}s)."
                )
            logger.info(
                "Requested clip window (%.2fs to %.2fs) exceeds source duration (%.2fs). "
                "Clamping duration to %.2fs.",
                start_seconds,
                requested_end,
                probe.duration,
                effective_duration,
            )
        else:
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
        if modes:
            existing_outputs = [output_dir / f"{m}.mp4" for m in modes]
        else:
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

    return effective_duration
