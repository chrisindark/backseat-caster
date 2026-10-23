# 📑 manifest.json — Clip Metadata Format

Each render writes `manifest.json` next to its MP4 outputs in `./data/renders/<clip_id>/`. It is the machine-readable "shipping label" of a clip: how it was cut, encoded, mixed, and where the artifacts are.

---

## 1. Where it's produced

- Writer: [`app/rendering/manifest.py`](../app/rendering/manifest.py) (`manifest.json` builder), executed by the render engine at the end of every job.
- Served: `GET /api/v1/renders/{clip_id}/manifest` (raw JSON override, per [API_REFERENCE.md](../API_REFERENCE.md)); the UI has a manifest viewer modal (`ui/src/components/ManifestModal.tsx`).

## 2. Content groups

The exact schema lives in the writer module; conceptually the manifest carries:

| Group | Contents |
|---|---|
| **Identity** | `clip_id`, source video id, request params that shaped the render |
| **Probe results** | Source and output ffprobe data: codecs, resolutions, fps, duration, bitrates, sample rates |
| **Cut & filters** | Actual start/end seconds, crop preset + padding fraction, quality preset + resolved encoder, blur-padding filter chain description |
| **Audio** | Ducking applied or not, loudnorm (EBU R128) target summary, peak limit |
| **Timing** | UTC timestamps for job start/end, encode wall time (always timezone-aware) |
| **Paths** | Absolute paths of `landscape.mp4`, `vertical_blur.mp4`, `vertical_crop.mp4`, source VOD |

## 3. Stability contract

- The manifest is an **append-friendly** format: consumers should ignore unknown fields so new keys can be added without a breaking bump.
- Renaming or removing keys pre-1.0 ships as a MINOR release (per [RELEASES.md](../RELEASES.md)) — update [ARCHITECTURE.md](../ARCHITECTURE.md) and this doc in the same change.
- Values are plain JSON (no debug blobs), since manifests from past renders double as a review log.

## 4. Usage patterns

- **Dedup / audit:** compare probe group across one clip's three formats to confirm cut alignment.
- **Automation:** scripts can safely re-read manifests after background renders complete rather than watching the filesystem.
- **UI fallback:** the render card's technical payload is rendered straight from `/manifest` when present.

## 5. Related

- Rendering behavior the manifest describes: [rendering.md](rendering.md), [audio-pipeline.md](audio-pipeline.md).
- Job state that produced it: [background-tasks.md](background-tasks.md).
