# YouTube Shorts Presentation and Editing Plan

## Objective

Create polished vertical gameplay highlights from Marvel Rivals recordings. Gameplay stays in view from the first frame and remains the main focus. Editing should emphasize the important moment without adding distracting effects or branding.

## Product decisions

- **Gameplay-first is the default.** The default Viral Kill presentation starts directly on gameplay and does not insert a full-screen intro or outro.
- **The approved intro and outro cards remain optional.** Creators can enable the current branded cards as a separate presentation choice. They are not used by the gameplay-first default preset.
- **A small in-video subscribe prompt is the default CTA style when enabled.** Full-screen outro cards are optional; spoken CTA audio remains opt-in.
- **No milestone depends on an LLM.** Presets are fixed configurations, hook and CTA copy is entered by the creator, event timing comes from deterministic video/audio analysis, and reframing uses computer-vision tracking. No AI-generated copy or automatic LLM decision-making is in scope.

## Existing implementation

These capabilities are already present and should be reused:

- 1080×1920 vertical outputs with crop and blurred-background modes.
- H.264/AAC rendering, 48 kHz audio, encoder selection with software fallback, and a single-pass render pipeline.
- Static vertical crop presets and blurred background treatment.
- Channel watermark upload and controls for position, scale, opacity, and margin.
- Optional branded intro/outro cards, plus an in-video CTA overlay and optional spoken CTA audio.
- Highlight mining with Marvel Rivals detectors, kill-feed/OCR analysis, and candidate event windows.
- Render manifest, staging, and upload paths that retain composed duration information.

The new card design and complete-CTA-audio behavior are implemented. Cards are still full-frame when enabled, so keep them disabled in the gameplay-first default.

## Milestones

### Milestone 0 — Rendering foundation **(implemented)**

- Keep the 9:16 output, crop/blur modes, H.264/AAC path, and software fallback.
- Preserve gameplay audio, normalize it, and limit peaks.
- Keep intro/outro cards optional and make their preview match the final render.
- Keep final render duration, manifest metadata, staging, and upload selection aligned.

**Resolved:** Target frame rate selection (30/60 fps) and 12–20 Mbps quality bitrates were fully delivered and verified in Milestone 6.

### Milestone 1 — Presentation presets and defaults **(implemented)**

Add three deterministic presets. The creator chooses a preset; settings explicitly changed in the channel profile override that preset.

#### Viral Kill — default

- Gameplay begins immediately.
- No full-screen intro or outro.
- Optional manually written hook caption.
- Subtle watermark.
- Optional small subscribe overlay near the end.
- Natural pacing; no effect that hides the action.

#### Cinematic Kill

- Gameplay begins immediately; minimal text and branding.
- Preserve game audio as the focus.
- Allow a restrained zoom or slow-motion treatment on a selected moment.
- No full-screen intro or outro by default.

#### Multi-Kill Montage

- Gameplay begins immediately with a manually written hook if desired.
- Use detected kill events for a counter and restrained combo notifications.
- Faster cuts only where event timestamps support them.
- Optional subtle subscribe overlay; no full-screen intro or outro by default.

**Acceptance:** presets are selectable and their values can be overridden individually. Preset behavior is configured in code/profile settings; it does not need an LLM to choose a preset or write copy.

### Milestone 2 — Gameplay overlays and subtle branding **(completed)**

Built on the existing watermark and CTA renderer with timing, upper-third hook captions, and text watermark fallbacks.

- Subtle watermark default: top-left, 5–8% width, configurable opacity and position.
- Added watermark `start_seconds` and `end_seconds` time gating in FFmpeg (`enable='between(t,...)'`).
- Text watermark fallback when logo is missing: rasterises `@ChannelHandle` / channel name into a clean semi-transparent PNG.
- Added upper-third hook caption overlay (`HookConfig`, `render_hook_overlay_png`) active during the opening 1–1.5 seconds, avoiding the center 50% crosshairs and combat reticle.
- Configurable in-video CTA overlay pill with position (`bottom` vs `upper_third`), duration (1.0s–10.0s), and custom headlines.
- Preserved existing full-frame branded bookend cards as an optional style.

**Acceptance:** overlays can be disabled independently and do not cover important gameplay areas in landscape or vertical outputs.

### Milestone 3 — Event-aware payoff and kill effects **(completed)**

Deterministic event moments extracted from highlight triggers and structured killfeed chains:

- Exposed reliable event timestamps for eliminations, multi-kills (`DOUBLE KO`, `TRIPLE KO`, `QUAD KO`), and team wipes.
- Restrained punch-in momentary zoom (5–7% zoom for 0.3s) centered on confirmed eliminations using FFmpeg multi-window crop/scale overlays.
- Configurable kill notification banner overlays (`render_kill_notification_png`) positioned in the lower-third or upper-third, leaving combat reticles, killfeed, and bottom HUD completely clear.
- Progressive combo multipliers (`1x`, `2x`, `3x`...) displayed cleanly on chained multi-kills.
- Graceful degradation: when event timestamps are absent or uncertain, renders finish cleanly without punch-in or badge overlays.

