# 🧩 Concepts

The shared vocabulary of BackseatCaster. Each entry links to the deep dive.

---

## Video (catalog entry)

A VOD record in the SQLite catalog. Origin is either **YouTube** (created by channel sync, downloaded via `yt-dlp`) or **local upload** (OBS recording dragged into the UI). Stores metadata, download state, and local file paths. → [ingestion.md](ingestion.md)

## Download

A background job that fetches the selected video file from YouTube to `./data/downloads/`, with progress/ETA exposed via `GET /videos/{id}/status`. → [ingestion.md](ingestion.md)

## Render Job

A request to cut one or more clip formats out of a time range of a local VOD:

| Output | Dimensions | Notes |
|---|---|---|
| `landscape.mp4` | 1920×1080 | Full-frame master copy |
| `vertical_blur.mp4` | 1080×1920 | Horizontal video padded top/bottom with blurred background |
| `vertical_crop.mp4` | 1080×1920 | Center crop according to `crop_preset` |

Artifacts land in `./data/renders/<clip_id>/` together with `manifest.json`. Job lifecycle states (`pending → processing → completed/failed`) are persisted so the UI can poll. → [rendering.md](rendering.md)

## Crop preset

How a 16:9 frame becomes a 9:16 output:

- `third_person` — 33.33% total blur padding (~16.66% top / bottom) — default.
- `cinematic` — 25% total blur padding.
- `direct_crop` — no padding, full-height center crop.
- `custom` — any `crop_blur_padding` fraction between 0.0 and 0.6.

## Quality preset

Encoder settings tier: `high` (5 Mbit / CRF 21), `compact` (3.5 Mbit / CRF 24), `archive` (20 Mbit / CRF 17). Encoder itself is auto-selected: `h264_videotoolbox` on Apple Silicon, `libx264` otherwise. → [rendering.md](rendering.md)

## Audio ducking & loudness

When a narration voiceover (WAV) is attached to a render, sidechain compression lowers gameplay audio during speech with smooth attack/release; the mix is peak-limited and normalized to EBU R128 **-14 LUFS** (YouTube Shorts standard). → [audio-pipeline.md](audio-pipeline.md)

## Manifest

A per-clip JSON record of every render: probe results (codecs, fps, durations, bitrates), filter chains, timing, and resolved artifact paths — the machine-readable "label" of a clip. → [manifest-format.md](manifest-format.md)

## Highlight Run

One execution of the highlight mining pipeline on a video (audio scan → ROI extraction → color/OCR visual matching → window clustering). Produces ranked **Highlight Candidates** with scores, time windows, and thumbnails. → [highlight-mining.md](highlight-mining.md)

## Highlight Candidate

A proposed clip window (15–45s, padded) with a match score and thumbnail frame. The creator can apply a candidate to the studio timeline (manual route) or feed it forward to the future Gemini verification stage (AI Caster route). → [highlight-mining.md](highlight-mining.md)

## Detector

A game-specific integration point (`app/services/highlight/detectors/`) that defines HUD regions and color/OCR triggers. Ships `marvel_rivals` and a `generic` fallback; the registry resolves the right set. → [highlight-mining.md](highlight-mining.md)

## UploadQueue

Selection state ("this clip goes to YouTube when I'm ready") plus one-click or batch resumable upload to YouTube Shorts. Requires a completed OAuth link. → [publishing.md](publishing.md)

## Auto-stage

Rendering the top-scoring highlight candidates into private vertical Shorts, generating AI (or deterministic) title/description/tags, and assigning staggered native `publishAt` slots. Runs after highlight detection when `AUTO_STAGE_ENABLED` is on, or on demand via `POST /api/v1/youtube/auto-stage`. → [publishing.md](publishing.md)

## Maintenance sweep

Deletes local render folders for clips already uploaded to YouTube while keeping `RenderJob` history and YouTube links, then stages each downloaded video's next `AUTO_STAGE_TOP_N` highlights. Runs on demand via `POST /api/v1/renders/auto-pipeline` or periodically through Celery beat. Source VODs are only removed when every completed render is uploaded. → [publishing.md](publishing.md#5-observability--recovery)

## BaseResponse

The mandatory response envelope `{ success, response, error }` on every endpoint except file streams. Frontend `api.ts` unwraps it automatically. → [response-envelope.md](response-envelope.md)

## Celery fallback

The dispatch rule: use Celery when the Redis broker is online, otherwise run in-process via FastAPI `BackgroundTasks`. Zero config either way. → [background-tasks.md](background-tasks.md)

## Correlation ID

Every HTTP request is stamped with `X-Correlation-ID` (middleware) so one log line accession can be traced across routers, services, and background workers.
