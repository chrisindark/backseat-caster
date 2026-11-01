"""Audio mixing, ducking, and peak limiting filtergraph builders (Milestone 5)."""

from __future__ import annotations


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
    narration_start_seconds: float = 0.0,
    audio_total_seconds: float | None = None,
    has_music: bool = False,
    music_input_label: str = "2:a",
    music_gain: float = 0.30,
    loop_optimization: bool = False,
    loop_fade_seconds: float = 0.10,
) -> tuple[str | None, str]:
    """
    Construct audio filtergraph string and return (filter_string, output_label).

    Features:
    - Pure game audio preservation when narration and music are absent.
    - Sidechain ducking of game audio when narration/voiceover is present.
    - Creator-supplied background music with sidechain ducking beneath foreground audio.
    - Seamless loop optimization with micro-faded boundary transitions (no pops/clicks).
    - True peak limiting (alimiter) and EBU R128 loudness normalization (loudnorm).
    """
    limiter_suffix = (
        ",alimiter=limit=0.95:attack=5:release=50" if limiter_enabled else ""
    )
    norm_suffix = (
        f",loudnorm=I={target_lufs:.1f}:TP={loudnorm_true_peak:.1f}:LRA={loudnorm_lra:.1f}"
        if normalize_audio
        else ""
    )

    total_duration = (
        float(audio_total_seconds) if audio_total_seconds else float(duration_seconds)
    )
    narration_start = max(0.0, float(narration_start_seconds or 0.0))

    # Fast path: Pure Game Audio without narration, music, or loop processing
    if not has_narration and not has_music and not loop_optimization:
        if has_source_audio:
            graph = (
                f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
                f"asetpts=PTS-STARTPTS{norm_suffix}[a_out]"
            )
            return graph, "[a_out]"
        else:
            graph = f"aevalsrc=0:d={duration_seconds:.3f}:s=48000:c=stereo[a_out]"
            return graph, "[a_out]"

    # Step 1: Build the primary foreground audio [a_fg]
    filter_parts: list[str] = []

    if has_narration:
        delay_filter = ""
        if narration_start > 0.001:
            delay_filter = f",adelay={int(round(narration_start * 1000))}|{int(round(narration_start * 1000))}"

        narr_chain = (
            f"[1:a]atrim=start=0,volume={narration_gain:.2f},"
            f"asetpts=PTS-STARTPTS{delay_filter},"
            f"apad=whole_dur={total_duration:.3f},"
            f"atrim=duration={total_duration:.3f},"
            f"asplit=2[a_narr_key][a_narr_mix]"
        )
        filter_parts.append(narr_chain)

        if has_source_audio:
            game_pad = ""
            if total_duration > duration_seconds + 0.01:
                game_pad = f",apad=whole_dur={total_duration:.3f}"
            game_chain = (
                f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
                f"asetpts=PTS-STARTPTS{game_pad}[a_game];"
                f"[a_game][a_narr_key]sidechaincompress=threshold=0.1:ratio=4:attack=20:release=250,"
                f"volume={ducked_game_gain:.2f}[a_ducked];"
                f"[a_ducked][a_narr_mix]amix=inputs=2:duration=first:dropout_transition=2,"
                f"atrim=duration={total_duration:.3f}[a_fg]"
            )
            filter_parts.append(game_chain)
        else:
            filter_parts.append("[a_narr_mix]anull[a_fg]")
    else:
        # No narration
        if has_source_audio:
            game_pad = ""
            if total_duration > duration_seconds + 0.01:
                game_pad = f",apad=whole_dur={total_duration:.3f}"
            filter_parts.append(
                f"[0:a]atrim=start={start_seconds:.3f}:duration={duration_seconds:.3f},"
                f"asetpts=PTS-STARTPTS{game_pad},atrim=duration={total_duration:.3f}[a_fg]"
            )
        else:
            filter_parts.append(
                f"aevalsrc=0:d={total_duration:.3f}:s=48000:c=stereo[a_fg]"
            )

    curr_mix = "a_fg"

    # Step 2: Background music sidechain-ducked beneath foreground audio
    if has_music:
        clean_music_in = music_input_label.strip("[]")
        music_chain = (
            f"[{curr_mix}]asplit=2[a_fg_key][a_fg_mix];"
            f"[{clean_music_in}]atrim=duration={total_duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={music_gain:.2f}[a_music_raw];"
            f"[a_music_raw][a_fg_key]sidechaincompress=threshold=0.15:ratio=3:attack=20:release=300[a_music_ducked];"
            f"[a_fg_mix][a_music_ducked]amix=inputs=2:duration=first:dropout_transition=2,"
            f"atrim=duration={total_duration:.3f}[a_mus_mix]"
        )
        filter_parts.append(music_chain)
        curr_mix = "a_mus_mix"

    # Step 3: Loop boundary micro-fade smoothing (eliminates pops at seam)
    loop_fade = ""
    if loop_optimization:
        fade_d = max(0.02, min(0.30, loop_fade_seconds))
        fade_st = max(0.0, total_duration - fade_d)
        loop_fade = f",afade=t=in:ss=0:d={fade_d:.3f},afade=t=out:st={fade_st:.3f}:d={fade_d:.3f}"

    # Step 4: Final limiting and EBU R128 normalization
    post_filters = f"{loop_fade}{limiter_suffix}{norm_suffix}".lstrip(",")
    if post_filters:
        filter_parts.append(f"[{curr_mix}]{post_filters}[a_out]")
    else:
        filter_parts.append(f"[{curr_mix}]anull[a_out]")

    full_graph = ";".join(filter_parts)
    return full_graph, "[a_out]"
