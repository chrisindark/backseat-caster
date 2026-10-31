# 📡 BackseatCaster — API Reference

All endpoints are mounted under the `API_PREFIX` (default **`/api/v1`**). Every endpoint except file streams/redirects (noted below) returns the `BaseResponse[T]` envelope:

```json
{
  "success": true,
  "response": { "...payload..." },
  "error": null
}
```

Error responses use the same envelope shape with `success: false` and a populated `error` (status code, detail, error code). Envelope details: [docs/response-envelope.md](docs/response-envelope.md). Interactive docs: `/docs` (Swagger) and `/redoc` — see [docs/openapi-support.md](docs/openapi-support.md).

---

## Root

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | App info: name, version, docs URL, API prefix, default channel |

## Health — `app/routers/health.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Healthcheck incl. Redis/storage status |

## Setup & First-Run Wizard — `app/routers/setup.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/setup/status` | Setup health status: FFmpeg, Disk Space, AI Key (optional), YouTube connected (optional), Zero-Click Ingest (optional) |
| `GET` | `/api/v1/setup/settings` | Active in-app settings (AI model/url, clipping defaults, auto-stage, cleanup, auto-mine, watch folder) |
| `PATCH` | `/api/v1/setup/settings` | Update in-app settings without editing `.env` (persisted to `data/settings.json`) |
| `POST` | `/api/v1/setup/demo` | Seed 60-second Marvel Rivals highlight demo project and render 3 vertical Shorts |

## Channel Brand Profile — `app/routers/channel.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/channel/profile` | Channel defaults: watermark settings, branded intro/outro cards, framing/quality presets, title template, pinned hashtags, privacy, upload slots, timezone and max clip length |
| `PUT` / `PATCH` | `/api/v1/channel/profile` | Update any subset of channel defaults (including `branding_*` and `max_clip_seconds`); omitted fields are untouched, blank text clears back to the default |
| `POST` | `/api/v1/channel/watermark` | Upload/replace the watermark logo (multipart `file`: PNG, JPG or WEBP, max 15 MB); stored under `data/channel/` |
| `DELETE` | `/api/v1/channel/watermark` | Remove the logo and disable the overlay |
| `GET` | `/api/v1/channel/watermark` | Raw image stream for UI preview (not enveloped) |

## Videos — `app/routers/videos.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/videos` | Paginated catalog with search & status filters (`status`: `all`, `downloaded`, `not_downloaded`, `downloading`, `highlights_mined`, `uploaded`, `cleanup_ready`; plus `search`, `channel`, `page`, `limit`) |
| `GET` | `/api/v1/videos/youtube/channel` | Preview channel videos from `yt-dlp` without saving (`channel`, `limit`, `offset`); flags which already exist locally |
| `POST` | `/api/v1/videos` | Create / register a catalog entry (`201`) |
| `POST` | `/api/v1/videos/sync` | Scrape & sync latest videos from the YouTube channel (`yt-dlp`) |
| `GET` | `/api/v1/videos/{video_id}` | Video details incl. local file path, render/upload counts, uploaded highlight links and cleanup flags |
| `PATCH` / `PUT` | `/api/v1/videos/{video_id}` | Update video metadata |
| `DELETE` | `/api/v1/videos/{video_id}` | Delete video from catalog |
| `POST` | `/api/v1/videos/{video_id}/download` | Queue VOD download via `yt-dlp` |
| `GET` | `/api/v1/videos/{video_id}/status` | Live download progress (percent, ETA) |
| `DELETE` | `/api/v1/videos/{video_id}/download` | Remove the downloaded file from disk |
| `POST` | `/api/v1/videos/{video_id}/cleanup` | Reclaim storage: delete the source VOD and/or render folders already uploaded to YouTube (`clean_vod`, `clean_uploaded_renders`, `clean_all_renders`); catalog and upload records are kept |
| `GET` | `/api/v1/videos/{video_id}/stream` | Stream local video file *(file stream — no envelope)* |
| `GET` | `/api/v1/videos/{video_id}/thumbnail` | Serve/extract thumbnail *(file stream — no envelope)* |
| `POST` | `/api/v1/videos/upload` | Direct upload of local/OBS recording (multipart: `file`, optional `title`, `channel_name`) → creates + probes video, generates thumbnail (`201`); chains into auto-mine when `AUTO_MINE_ON_INGEST` is on |
| `GET` | `/api/v1/videos/watch/status` | Watch folder config, whether it exists, how many recordings are waiting, and recent ingest ledger rows (`recent_limit`) |
| `POST` | `/api/v1/videos/watch/scan` | Scan the OBS watch folder once and ingest finished recordings (`dry_run=true` reports without copying) |