**Acceptance:** event overlays line up with their detected timestamps and degrade cleanly when detection is uncertain.

### Milestone 4 — Dynamic vertical reframing **(COMPLETED)**

Add computer-vision-based framing on top of the existing static presets.

- Track the player or relevant action area where the source permits it.
- Smoothly interpolate crop movement and constrain it to valid source bounds.
- Avoid abrupt horizontal jumps and preserve enemies, effects, and essential HUD content where possible.
- Use static crop presets when tracking is unavailable or unreliable.
- Preserve aspect ratio; never stretch gameplay. Keep the blurred-background mode as a fallback.

**Acceptance:** tracking can be disabled, and fallback rendering remains valid for difficult footage. (Verified via `tests/test_player_tracking.py`).

### Milestone 5 — Optional audio and loop tools **(COMPLETED)**

- Keep gameplay audio primary; preserve elimination and ultimate sounds, normalize, and limit peaks.
- Allow creator-supplied background music with a volume control and ducking beneath gameplay or speech. The creator is responsible for using music they can publish.
- Add optional loop optimization using deterministic visual/audio comparisons between the start and end. Never repeat a sequence or compromise the final elimination to create a loop.

**Acceptance:** music and looping are off by default, independently switchable, and do not introduce clipping or obvious audio discontinuities. (Verified via `tests/test_audio_music_loop.py`).

### Milestone 6 — Output quality and publish-path verification **(COMPLETED)**

- Target 1080×1920, 9:16, H.264, yuv420p, AAC at 192 kbps and 48 kHz. Keep source color where possible.
- Add a 60 FPS output option and verify frame pacing; avoid unnecessary frame-rate conversion when source quality would suffer.
- Add a high-quality vertical bitrate target in the 12–20 Mbps range while retaining compact and archive choices.
- Keep encoder hardware acceleration with a tested software fallback.
- Test intro-only, outro-only, overlay-only, and gameplay-first renders.
- Verify duration, A/V synchronization, overlay positions, and final payoff in the actual MP4 and manifest before staging/upload.
- Keep varied highlight lengths. Typical guidance: 12–18 seconds for a single kill, 20–28 seconds for consecutive kills, and 25–35 seconds for a team wipe; do not pad clips to a fixed length.

**Acceptance:** the final staged file matches the selected preset, renders cleanly in both vertical and landscape modes where selected, and passes the render-to-upload duration checks. (Verified via `tests/test_publish_path_verification.py`).

## Configuration principles

- Keep the existing manual channel profile as the source for creator-controlled values.
- Add a `presentation_preset` field with a fixed supported set: `viral_kill`, `cinematic_kill`, and `multi_kill_montage`.
- Add independent settings for watermark timing, hook text/timing/position, kill effects, CTA text/timing/style, background music path/volume, loop optimization, and target frame rate.
- Settings explicitly changed by the creator override preset defaults.
- Keep hook and CTA text as creator-entered values. Do not generate titles, hooks, or spoken scripts with an LLM.
- Preserve a configuration switch for optional full-screen branded intro/outro cards, while leaving them off in the gameplay-first presets.

## Recommended implementation order

1. Implement Milestone 1 so each output style has clear, consistent defaults.
2. Implement Milestone 2, reusing the existing watermark and CTA renderers.
3. Add event timestamps and overlays in Milestone 3.
4. Implement dynamic reframing in Milestone 4.
5. Add optional audio/loop tools in Milestone 5.
6. Complete output-quality and staging/upload verification in Milestone 6.

## Follow-up plan — closing the remaining gaps

Milestones 0–6 are implemented and covered by tests, but the plan is not yet
"done" end to end. The items below are the verified gaps between the code and a
finished, creator-usable feature. Execute in order; each step is independently
shippable and must not depend on an LLM.

### Step 7.1 — Land and format the existing milestone work (COMPLETED)

The M1–M6 implementation currently exists only as uncommitted working-tree
changes (new rendering modules, three Alembic revisions, six test files,
model/schema/engine/UI edits, and new docs).

- [x] Run `uv run ruff format` (currently reports 15 files) and re-run
      `uv run ruff check` until clean.
- [x] Re-run `uv run pytest -q` and `uv run alembic heads` (must remain a
      single head) before committing.
- [x] Commit the milestone work in logical commits so the plan history is
      reviewable: rendering modules → migrations → API/schema → UI → tests →
      docs.

**Acceptance:** `git status` is clean, the tree is formatted, and the full
suite passes from a clean checkout.

### Step 7.2 — Expose the independent settings in the `/channel` UI (COMPLETED)

The backend, schemas, and TypeScript types support every new setting, but the
channel editor only exposes the preset selector and the pre-existing watermark,
CTA, and card controls. A creator cannot currently change the advanced values
without calling the API.

Target files: `ui/src/app/channel/page.tsx`, `ui/src/types/video.ts`.

