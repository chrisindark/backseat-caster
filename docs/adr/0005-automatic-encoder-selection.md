# ADR 0005 — Automatic FFmpeg Encoder Selection

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

BackseatCaster targets Apple Silicon laptops first (where `h264_videotoolbox` is dramatically faster and battery-friendly) but also runs in Docker on Linux (`libx264` only), and must never fail because of a hardcoded encoder flag on a machine without that encoder.

## Decision

- Encoder selection is **resolved at render time**, not baked into commands:
  - `RenderConfig.preferred_encoder` ∈ `auto | h264_videotoolbox | libx264`, default `auto`.
  - `auto` hydrates from `detect_available_encoders()` — `h264_videotoolbox` on macOS when the encoder exists, otherwise `libx264`.
- Rate/quality parameters are split per encoder and defined by quality presets (`high` / `compact` / `archive`): VideoToolbox gets bitrate/maxrate/bufsize; libx264 gets CRF + preset.
- Video filter graphs (`filters.py`) and audio graphs (`audio.py`) stay encoder-agnostic.

## Consequences

- Positive: the same request renders correctly on a Mac and in a Linux container; speed stays native on Apple Silicon; tests can assert resolved encoder from the manifest.
- Negative: build reproducibility depends on the FFmpeg build present — the Docker image must keep `libx264` compiled in, and manifests are the debugging trail for "which encoder actually ran".

Enforcement: reviewers reject any hardcoded encoder flag or `-b:v` that isn't sourced from `RenderConfig`/presets.

## References

- [docs/rendering.md](../rendering.md)
- [CONFIGURATION.md — Render defaults](../../CONFIGURATION.md#7-render-defaults-not-env)
- [docs/deployment.md](../deployment.md)
