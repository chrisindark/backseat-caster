# 🎬 Specification & Architecture: Intro & "Subscribe & Bell" CTA Pipeline

> **Document Version:** 1.0.0  
> **Target Release:** Tier 3 Branding Extension / Post-Phase 8.5  
> **Status:** Draft / Specification (Multi-Agent Ready)

---

## 1. Executive Summary & Goals

BackseatCaster currently provides channel-level branding defaults (watermark overlay, framing presets, quality tiers, upload slots, title templates). This specification defines the architecture for extending brand consistency to **intro cards** and **"Subscribe to the channel and click the bell icon for more clips and videos" Call-to-Action (CTA)** segments on every rendered clip.

### Core Requirements
1. **Shorts Duration Ceiling (180s Budget):**
   - In accordance with the updated YouTube Shorts specification, clips qualify for Shorts up to **180 seconds** (3 minutes).
   - The highlight mining engine decides the core clip length (typically 15s–60s). Intro and outro/CTA segments are added on top of the highlight.
   - The final composed video duration **must not exceed 180.0 seconds**. If `clip_duration + intro_duration + outro_duration > 180.0s`, the engine dynamically adjusts or switches modes to preserve the 180s ceiling.
2. **Dual Presentation Styles:**
   - **Mode A: In-Video Lower-Third Overlay Banner:** Burns an animated or styled visual card/banner into the bottom-third of the video during the final $N$ seconds (e.g. 3–5s) of gameplay without increasing video duration.
   - **Mode B: End Card Screen (Outro Bumper):** Appends a standalone 2–3s outro card screen after gameplay concludes.
   - Creator can select their preferred default mode in the Channel Profile.
3. **Synthesized TTS Audio Engine:**
   - Synthesizes the spoken voiceover (*"Subscribe to the channel and click the bell icon for more clips and videos"* or creator-configured text) via a fast, local neural TTS engine (`edge-tts`).
   - Pairs voiceover with a bundled broadcast bell sound effect (`bell_chime.wav`).
   - Automatically ducks the gameplay audio beneath the spoken voiceover and runs through the -14 LUFS EBU R128 loudness normalizer.
4. **Single-Pass FFmpeg Rendering:**
   - Composes video, watermark, intro, CTA overlay/concat, narration, voiceover, and audio ducking inside a single FFmpeg filtergraph execution to avoid multi-generation re-encoding loss.

---

## 2. Technical Architecture & Component Flow

```
                              ┌───────────────────────────────────┐
                              │     Channel Profile Settings      │
                              │ (Intro, CTA Style, TTS Copy, Font) │
                              └─────────────────┬─────────────────┘
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     [TTS Synthesis Service]                                       [Pillow Branding Engine]
 (Synthesizes speech to cached WAV)                          (Rasterizes intro card / CTA banner)
                 │                                                             │
                 ▼                                                             ▼
     [Intro/CTA Audio Inputs]                                      [Intro/CTA Image Inputs]
 (TTS Voiceover + Bell Chime SFX)                                 (PNG cards & Lower-Third Pill)
                 │                                                             │
                 └──────────────────────────────┬──────────────────────────────┘
                                                │
                                                ▼
                        ┌───────────────────────────────────────────────┐
                        │      FFmpeg Single-Pass Render Engine         │
                        │                                               │
                        │ Video Graph:                                  │
                        │   [0:v] -> Crop/Blur -> Watermark             │
                        │   If In-Video Overlay:                        │
                        │     -> overlay=x:y:enable='between(t,...)'    │
                        │   If End Card:                                │
                        │     -> concat=n=3 (intro + clip + outro)      │
                        │                                               │
                        │ Audio Graph:                                  │
                        │   [0:a] Gameplay Audio                        │
                        │   -> Ducking during TTS Voiceover             │
                        │   -> adelay (for intro)                       │
                        │   -> amix/concat (with voiceover + bell)      │
                        │   -> loudnorm (-14 LUFS YouTube Shorts)       │
                        └───────────────────────┬───────────────────────┘
                                                │
                                                ▼
                                    Output Render Artifacts
                                (landscape.mp4, vertical_*.mp4)
```

