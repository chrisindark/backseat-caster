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

## Videos — `app/routers/videos.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/videos` | Paginated catalog with search & status filters |
| `POST` | `/api/v1/videos` | Create / register a catalog entry (`201`) |
| `POST` | `/api/v1/videos/sync` | Scrape & sync latest videos from the YouTube channel (`yt-dlp`) |
| `GET` | `/api/v1/videos/{video_id}` | Video details incl. local file path |
| `PATCH` / `PUT` | `/api/v1/videos/{video_id}` | Update video metadata |
| `DELETE` | `/api/v1/videos/{video_id}` | Delete video from catalog |
| `POST` | `/api/v1/videos/{video_id}/download` | Queue VOD download via `yt-dlp` |
| `GET` | `/api/v1/videos/{video_id}/status` | Live download progress (percent, ETA) |
| `DELETE` | `/api/v1/videos/{video_id}/download` | Remove the downloaded file from disk |
| `GET` | `/api/v1/videos/{video_id}/stream` | Stream local video file *(file stream — no envelope)* |
| `GET` | `/api/v1/videos/{video_id}/thumbnail` | Serve/extract thumbnail *(file stream — no envelope)* |
| `POST` | `/api/v1/videos/upload` | Direct upload of local/OBS recording (multipart: `file`, optional `title`, `channel_name`) → creates + probes video, generates thumbnail (`201`) |

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
| `GET` | `/api/v1/renders` | Paginated clip catalog |
| `GET` | `/api/v1/renders/{clip_id}` | Clip details |
| `GET` | `/api/v1/renders/{clip_id}/status` | Per-clip render status |
| `GET` | `/api/v1/renders/{clip_id}/manifest` | `manifest.json` contents *(overridden response — raw manifest)* |
| `DELETE` | `/api/v1/renders/{clip_id}` | Delete clip artifacts |
| `POST` | `/api/v1/renders/bulk-delete` (+ aliases `DELETE /renders/bulk`, `DELETE /renders`) | Bulk delete renders |
| `POST` | `/api/v1/renders/{clip_id}/upload-selection` | Stage/select clip(s) for upload queue |
| `GET` | `/api/v1/renders/{clip_id}/stream/{video_type}` | Stream one output format (`landscape`, `vertical_blur`, `vertical_crop`) *(file stream)* |

Render job flow: `POST /renders` → job persisted `pending` → Celery/BackgroundTasks executes FFmpeg → outputs + `manifest.json` land in `./data/renders/<clip_id>/` → poll `/status`. See [docs/rendering.md](docs/rendering.md).

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
| `GET` | `/api/v1/youtube/staging` | Auto-staged clips awaiting review or scheduled release (with quota summary) |
| `POST` | `/api/v1/youtube/staging/{clip_id}/schedule` | Set or clear the native `publishAt` timestamp (`{"publish_at": ISO \| null}`) |
| `POST` | `/api/v1/youtube/staging/{clip_id}/publish-now` | Clear the schedule and upload the staged clip immediately |
| `POST` | `/api/v1/youtube/auto-stage` | Render, enrich and schedule the top N highlight candidates for a video |

Unauthenticated upload attempts return `401` until `GET /auth/url` → consent is complete. Uploads are rejected with `429` once the daily quota budget cannot cover another upload. See [docs/youtube-authentication.md](docs/youtube-authentication.md) and [docs/publishing.md](docs/publishing.md).

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