- [x] **Hook caption:** enabled toggle, text input, start time, duration, and
      `upper_third` / `bottom` position.
- [x] **Kill effects:** enabled toggle (event badges + punch-in) with a short
      explanation that it degrades cleanly when timestamps are missing.
- [x] **Dynamic tracking:** enabled toggle with a "falls back to static crop"
      note.
- [x] **Watermark timing:** optional start/end seconds alongside the existing
      position/size/opacity controls.
- [x] **CTA position:** `bottom` vs `upper_third` selector beside the existing
      style/duration controls.
- [x] **Output:** target frame-rate selector (Match source / 30 / 60).
- [x] Add every field to the `ChannelProfileUpdate` payload in `handleSave` and
      read it back in `applyProfile`.

**Acceptance:** saving in the UI persists each value, reloading the page shows
the saved value, and a preset selection still seeds defaults that explicit
values override. `npx tsc --noEmit` and `npm run lint` stay clean.

### Step 7.3 — Add first-class background-music upload (COMPLETED)

`bg_music_path` is a raw filesystem path with no upload flow, so
"creator-supplied background music" is impractical. Mirror the existing
watermark upload pattern.

Target files: `app/routers/channel.py`, `app/services/channel_profile.py`,
`ui/src/app/channel/page.tsx`, `ui/src/lib/api.ts`.

- [x] `POST /api/v1/channel/music` (multipart) validates the file with
      `ffprobe`, stores it under `data/channel/music/`, and writes
      `bg_music_path`.
- [x] `GET` / `DELETE /api/v1/channel/music` for preview and removal, returning
      `BaseResponse[T]`.
- [x] Expose upload, remove, and volume controls in the `/channel` audio
      section.
- [x] Rendering keeps the current behaviour: missing file or disabled music
      renders silently without music.

**Acceptance:** an uploaded track is used by the next render, deleting it
reverts cleanly, and the manifest still records the resolved music settings.

### Step 7.4 — Implement the Cinematic Kill treatment

`cinematic_kill` promises "a restrained zoom or slow-motion treatment on a
selected moment", but no slow-motion code exists and the preset disables kill
effects, so it currently has no payoff treatment.

Target files: `app/rendering/presentation.py`, `app/rendering/engine.py`,
`app/rendering/filters.py`, `tests/test_presentation_presets.py`.

- [x] Choose the treatment deterministically: the confirmed elimination
      timestamp when available, otherwise the clip midpoint.
- [x] Implement a restrained, bounded effect (short punch-in zoom and/or a
      brief speed ramp) with a fixed maximum duration and zoom factor.
- [x] Keep audio in sync when time-stretching (`setpts` paired with the matching
      `atempo`), and never let the effect cover the final elimination.
- [x] Make the treatment opt-out via an explicit override, and leave the other
      presets unchanged.

**Acceptance:** the cinematic preset applies the effect at the chosen moment,
A/V stays aligned, other presets render identically, and disabling the effect
returns a plain render.

### Step 7.5 — Declare direct media dependencies

`tracking.py` and `loop.py` import `cv2` and `numpy`, which are only available
transitively via `rapidocr-onnxruntime`; a future dependency change would break
Milestones 4 and 5 silently.

- [x] Add `opencv-python-headless` (or the project's chosen OpenCV build) and
      `numpy` to `pyproject.toml`.
- [x] Confirm the Docker image and a fresh `uv sync` both install them.
- [x] Re-run the tracking, loop, and render tests.

**Acceptance:** a clean environment installs the declared packages and the
tracking/loop test files pass without relying on another package's tree.

### Step 7.6 — Make A/V sync and payoff verification explicit

Milestone 6 verifies duration, dimensions, frame rate, and stream presence, but
not stream sync or that the payoff survives into the encoded file.

Target files: `tests/test_publish_path_verification.py`.

- [x] Assert the audio and video stream durations agree within a small tolerance
      for overlay-only, intro-only, outro-only, and gameplay-first renders.
- [x] Sample frames at the expected overlay timestamps and assert the overlay is
      present where intended and absent after its window ends.
- [x] Assert the final elimination window is still intact when kill effects are
      enabled.

**Acceptance:** the added checks fail on a deliberately offset or clipped
render and pass on the current pipeline.

### Step 7.7 — Reconcile documentation

- [x] Update `docs/channel-branding.md` with the new controls, the music upload
      flow, and the advanced override table.
- [x] Update `ROADMAP.md` so the Tier 3 branding entry lists the presets,
      overlays, tracking, audio/loop tools, and quality targets.
- [x] Mark this follow-up section complete, or move any deferred items into a
      clearly labelled "Deferred" subsection with the reason.
- [x] Remove the now-resolved "Current gap" note under Milestone 0 (frame rate
      and 12–20 Mbps bitrate were delivered in Milestone 6).

**Acceptance:** docs match the shipped UI/API, and no milestone claims work that
does not exist in the repository.
