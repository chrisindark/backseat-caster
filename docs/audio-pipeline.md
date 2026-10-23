# 🔊 Audio Pipeline

The audio chain lives in [`app/rendering/audio.py`](../app/rendering/audio.py) (`build_audio_filter_graph`). Every knob it touches is exposed as a `RenderConfig` field in [`app/rendering/config.py`](../app/rendering/config.py) — never hardcode values into the graph.

---

## 1. No narration (pure game audio)

`has_narration=False` keeps gameplay audio **unducked** (`unducked_game_gain`, default 1.0):

- Source audio is trimmed to the clip window (`atrim=start=…:duration=…`) and reset to zero-based PTS.
- If `normalize_audio` is on, the EBU R128 filter is appended (see §3).
- If the source has no audio and no narration was provided, a silent stereo bed (`aevalsrc=0`, 48 kHz) is generated so players don't crash on clipless streams. This is why `has_source_audio` is threaded through from the probe step.

## 2. Narration ducking (sidechain compression)

`has_narration=True` mixes the voiceover (input `#1`, a WAV) over gameplay audio (input `#0`) with a sidechain compress, then mixes:

1. Narration is trimmed and scaled by `narration_gain` (default 1.0).
2. Gameplay audio passes through `sidechaincompress` keyed by the narration: `threshold=0.1, ratio=4, attack=20, release=250` — speech ducks the game track, then it recovers smoothly (250 ms release avoids abrupt jumps).
3. The ducked game chain is further attenuated by `ducked_game_gain` (default 0.30, i.e. −10 dB of headroom).
4. Both are folded with `amix=duration=first` so clip length is dictated by the render window.

If the source has no audio, the narration alone (with gains + limiter/normalizer) is the output.

## 3. Peak limiting & loudness normalization

Applied to the final mix (with or without narration), both controlled from `RenderConfig`:

| Filter | Parameters | Purpose |
|---|---|---|
| `alimiter` (if `limiter_enabled`) | `limit=0.95, attack=5, release=50` | catch post-mix transients below digital ceiling |
| `loudnorm` (if `normalize_audio`) | `I=target_lufs=-14.0`, `TP=-1.5`, `LRA=11.0` | EBU R128 integrated loudness normalization to the YouTube Shorts standard, with true-peak ceiling |

Output is AAC at `audio_bitrate=192k`, 48 kHz (`audio_sample_rate`).

## 4. Gating flags & duration handling

- `normalize_audio` / `limiter_enabled` ship enabled on every render by default; disable per request via `RenderConfig` if the source mix is already broadcast-standard.
- `clamp_to_duration=True` silently clamps clips that overrun the source's real duration instead of raising `ValidationError` (`min_clip_duration` defaults to 0.5 s and rejects anything shorter before FFmpeg is invoked).