---

## 3. Detailed Component Specifications

### 3.1. Shorts Duration Guardrail (180.0s Hard Limit)

The total output runtime $T_{\text{total}}$ is calculated as:
- **For In-Video Overlay Mode:**
  $$T_{\text{total}} = T_{\text{intro}} + T_{\text{clip}}$$
  *(CTA runs concurrently with the final $N$ seconds of the clip, adding 0 extra runtime).*
- **For End Card Mode:**
  $$T_{\text{total}} = T_{\text{intro}} + T_{\text{clip}} + T_{\text{outro}}$$

**Guardrail Policy:**
1. If $T_{\text{total}} \le 180.0\text{s}$: Render proceeds normally.
2. If $T_{\text{total}} > 180.0\text{s}$ and Mode is *End Card*:
   - Automatically fall back to *In-Video Overlay Mode* (saving $T_{\text{outro}}$).
3. If $T_{\text{total}} > 180.0\text{s}$ even after fallback:
   - Trim intro duration or clamp end time such that $T_{\text{total}} = 180.0\text{s}$.
   - Log an informative warning in `manifest.json`: `"duration_clamped_to_shorts_limit": true`.

---

### 3.2. Visual Assets & Pill Layout (Pillow Rasterization)

To ensure zero dependencies on system freetype/libfontconfig, all graphics are pre-rasterized using Pillow before being handed to FFmpeg:

#### A. Intro Card
- Full-frame card (1920×1080 for landscape, 1080×1920 for vertical).
- Channel logo (if available) centered with channel title and optional subtitle.
- Duration: 0.8s – 2.0s (default: 1.2s).

#### B. End Card Screen (Outro Bumper)
- Full-frame card with dark glass background (`#0B0D13`).
- Large bell icon graphic with gold/accent highlight (`#F59E0B` / `#F43F5E`).
- Primary text: `SUBSCRIBE & CLICK THE 🔔` (or custom headline).
- Subtitle: `For more clips and videos daily`.
- Channel handle / watermark at bottom.

#### C. In-Video Lower-Third Overlay Banner
- A rounded pill / banner positioned at the bottom margin of the screen:
  - Width: ~88% of video width (950px on 1080×1920 vertical).
  - Height: ~140–180px.
  - Background: Semi-transparent dark pill (`rgba(11, 13, 19, 0.88)`) with subtle accent border.
  - Left side: Bell icon graphic.
  - Center/Right side: Two-line layout:
    - Top line (Bold, 36px): **SUBSCRIBE & TAP 🔔**
    - Bottom line (Regular, 24px): *Click the bell icon for daily clips*
- Overlay timing: Active from $t_{\text{start}} = \max(0, T_{\text{clip}} - T_{\text{cta}})$ to $T_{\text{clip}}$.

---

### 3.3. TTS Audio Synthesis & Bell SFX Engine

1. **TTS Synthesis:**
   - Library: `edge-tts` (asynchronous, Microsoft Neural voices, zero API key required, high naturalism).
   - Default Voice: `en-US-ChristopherNeural` (clear broadcast gaming tone) or `en-US-GuyNeural`.
   - Output format: 48kHz mono 16-bit `.wav`.
   - Caching: Synthesized `.wav` files are cached in `data/channel/tts_cache/<md5_hash>.wav`. If the channel CTA text and voice have not changed, subsequent renders re-use the cached audio with 0ms synthesis overhead.
2. **Bell Chime SFX:**
   - Bundled asset: `app/assets/audio/bell_chime.wav` (clean high-frequency chime/notification ring).
   - Mixed with the TTS voiceover so the bell rings right as the voice says *"bell icon"*.
