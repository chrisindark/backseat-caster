"""Audio mixing, ducking, and peak limiting filtergraph builders."""


def build_audio_filter_graph(
    start_seconds: float,
    duration_seconds: float,
    has_source_audio: bool,
    has_narration: bool = False,
    ducked_game_gain: float = 0.30,
    narration_gain: float = 1.0,
    limiter_enabled: bool = True,
    normalize_audio: bool = True,
    target_lufs: float = -14.0,
    loudnorm_true_peak: float = -1.5,
    loudnorm_lra: float = 11.0,
) -> tuple[str | None, str]:
    """
    Construct audio filtergraph string and return (filter_string, output_label).

    If has_narration is False:
        Game audio is preserved unducked with zero volume attenuation.
        If normalize_audio is True, EBU R128 loudness normalization (default -14 LUFS) is applied.
    If has_narration is True:
        Game audio is ducked to ducked_game_gain, mixed with narration, and passed through peak limiter.
        If normalize_audio is True, EBU R128 loudness normalization (default -14 LUFS) is applied to the final mix.
    """
    limiter_suffix = (
        ",alimiter=limit=0.95:attack=5:release=50" if limiter_enabled else ""
    )
    norm_suffix = (
        f",loudnorm=I={target_lufs:.1f}:TP={loudnorm_true_peak:.1f}:LRA={loudnorm_lra:.1f}"
        if normalize_audio
        else ""
    )

    # Mode 1: No narration voiceover (Pure Game Audio, NO ducking)
    if not has_narration:
        if has_source_audio:
            graph = (
                f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
                f"asetpts=PTS-STARTPTS{norm_suffix}[a_out]"
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
            f"asetpts=PTS-STARTPTS[a_game];"
            f"[1:a]atrim=start=0:duration={duration_seconds:.3f},"
            f"asetpts=PTS-STARTPTS,volume={narration_gain:.2f}[a_narr];"
            f"[a_game][a_narr]sidechaincompress=threshold=0.1:ratio=4:attack=20:release=250,"
            f"volume={ducked_game_gain:.2f}[a_ducked];"
            f"[a_ducked][a_narr]amix=inputs=2:duration=first:dropout_transition=2"
            f"{limiter_suffix}{norm_suffix}[a_out]"
        )
        return graph, "[a_out]"
    else:
        # Source video has no audio, only narration
        graph = (
            f"[1:a]atrim=start=0:duration={duration_seconds:.3f},"
            f"asetpts=PTS-STARTPTS,volume={narration_gain:.2f}"
            f"{limiter_suffix}{norm_suffix}[a_out]"
        )
        return graph, "[a_out]"