## Renders — `app/routers/renders.py`

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/renders` | Create render job from `RenderClipRequest` |
| `POST` | `/api/v1/renders/jobs` | RESTful alias for `POST /renders` |
| `GET` | `/api/v1/renders/jobs` | List jobs (filters: `video_id`, `status`, `limit`) |
| `GET` | `/api/v1/renders/jobs/{job_id}` | Job details |
| `GET` | `/api/v1/renders/jobs/{job_id}/status` | Job status (alias) |
| `POST` | `/api/v1/renders/jobs/{job_id}/retry` | Retry a failed job |
| `PATCH` / `PUT` | `/api/v1/renders/jobs/{job_id}` | Update job |
| `DELETE` | `/api/v1/renders/jobs/{job_id}` | Delete job |
| `GET` | `/api/v1/renders` | List completed clip renders (optional `video_id` filter) |
| `GET` | `/api/v1/renders/{clip_id}` | Clip details |
| `GET` | `/api/v1/renders/{clip_id}/status` | Per-clip render status |
| `GET` | `/api/v1/renders/{clip_id}/manifest` | `manifest.json` contents *(overridden response — raw manifest)* |
| `DELETE` | `/api/v1/renders/{clip_id}` | Delete clip artifacts |
| `POST` | `/api/v1/renders/bulk-delete` (+ aliases `DELETE /renders/bulk`, `DELETE /renders`) | Bulk delete renders |
| `POST` | `/api/v1/renders/cleanup-uploaded` | Delete local render folders for clips already uploaded to YouTube; `RenderJob` records and YouTube links are retained. Body: `sync`, `clean_vod` |
| `POST` | `/api/v1/renders/auto-pipeline` | Maintenance sweep: clean uploaded render folders, then stage the next `AUTO_STAGE_TOP_N` highlights per downloaded video (repeat runs consume the next-best candidates). Body: `stage`, `cleanup`, `clean_vod`, `top_n`, `min_score`, `clipping_mode`, `schedule`, `sync` |
| `POST` | `/api/v1/renders/{clip_id}/upload-selection` | Stage/select clip(s) for upload queue |
| `POST` | `/api/v1/renders/{clip_id}/regenerate-metadata` | Rewrite staged title/description/tags without re-rendering; `{"use_llm": true\|false\|null}` picks AI vs deterministic copy, returns `previous` copy for comparison |
| `GET` | `/api/v1/renders/{clip_id}/stream/{video_type}` | Stream one output format (`landscape`, `vertical_blur`, `vertical_crop`) *(file stream)* |

Render job flow: `POST /renders` → job persisted `pending` → Celery/BackgroundTasks executes FFmpeg → outputs + `manifest.json` land in `./data/renders/<clip_id>/` → poll `/status`. See [docs/rendering.md](docs/rendering.md).

Maintenance is available on demand through the two endpoints above, or scheduled with Celery beat by setting `AUTO_PIPELINE_INTERVAL_MINUTES`. Cleanup removes files only: the `RenderJob` rows remain so upload history, scheduling metadata and YouTube links stay queryable. Source VODs are only removed when **every** completed render for that video is already uploaded and none is pending/rendering.

## Highlights — `app/routers/highlights.py`

Nested under each video: prefix `/api/v1/videos/{video_id}/highlights`.

| Method | Path | Description |
|---|---|---|
| `GET` | `.../highlights/runs` | History of detection runs |
| `POST` | `.../highlights/detect` | Start a highlight mining job (audio scan → ROI → visual match → deep HUD extraction → clustering) |
| `GET` | `.../highlights/status` | Live status of the active run |
| `GET` | `.../highlights` | Ranked candidate list |
| `DELETE` | `.../highlights` | Delete candidates/runs for the video |
| `GET` | `.../highlights/{candidate_id}/thumb.jpg` | Candidate thumbnail *(file stream)* |

Candidate `details` include Phase 3 signals when available: `hero_name`, `multi_kill_chain`, `abilities_used`, `killfeed_chain` (rows, actor/victim teams, attribution, multi-kill label) and `ultimate_casts` (cast timing, charge before/after, post-cast kills). Hero/ability identification requires templates under `HERO_TEMPLATES_DIR`; without them those fields stay `null`/empty. See [docs/highlight-mining.md](docs/highlight-mining.md).

## YouTube (OAuth & Publishing) — `app/routers/youtube.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/youtube/auth/status` | Whether a valid OAuth token exists |
| `GET` | `/api/v1/youtube/auth/url` | Generate consent URL for the OAuth flow |
| `GET` | `/api/v1/youtube/auth/callback` | Browser redirect target (exchanges code → token) *(HTML redirect)* |
| `POST` | `/api/v1/youtube/auth/callback` | Manual code exchange |
| `POST` | `/api/v1/youtube/auth/credentials` | Submit client credentials (`client_secrets.json` upload or inline) |
| `POST` | `/api/v1/youtube/auth/revoke` | Revoke stored token & delete token file |
| `GET` | `/api/v1/youtube/upload/queue` (alias `/api/v1/youtube/queue`) | Staged/selected clips upload queue |
| `POST` | `/api/v1/youtube/upload/selected` | Upload all selected completed clips (`sync=true` waits per-upload) |
| `POST` | `/api/v1/youtube/upload/{clip_id}` | Resumable upload of one clip to YouTube Shorts |
| `GET` | `/api/v1/youtube/quota` | Today's YouTube Data API units used/remaining and upload headroom |
| `GET` | `/api/v1/youtube/staging` | Auto-staged clips awaiting review or scheduled release (with quota summary and `llm_available`) |
| `POST` | `/api/v1/youtube/staging/{clip_id}/schedule` | Set or clear the native `publishAt` timestamp (`{"publish_at": ISO \| null}`) |
| `POST` | `/api/v1/youtube/staging/{clip_id}/publish-now` | Clear the schedule and upload the staged clip immediately |
| `POST` | `/api/v1/youtube/auto-stage` | Render, enrich and schedule the top N highlight candidates for a video |

Unauthenticated upload attempts return `401` until `GET /auth/url` → consent is complete. Quota accounting is advisory: the local counter only charges the 1,600-unit upload cost after YouTube accepts the upload, and `GET /youtube/quota` reports `failed_uploads`, `blocked_reason`, `blocked_until`, `api_quota_exhausted` and `upload_limit_exceeded`. YouTube's `quotaExceeded` (project Data API budget) and `uploadLimitExceeded` (channel video upload limit) are parsed separately, persisted on the upload job, and returned with a human-readable message plus `error_code`/`retry_at` instead of a raw `HttpError`. Sync uploads return `429` for either limit. See [docs/youtube-authentication.md](docs/youtube-authentication.md) and [docs/publishing.md](docs/publishing.md).

---

## Status Codes

The global exception handlers (registered in `app/core/responses.py`) normalize errors:

| Status | Raised when |
|---|---|
| `400` | Invalid upload/multipart parameters, invalid render params |
| `401` | YouTube not authenticated |
| `404` | Unknown video/clip/job/id |
| `409` | Duplicate catalog entry (`POST /videos`) |
| `500` | Unexpected failures (detail logged with request correlation id) |

---

## Correlation IDs

Every request gets `X-Correlation-ID` (and `X-Request-ID`) via `CorrelationIdMiddleware`; both are exposed in CORS responses and included in the log lines for the request. Useful when matching a front-end failure to backend logs.