3. **Gameplay Audio Ducking:**
   - During the CTA voiceover duration, gameplay audio gain is ducked to `0.25` (-12dB) with smooth 200ms attack/release curves.
   - All audio passes through the EBU R128 `loudnorm` filter (-14 LUFS, -1.5 dBTP, 11 LU LRA) ensuring compliance with YouTube Shorts loudness standards.

---

## 4. Multi-Agent Implementation Milestones

To enable clean parallel or staged development across autonomous agents, the work is partitioned into 6 self-contained milestones with strict boundaries and contracts.

```
┌────────────────────────────────────────────────────────────────────────┐
│ M0: Schema, Models & Alembic Migration                                  │
│ (ChannelProfile fields, Pydantic schemas, 180s duration budget rule)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────┐   ┌──────────────────────────────────┐
│ M1: TTS Engine & Audio Assets   │   │ M2: Visual Cards & Overlay Gen   │
│ - edge-tts synthesis utility    │   │ - Intro card & outro card        │
│ - MD5 hash audio disk cache     │   │ - Lower-third pill banner        │
│ - Bundled bell_chime.wav        │   │ - Bell icon rasterizer           │
└────────────────┬────────────────┘   └────────────────┬─────────────────┘
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ M3: FFmpeg Engine Integration (Video + Audio Single-Pass Filtergraph)  │
│ - Lower-third overlay vs concat branch                                 │
│ - Voiceover mixing + sidechain ducking + loudnorm                      │
│ - 180s duration clamping                                               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────┐   ┌──────────────────────────────────┐
│ M4: Backend Routers & API       │   │ M5: Frontend UI Brand Editor     │
│ - /api/v1/channel/profile ext   │   │ - Intro & CTA controls in /channel│
│ - /api/v1/channel/cta/preview   │   │ - Live visual card/overlay prev  │
│ - Integration with AutoStage    │   │ - TTS audio preview button       │
└────────────────┬────────────────┘   └────────────────┬─────────────────┘
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ M6: Verification, Integration Testing & Documentation                  │
│ - Synthetic FFmpeg end-to-end pytest tests                             │
│ - 180s ceiling assertions                                              │
│ - docs/channel-branding.md & ROADMAP.md updates                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Milestone 0: Data Models, Schemas & Duration Budgeting
*Estimated scope: Backend model & config*

- **Target Files:**
  - `app/models/channel_profile.py`
  - `alembic/versions/<hash>_add_intro_cta_branding.py`
  - `app/schemas/channel.py`
  - `app/rendering/config.py`
- **Deliverables:**
  1. Add columns to `ChannelProfile`:
     - `intro_enabled` (`bool`, default `False`)
     - `intro_seconds` (`float`, default `1.2`, min `0.5`, max `3.0`)
     - `intro_title` (`str`, nullable)
     - `intro_subtitle` (`str`, nullable)
     - `cta_enabled` (`bool`, default `True`)
     - `cta_style` (`str`, default `"overlay"`, values: `["overlay", "outro_card"]`)
     - `cta_seconds` (`float`, default `3.5`, min `2.0`, max `6.0`)
     - `cta_headline` (`str`, default `"SUBSCRIBE & TAP 🔔"`)
     - `cta_subtitle` (`str`, default `"Click the bell for more clips and videos"`)
     - `cta_speech_text` (`str`, default `"Subscribe to the channel and click the bell icon for more clips and videos"`)
     - `cta_voice` (`str`, default `"en-US-ChristopherNeural"`)
  2. Generate clean Alembic migration.
  3. Update `BrandingConfig` with `max_shorts_duration = 180.0` and duration computation helpers.
- **Contract / Test Criteria:**
  - Alembic migrates cleanly forwards and backwards.
  - Serialization round-trips via `ChannelProfileResponse` and `ChannelProfileUpdate`.

---

### Milestone 1: TTS Audio Synthesis & SFX Engine
*Estimated scope: Audio synthesis utility*

- **Target Files:**
  - `app/services/tts.py` (New module)
  - `app/assets/audio/bell_chime.wav` (New bundled asset)
  - `pyproject.toml` (Add `edge-tts` dependency)
  - `tests/test_tts.py` (Unit tests)
- **Deliverables:**
  1. Implement `TTSService.synthesize_speech(text: str, voice: str) -> Path`:
     - Asynchronous generation using `edge-tts`.
     - Deterministic hash caching in `data/channel/tts_cache/`.
     - Fallback error handling if network is offline (returns silence or bundled tone).
  2. Implement `TTSService.generate_cta_audio(speech_text: str, include_bell: bool = True) -> Path`:
     - Generates the speech `.wav`.
     - In FFmpeg or Python `wave`, mixes the bell chime at a specified offset (e.g. 1.8s into the sentence).
     - Returns path to ready-to-mux audio file.
- **Contract / Test Criteria:**
  - Offline unit test with mock verifies cache hit and audio output path.
  - Deterministic caching produces identical file hashes for identical input text.

---

### Milestone 2: Visual Card & In-Video Overlay Generator (Pillow)
*Estimated scope: Rendering / Graphics*

- **Target Files:**
  - `app/rendering/branding.py`
  - `tests/test_branding_graphics.py`
- **Deliverables:**
  1. **Bell Icon Rendering:** Vector/path or high-res raster icon bundled in code/assets and drawn crisply with Pillow.
  2. **Intro Card Drawing:**
     - Supports `(1920, 1080)` and `(1080, 1920)`.
     - Draws channel name, accent bar, and title.
  3. **Outro Card Drawing:**
     - Draws full-screen card with large bell icon, headline, and subtitle.
  4. **In-Video Lower-Third Pill Banner Drawing:**
     - Transparent RGBA canvas `render_cta_overlay_png(size, headline, subtitle, accent_color, ...)`.
     - Draws a rounded rectangle pill with semi-transparent dark fill and accent border.
     - Renders bell icon on the left, typography on the right.
- **Contract / Test Criteria:**
  - Generates valid PNG images at target dimensions with transparency (RGBA) for overlay mode and RGB for card mode.
  - Tested on headless environment with zero font dependencies.

---

### Milestone 3: FFmpeg Single-Pass Filtergraph & 180s Duration Clamp
*Estimated scope: FFmpeg Core Engine*

- **Target Files:**
  - `app/rendering/engine.py`
  - `app/rendering/filters.py`
  - `app/rendering/audio.py`
  - `tests/test_renderer.py`
- **Deliverables:**
  1. **Video Filtergraph Extension:**
     - When `cta_style == "overlay"`:
       - Input image: `-loop 1 -t {cta_seconds} -i {overlay_png}`.
       - Filter: `overlay=x=(W-w)/2:y=H-h-margin:enable='gte(t,{start_time})'` composited before format mapping.
     - When `cta_style == "outro_card"`:
       - Uses existing concat chain (`[intro][clip][outro]concat=n=3`).
  2. **Audio Filtergraph Extension:**
     - Muxes the generated CTA audio file as an extra FFmpeg input.
     - During the CTA time range, applies `volume=0.25` ducking to the primary gameplay audio.
     - Uses `amix` to combine ducked gameplay with CTA speech + bell sound.
     - Applies final `loudnorm=I=-14:TP=-1.5:LRA=11` filter.
  3. **Duration Enforcement:**
     - Clamps final output to $\le 180.0\text{s}$.
- **Contract / Test Criteria:**
  - Synthetic test video renders through all presets (`landscape`, `vertical_blur`, `third_person`).
  - Output file audio tracks contain audible voiceover + bell and meet -14 LUFS standard.

---

### Milestone 4: Backend API & Service Integration
*Estimated scope: Routers & Services*

- **Target Files:**
  - `app/routers/channel.py`
  - `app/services/channel_profile.py`
  - `app/services/renders.py`
  - `app/services/auto_stage.py`
  - `tests/test_channel_profile.py`
- **Deliverables:**
  1. Extend `GET /api/v1/channel/profile` and `PUT /api/v1/channel/profile` to return and accept intro & CTA parameters.
  2. Add `POST /api/v1/channel/cta/preview-tts`:
     - Body: `{ "speech_text": "...", "voice": "..." }`.
     - Returns audio stream or temporary preview URL.
  3. Add `GET /api/v1/channel/cta/preview-image`:
     - Query params: `style=overlay|outro_card&orientation=vertical|landscape`.
     - Returns PNG preview of the generated banner or card.
  4. Ensure `RenderService.create_render_job()` and `AutoStageService` consume the resolved intro and CTA settings when launching render jobs.
- **Contract / Test Criteria:**
  - API endpoints return `BaseResponse[T]`.
  - Preview endpoints respond in under 500ms with cached assets.

---

### Milestone 5: Frontend UI & Live Brand Preview
*Estimated scope: Next.js Frontend*

- **Target Files:**
  - `ui/src/app/channel/page.tsx`
  - `ui/src/lib/api.ts`
  - `ui/src/types/video.ts`
- **Deliverables:**
  1. Add **"Intro & Call-to-Action (CTA)"** card section to `/channel`:
     - **Intro Card Controls:** Toggle switch, duration slider (0.5s – 3.0s), intro title/subtitle inputs.
     - **CTA Controls:** Toggle switch, style radio buttons (**"In-Video Lower-Third Overlay"** vs **"End Card Screen"**).
     - **CTA Text Inputs:** Headline (`"SUBSCRIBE & TAP 🔔"`), Subtitle (`"Tap the bell for more clips"`), Speech Script input.
     - **Audio Controls:** Voice selector, **"Listen to Voiceover"** test button that plays the synthesized audio + bell chime.
  2. **Interactive Live Preview Canvas:**
     - Toggle between 9:16 Vertical and 16:9 Landscape preview.
     - Displays the simulated video frame with the lower-third pill or end card screen and live text updates.
- **Contract / Test Criteria:**
  - Form state updates cleanly and saves via `PUT /api/v1/channel/profile`.
  - Works responsively across desktop and tablet screen sizes.

---

### Milestone 6: Automated Testing & Documentation
*Estimated scope: QA & Docs*

- **Target Files:**
  - `tests/test_branding_e2e.py`
  - `docs/channel-branding.md`
  - `ROADMAP.md`
- **Deliverables:**
  1. End-to-end pytest covering:
     - Rendering with Intro only.
     - Rendering with In-Video CTA overlay.
     - Rendering with End Card outro.
     - Rendering with both Intro and CTA.
     - Verification that output duration does not exceed 180 seconds.
  2. Update documentation with screenshots/ASCII diagrams explaining the intro and CTA configuration.
- **Contract / Test Criteria:**
  - All tests pass with `uv run pytest`.
  - `uv run ruff check` passes with zero lint or format violations.

---

## 5. Risk Assessment & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **TTS Generation Delay on Render** | High latency if TTS is generated synchronously during FFmpeg job. | Cache synthesized audio by MD5 hash of text+voice. Pre-synthesize audio when the user saves profile in `/channel` so rendering has 0ms audio synthesis wait. |
| **Network Failure during edge-tts synthesis** | Render job failure if internet connection drops. | If TTS synthesis fails, gracefully degrade: mix the bundled local `bell_chime.wav` and render the on-screen visual banner without blocking the render. |
| **Gameplay Dialogue Muffled by Ducking** | Voiceover might clash with game dialogue. | Set ducking ratio to sensible `0.25` with smooth 200ms sigmoid attack and release, leaving enough game presence without muddying the CTA. |
| **Overlapping Watermark and CTA Overlay** | Watermark in bottom-right might collide with lower-third CTA. | Anchor lower-third CTA with standard bottom margin; automatically adjust watermark position or raise CTA baseline if both occupy the lower quadrant. |
