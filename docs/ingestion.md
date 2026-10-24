# 📥 Ingestion (YouTube & OBS Upload)

Two ways to fill `./data/downloads/` with VODs. Both produce the same catalog model so downstream (studio, mining, rendering) is origin-agnostic. Decision record: [ADR 0006](adr/0006-parallel-youtube-and-local-ingestion.md).

---

## 1. YouTube channel ingestion

**Flow:** channel URL → `yt-dlp` metadata scrape → catalog rows → selective download.

- `POST /api/v1/videos/sync` scrapes channel metadata (titles, durations, IDs) via [`YtdlpService`](../app/services/youtube.py) and inserts/updates catalog entries. The channel comes from the request or `DEFAULT_YOUTUBE_CHANNEL`.
- `POST /api/v1/videos/{id}/download` creates a background download task ([background-tasks.md](background-tasks.md)); `yt-dlp` fetches the best MP4 quality while progress is exposed at `GET /api/v1/videos/{id}/status` (percent + ETA).
- `DELETE /api/v1/videos/{id}/download` removes the file but keeps the catalog row.

Repository-layer notes:

- yt-dlp is invoked as a subprocess with JSON-parse scoping; quality/format selection is centralized in `YtdlpService` — do not add ad-hoc flags in routers.
- Failures during sync are surfaced per item in the sync response envelope rather than aborting the batch.

## 2. Local / OBS upload

**Flow:** drag & drop in the UI → multipart POST → probe + thumbnail → catalog entry ready for studio.

`POST /api/v1/videos/upload` (multipart form):

| Field | Required | Description |
|---|---|---|
| `file` | ✅ | `.mp4`, `.mkv`, `.mov`, `.webm`, ... — rejected with `400` otherwise |
| `title` | — | display title; falls back to filename |
| `channel_name` | — | default `OBS Studio` |

The service streams the upload to `./data/downloads`, then probes it via ffprobe (`app/rendering/probe.py`) to populate duration/codec metadata and extracts a JPEG thumbnail (`<video_id>_thumb.jpg`). The response is the created `VideoResponse` (`201`), same envelope as everything else ([response-envelope.md](response-envelope.md)).

The UI flow lives in `ui/src/components/OBSUploadDropzone.tsx` with a progress bar and instant catalog refresh.

## 3. Serving media back

Both origins resolve to the same playback surface used by the studio:

- `GET /api/v1/videos/{video_id}/stream` — ranges the local file (HTTP range support for seeking).
- `GET /api/v1/videos/{video_id}/thumbnail` — cached `<id>_thumb.jpg` or on-demand extraction.

## 4. Storage rules

| Artifact | Path |
|---|---|
| VOD file | `./data/downloads/` (configured via `DOWNLOADS_DIR`) |
| Thumbnail | `./data/downloads/<video_id>_thumb.jpg` |
| Highlights & renders | separate roots — never write media artifacts here from ingestion code |

All paths are resolved `Path` objects from settings; ingestion code creates parents with `mkdir(parents=True, exist_ok=True)`.

## 5. Testing this area

`tests/test_api.py` covers catalog + upload flows with TestClient; uploads in tests use tiny synthetic videos produced with `lavfi` (`testsrc`) — never real network downloads.
