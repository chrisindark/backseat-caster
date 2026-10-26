# 📤 Publishing (YouTube Uploads)

Once OAuth is linked ([youtube-authentication.md](youtube-authentication.md)), clips flow through a staging queue into resumable YouTube Shorts uploads. Business logic: `YouTubeUploaderService` in [`app/services/youtube_uploader.py`](../app/services/youtube_uploader.py).

---

## 1. Concepts

- **Selection / staging:** a completed render can be flagged for upload (`POST /renders/{clip_id}/upload-selection`). Selected clips form the queue visible at `GET /api/v1/youtube/upload/queue`.
- **Creator-in-the-loop:** the pipeline can auto-render and stage clips, but it never uploads on its own — uploads happen on explicit user action only.
- **Resumable upload protocol:** the service uses the YouTube Data API v3 resumable session so large Shorts uploads can retry across network glitches.

## 2. Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/youtube/upload/queue` | Clips staged/selected for upload (alias `/api/v1/youtube/queue`) |
| `POST` | `/api/v1/youtube/upload/selected` | Upload all selected completed clips. `?sync=true` runs uploads inline (blocking) — otherwise background dispatch |
| `POST` | `/api/v1/youtube/upload/{clip_id}` | Upload one clip |

Both upload paths:

1. Verify `auth_status.is_authenticated` — else `401` ("authenticate first via `/api/v1/youtube/auth/url`").
2. Confirm the clip's artifacts exist on disk.
3. Dispatch through the standard Celery/BackgroundTasks rule ([background-tasks.md](background-tasks.md)); synchronous (`sync=true`) returns per-clip results in the envelope.

## 3. Vertical / Shorts flow

Uploads target vertical outputs (`vertical_blur.mp4` / `vertical_crop.mp4`) for Shorts-length content; which format to prefer is part of the selection payload. Keyed details (title, description, tags) are attached at selection time via the upload-selection PATCH — without them, the service still uploads but the video gets a bare title.

## 3.1 Auto-stage & native scheduling

When `AUTO_STAGE_ENABLED` is on (or `auto_render_top_n` is passed to highlight detection), the top-scoring candidates are rendered as private vertical Shorts and staged with Gemini/fallback metadata. `POST /api/v1/youtube/auto-stage` does the same on demand for one video.

- `GET /api/v1/youtube/staging` lists staged clips awaiting review, including the quota summary and `llm_available`.
- `POST /api/v1/youtube/staging/{clip_id}/schedule` sets/clears a native `status.publishAt` timestamp; uploads are private and YouTube releases them at that time.
- `POST /api/v1/youtube/staging/{clip_id}/publish-now` clears the schedule and uploads immediately.
- `GET /api/v1/youtube/quota` reports today's advisory unit usage and upload headroom.

## 4. Batch behavior

`POST /upload/selected` triggers the queue; `batch_upload_clips` task serializes selections with per-clip success records rather than aborting on one failure — the response envelope lists both landed and failed clips. Re-running a batch is safe (artifact missing / already-uploaded checks are idempotent).

## 5. Observability & recovery

- Each clip's upload state is persisted; the UI (`/youtube` page, `UploadQueueModal`) polls the queue for live status.
- Failed uploads report via their clip entry (detail color-coded in the queue modal); resolution steps include re-linking OAuth or re-rendering the clip if the artifact is missing.
- **Retention & cleanup:** uploaded render folders can be reclaimed on demand (`POST /api/v1/renders/cleanup-uploaded` or the `cleanup` option of `POST /api/v1/renders/auto-pipeline`) or on a schedule via Celery beat (`AUTO_PIPELINE_INTERVAL_MINUTES`). Cleanup deletes local files only — `RenderJob` rows, scheduling metadata and YouTube links are retained. Source VODs are only removed when every completed render for that video is uploaded (`AUTO_CLEANUP_VOD`). A deleted local clip keeps its YouTube copy, and deleting the YouTube video does not alter local records.

## 6. Testing

`tests/test_youtube_upload.py` exercises the uploader service against stubbed Google API surfaces — no test ever performs a real upload or writes a real token. Keep it that way.
