"""Audio mixing, ducking, and peak limiting filtergraph builders."""

from typing import Optional, Tuple


def build_audio_filter_graph(
    start_seconds: float,
    duration_seconds: float,
    has_source_audio: bool,
    has_narration: bool = False,
    ducked_game_gain: float = 0.30,
    narration_gain: float = 1.0,
    limiter_enabled: bool = True,
) -> Tuple[Optional[str], str]:
    """
    Construct audio filtergraph string and return (filter_string, output_label).

    If has_narration is False:
        Game audio is preserved 100% unducked with zero volume attenuation.
    If has_narration is True:
        Game audio is ducked to ducked_game_gain, mixed with narration, and passed through peak limiter.
    """
    limiter_suffix = (
        ",alimiter=limit=0.95:attack=5:release=50" if limiter_enabled else ""
    )

    # Mode 1: No narration voiceover (Pure Game Audio, NO ducking)
    if not has_narration:
        if has_source_audio:
            graph = (
                f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
                f"asetpts=PTS-STARTPTS[a_out]"
            )
            return graph, "[a_out]"
        else:
            # Generate silent audio so players don't crash
            graph = f"aevalsrc=0:d={duration_seconds:.3f}:s=48000:c=stereo[a_out]"
            return graph, "[a_out]"

    # Mode 2: With Narration Voiceover
    if has_source_audio:
        graph = (
            f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
            f"asetpts=PTS-STARTPTS,volume={ducked_game_gain:.2f}[a_game];"
            f"[1:a]atrim=start=0:duration={duration_seconds:.3f},"
            f"asetpts=PTS-STARTPTS,volume={narration_gain:.2f}[a_narr];"
            f"[a_game][a_narr]amix=inputs=2:duration=first:dropout_transition=2"
            f"{limiter_suffix}[a_out]"
        )
        return graph, "[a_out]"
    else:
        # Source video has no audio, only narration
        graph = (
            f"[1:a]atrim=start=0:duration={duration_seconds:.3f},"
            f"asetpts=PTS-STARTPTS,volume={narration_gain:.2f}"
            f"{limiter_suffix}[a_out]"
        )
        return graph, "[a_out]"
