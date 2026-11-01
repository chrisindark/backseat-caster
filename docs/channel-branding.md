# Channel Brand Consistency (Tier 3)

The channel profile keeps every clip looking like the same channel without
re-selecting the same settings per clip. It is stored in the SQLite database
(`channel_profiles`, singleton row `id = 1`), not in environment variables.

---

## 1. Where to Edit It

Open **Brand** in the navbar (`/channel`) or use the REST API:

```bash
# Read current channel profile
curl http://localhost:3001/api/v1/channel/profile

# Update presentation preset, framing, quality, and publishing defaults
curl -X PUT http://localhost:3001/api/v1/channel/profile \
  -H 'Content-Type: application/json' \
  -d '{
    "channel_name": "NightOwl",
    "presentation_preset": "viral_kill",
    "default_framing_preset": "third_person",
    "default_quality_preset": "high",
    "target_fps": 60,
    "hook_enabled": true,
    "hook_text": "WAIT FOR THE FLANK...",
    "hook_duration_seconds": 1.5,
    "tracking_enabled": true,
    "kill_effects_enabled": true,
    "cinematic_treatment_enabled": false,
    "loop_optimization": true,
    "bg_music_volume": 0.25,
    "title_template": "{title} | {channel}",
    "pinned_hashtags": ["Shorts", "NightOwl", "MarvelRivals"],
    "default_privacy": "public",
    "upload_slots": ["08:00", "12:30", "18:30"],
    "upload_timezone": "Asia/Kolkata"
  }'

# Upload channel logo watermark
curl -X POST http://localhost:3001/api/v1/channel/watermark \
  -F 'file=@logo.png'

# Upload channel background music track
curl -X POST http://localhost:3001/api/v1/channel/music \
  -F 'file=@background_beat.mp3'
```

---

## 2. Presentation Presets

BackseatCaster provides three deterministic presentation presets. Selecting a preset pre-configures branding, framing, audio, and visual payoffs:

| Preset | Framing | Cards | Watermark | CTA Style | Visual Payoff | Audio / Music |
|---|---|---|---|---|---|---|
| **Viral Kill** *(default)* | `third_person` | Disabled | Subtle lower-right (70% opacity) | Lower-third overlay pill | Clean gameplay focus | 30% bg music volume |
| **Cinematic Kill** | `cinematic` | Disabled | Subtle lower-right | Disabled | Restrained 8% zoom on elimination or midpoint | 20% bg music volume |
| **Multi-Kill Montage** | `third_person` | Disabled | Subtle lower-right | Lower-third overlay pill | Punch-in zoom + combo badges (`DOUBLE KO`, `TEAM WIPE`) | 30% bg music volume |

---

## 3. Background Music & Looping Tools

Creators can upload a dedicated channel background music track to accompany gameplay:

- **Upload & Storage:** `POST /api/v1/channel/music` validates files with `ffprobe` (audio stream presence, valid sample rate, duration), stores the asset securely under `data/channel/music/channel_bg_music<ext>`, and sets `bg_music_path`.
- **Preview & Removal:** `GET /api/v1/channel/music` streams the audio for in-app preview; `DELETE /api/v1/channel/music` removes the track and resets `bg_music_path` to `None`.
- **Sidechain Ducking:** During render, the engine mixes the background track with gameplay audio, ducking music volume to configured levels (`bg_music_volume`, default 0.20-0.30) to preserve dialogue and critical game cues.
- **Graceful Fallback:** If music is unconfigured or the file is missing from disk, renders proceed silently without music.
- **Seamless Loop Optimization:** When `loop_optimization` is enabled:
  - Audio seams receive 50-100ms bidirectional micro-fades (`afade=t=in` / `afade=t=out`) at clip boundaries to eliminate audible clicks and pops on platform repeat loops.
  - Visual continuity is analyzed across the boundary (mean squared error and histogram similarity between first and last frames) and logged to `manifest.json`.

---

## 4. Visual Payoffs & Dynamic Reframing

