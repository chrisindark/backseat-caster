# 🎬 Rendering Engine

The FFmpeg render engine (`app/rendering/`) turns a time range of a local VOD into three synchronized outputs plus a manifest. Decision records: [ADR 0005](adr/0005-automatic-encoder-selection.md) (encoder selection), [ADR 0004](adr/0004-sqlite-local-first-storage.md) (artifact storage).

---

## 1. Outputs

| File | Dimensions | Composition |
|---|---|---|
| `landscape.mp4` | 1920×1080 | 16:9 master — full frame re-encoded |
| `vertical_blur.mp4` | 1080×1920 | Original video scaled + mirrored/boxblurred background fill, original centered |
| `vertical_crop.mp4` | 1080×1920 | Center crop via `crop_preset` padding rules |
| `manifest.json` | — | Probe data, filters, timing, paths ([manifest-format.md](manifest-format.md)) |

Lanczos scaling is used throughout for detail quality.

## 2. Crop presets

Defined in `app/rendering/config.py` as `CROP_PADDING_PRESETS`:

| Preset | Padding fraction | Meaning |
|---|---|---|
| `third_person` | 0.3333 | ~16.66% blurred band top & bottom (default — gameplay HUD stays readable) |
| `cinematic` | 0.25 | slightly shorter crop bands |
| `direct_crop` | 0.0 | pure full-height center crop |
| `custom` | any `crop_blur_padding` ∈ [0.0, 0.6] | |

## 3. Quality presets

| Preset | videotoolbox bitrate | libx264 CRF | Target |
|---|---|---|---|
| `high` (default) | 5M avg / 7M max / 10M buf | 21 | matches 1080p source (~35-40 MB/min) |
| `compact` | 3.5M / 5M / 7M | 24 | quick sharing (~25 MB/min) |
| `archive` | 20M / 25M / 40M | 17 | studio mastering (~120 MB/min) |

`RenderConfig.preferred_encoder` accepts `auto` (default), `h264_videotoolbox`, or `libx264`.

## 4. Encoder selection (do not hardcode encoders)

`detect_available_encoders()` introspects the FFmpeg build and resolves the configured preference to a concrete encoder flag set: `h264_videotoolbox` on Apple Silicon; `libx264` (CRF + `medium` preset) on Linux/Docker (this is the Docker path). Filter graphs and vendor-specific rate flags live in `app/rendering/filters.py` and `config.py` respectively. Routers, services, and UI pass only `RenderConfig` values around.

## 5. Audio integration

The engine attaches audio filters from `app/rendering/audio.py`: sidechain ducking when a narration WAV is provided, peak limiting, and EBU R128 → -14 LUFS `loudnorm` normalization. Full behavior: [audio-pipeline.md](audio-pipeline.md).

## 6. Validation & progression

- `app/rendering/validator.py` rejects impossible configs (invalid preset combos, zero/negative duration, padding out of range) before any FFmpeg invocation.
- [`VideoService`]/[`RenderService`] create the job: state `pending` → `processing` → `completed`/`failed`, tracked on the `RenderJob` model.
- Execution hangs off the standard Celery/BackgroundTasks rule ([background-tasks.md](background-tasks.md)).
- Progress and results are pumped via `RenderService` and available through `GET /renders/{clip_id}/status` (also `/renders/jobs/{job_id}/status`).

## 7. CLI

`app/rendering/cli.py` exposes the engine standalone for scripting/rendering without the API:

```bash
uv run python -m app.rendering.cli --input ./data/downloads/vod.mp4 --start 90 --end 145 --mode third_person --quality high
```

Used heavily by `tests/test_renderer.py` to validate outputs from synthetic assets generated with `lavfi` (`testsrc2` + `sine`).