- **Dynamic Player Tracking (`tracking_enabled`):**
  Uses OpenCV (`cv2`) motion energy and contour centroid analysis to smoothly re-center the 9:16 vertical crop window around active combat and player movement, falling back to static framing if motion is ambiguous.
- **Kill Payoff Badges (`kill_effects_enabled`):**
  Triggers momentary punch-in zooms (12%) and combo notification badges (e.g., `DOUBLE KO`, `TRIPLE KO`, `TEAM WIPE`) at confirmed elimination timestamps detected by the killfeed and HUD analysis.
- **Cinematic Payoff Treatment (`cinematic_treatment_enabled`):**
  Applies an elegant, restrained 8% punch-in zoom (0.50s max duration) centered on the first confirmed elimination or the clip midpoint, without noisy arcade badges or text overlays.
- **Target Frame Rate (`target_fps`):**
  Forces clean 60 FPS or 30 FPS output (via `-r <fps>` flags) with matching audio clock synchronization, or preserves native source rate when unset.
- **High Bitrate Targets (`quality_preset`):**
  Target 12–20 Mbps video bitrates (`high`: 12M, `archive`: 20M, `compact`: 5M) for crisp YouTube Shorts mobile rendering.

---

## 5. Advanced Override Hierarchy

Settings follow a strict three-tier precedence: **Per-Clip Request > Channel Profile Default > Preset Default**.

| Setting | Preset Default | Channel Profile Default | Per-Clip Override |
|---|---|---|---|
| `branding_enabled` | `False` (all presets) | `branding_enabled` | `RenderClipRequest.branding.enabled` |
| `branding_intro` / `outro` | Preset definition | Profile columns | `RenderClipRequest.branding.intro` / `outro` |
| `default_framing_preset` | Preset default (`third_person` / `cinematic`) | `default_framing_preset` | `RenderClipRequest.crop_preset` |
| `default_quality_preset` | `high` | `default_quality_preset` | `RenderClipRequest.quality_preset` |
| `target_fps` | `None` (source native) | `target_fps` (e.g. 60) | `RenderClipRequest.target_fps` |
| `watermark_enabled` | `True` | `watermark_enabled` | `RenderClipRequest.watermark.enabled` |
| `hook_enabled` / `hook_text` | Disabled | Profile hook settings | `RenderClipRequest.hook.*` |
| `kill_effects_enabled` | Preset definition | Profile `kill_effects_enabled` | `RenderClipRequest.kill_effects.enabled` |
| `cinematic_treatment_enabled`| `True` on `cinematic_kill` | Profile override | `RenderClipRequest.cinematic_treatment.enabled`|
| `tracking_enabled` | Preset definition | Profile `tracking_enabled` | `RenderClipRequest.tracking.enabled` |
| `bg_music_volume` | Preset definition | Profile `bg_music_volume` | `RenderClipRequest.music.volume` |
| `loop_optimization` | Preset definition | Profile `loop_optimization` | `RenderClipRequest.loop.enabled` |
| `cta_enabled` / `cta_style` | Preset definition | Profile CTA settings | `RenderClipRequest.cta.*` |

---

## 6. Rendering & Manifest Pipeline

All visual treatments (blur padding, crop window, tracking, punch-in zoom, watermark, hook caption, CTA overlay, intro/outro cards) and audio processing (ducking, background music, TTS voiceover, bell chime, loop fades, EBU R128 loudness normalization) execute inside a **single FFmpeg pass**.

Every render writes a complete `manifest.json` detailing:
- `preset`: Selected presentation preset
- `quality`: Resolved bitrate and encoder flags
- `fps`: Target frame rate and stream probe
- `watermark`: Applied logo, position, opacity, scale, and margin
- `hook`: Hook caption text, position, and timing window
- `kill_effects`: Detected events and combo badges
- `cinematic_treatment`: Target moment, zoom scale, and duration
- `tracking`: Dynamic crop mode and centroid tracking metadata
- `music`: Background track presence and volume
- `loop`: Audio seam smoothing and visual continuity metrics
- `branding`: Intro/outro card durations and total composed length
- `cta`: Call-to-action style, voiceover, and audio mixing details
- `duration_budget`: Target duration and Shorts tier classification
