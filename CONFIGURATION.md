# ⚙️ BackseatCaster — Configuration

Configuration lives in [`app/config.py`](app/config.py) as a Pydantic `Settings` object backed by environment variables and optional `.env` files.

---

## 1. Environment Files

Settings are loaded from the first match in: `.env`, `app/.env`, `../.env` (cwd-relative). Unknown env keys are ignored (`extra="ignore"`). A commented template lives in [`app/.env.example`](app/.env.example); copy the values you need into a local root `.env`.

---

## 2. Application

| Variable | Type | Default | Description |
|---|---|---|---|
| `PROJECT_NAME` | `str` | `BackseatCaster API` | API title shown in OpenAPI docs |
| `VERSION` | `str` | `0.1.0` | App version |
| `DEBUG` | `bool` | `True` | Debug mode flag |
| `HOST` | `str` | `127.0.0.1` | Uvicorn bind host (used by `python -m app.main`) |
| `PORT` | `int` | `8000` | Uvicorn bind port (used by `python -m app.main`) |
| `API_PREFIX` | `str` | `/api/v1` | Mount prefix for all routers |
| `CORS_ORIGINS` | `list[str] \| str` | `["http://localhost:3000","http://127.0.0.1:3000"]` | Allowed origins. Accepts a JSON array or comma-separated string (validator normalizes both) |

> Note: dev servers are usually started with an explicit port (`uvicorn ... --port 3001`), which overrides `PORT`.

---

## 3. Database

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | `str` | `sqlite:///./data/backseatcaster.db` | SQLAlchemy URL (SQLite) |
| `DB_POOL_SIZE` | `int` | `20` | Connection pool size |
| `DB_MAX_OVERFLOW` | `int` | `10` | Max overflow connections |
| `DB_POOL_TIMEOUT` | `float` | `30.0` | Pool checkout timeout (s) |
| `DB_POOL_RECYCLE` | `int` | `1800` | Connection recycle age (s) |

Schema changes must ship with an Alembic migration: `uv run alembic revision --autogenerate -m "..."`.

---

## 4. Storage Paths

All runtime artifacts must stay under `./data`. Paths accept relative or absolute strings and are resolved via `pathlib.Path`.

| Variable | Default | Content |
|---|---|---|
| `DOWNLOADS_DIR` | `./data/downloads` | VOD files + `<video_id>_thumb.jpg` thumbnails |
| `RENDERS_DIR` | `./data/renders` | Per-clip output dirs (`landscape.mp4`, `vertical_blur.mp4`, `vertical_crop.mp4`, `manifest.json`) |
| `HIGHLIGHTS_DIR` | `./data/highlights` | Highlight run artifacts and candidate thumbnails |
| `HERO_TEMPLATES_DIR` | `./data/hero_templates` | User-supplied hero portrait / ability icon templates (`<game>/heroes/*.png`, `<game>/abilities/*.png`) |
| `CHANNEL_ASSETS_DIR` | `./data/channel` | Uploaded channel watermark/logo assets managed from the `/channel` UI |

All four storage directories (`downloads`, `renders`, `highlights`) plus the parent dirs of the OAuth files are created on startup by `Settings.ensure_directories()`.

---

## 5. Celery & Redis

| Variable | Type | Default | Description |
|---|---|---|---|
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | Runtime cache client (ping health check, key-value helpers) |
| `REDIS_TTL` | `int` | `3600` | Default cache TTL (s) — must parse as int |
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/0` | Celery result backend |

If `is_celery_broker_online()` returns `False`, background work transparently falls back to FastAPI `BackgroundTasks` — no configuration required. See [docs/background-tasks.md](docs/background-tasks.md) and [docs/caching.md](docs/caching.md).

---

## 6. YouTube (Ingestion & Publishing)

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_YOUTUBE_CHANNEL` | `""` | Channel handle/URL used by `POST /api/v1/videos/sync` when the request doesn't specify one |
| `YOUTUBE_CLIENT_SECRETS_FILE` | `./data/client_secrets.json` | Google OAuth client secrets (user-provided) |
| `YOUTUBE_TOKEN_FILE` | `./data/youtube_token.json` | Stored OAuth token (written on first consent) |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | `None` | Optional inline alternative to the secrets file |
| `YOUTUBE_REFRESH_TOKEN` | `None` | Optional pre-obtained refresh token |
| `YOUTUBE_REDIRECT_URI` | `http://localhost:3001/api/v1/youtube/auth/callback` | OAuth redirect target (must match Google Cloud Console config) |

OAuth details: [docs/youtube-authentication.md](docs/youtube-authentication.md), [SECURITY.md](SECURITY.md).

### 6.1 Phase 8 — Auto-Stage, LLM Metadata & Quota

| Variable | Default | Description |
|---|---|---|
| `AUTO_STAGE_ENABLED` | `False` | Run auto-staging automatically after highlight detection completes |
| `AUTO_STAGE_TOP_N` | `3` | How many top-scoring candidates to render and stage (0 disables) |
| `AUTO_STAGE_MIN_SCORE` | `0.6` | Minimum candidate score eligible for auto-staging |
| `AUTO_STAGE_CLIPPING_MODE` | `third_person` | Vertical render mode for staged clips (`third_person`, `direct_crop`, `cinematic`, `vertical_blur`) |
| `AUTO_STAGE_FIRST_SLOT_HOURS` | `1` | Hours from now before the first native `publishAt` slot |
| `AUTO_STAGE_INTERVAL_HOURS` | `24` | Spacing between consecutive scheduled releases (min 1) |
| `AUTO_STAGE_TIMEZONE` | `Asia/Kolkata` | Timezone used to interpret `AUTO_STAGE_DAILY_SLOTS` |
| `AUTO_STAGE_DAILY_SLOTS` | `["08:00", "12:30", "16:00", "18:30", "20:30", "23:00"]` | Daily local release times; when set, schedules roll across days instead of using the interval |
| `LLM_METADATA_ENABLED` | `False` | Master switch for AI copy (deterministic generator used by default when false) |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Base URL for OpenAI-compatible endpoint (Ollama, LM Studio, Groq, OpenAI, Gemini) |
| `LLM_API_KEY` | `None` | Optional API key (not required for local Ollama; falls back to `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`) |
| `LLM_MODEL` | `llama3.2` | Model name for chat completions (e.g. `llama3.2`, `gpt-4o-mini`, `gemini-2.5-flash`) |
| `GEMINI_API_KEY` | `None` | (Legacy) Gemini key; automatically resolves to Gemini's OpenAI-compatible endpoint |
| `GEMINI_MODEL` | `gemini-2.5-flash` | (Legacy) Model name when using Gemini key |
| `YOUTUBE_DAILY_QUOTA_UNITS` | `10000` | Daily YouTube Data API unit budget |
| `YOUTUBE_UPLOAD_QUOTA_COST` | `1600` | Units consumed per upload (6 uploads/day at defaults) |
| `YOUTUBE_QUOTA_TIMEZONE` | `America/Los_Angeles` | Timezone whose midnight resets the quota day |

Staging behaviour: clips are rendered as private vertical Shorts, metadata is generated with deterministic copy by default (or AI copy when enabled), and staggered `publishAt` slots are assigned so YouTube releases them without the local machine staying online. The local quota counter charges `YOUTUBE_UPLOAD_QUOTA_COST` only after YouTube accepts an upload; `quotaExceeded` and channel-level `uploadLimitExceeded` responses are tracked separately so the UI can explain which limit was hit. See [ROADMAP.md](ROADMAP.md) §Phase 8.

### 6.2 Maintenance Pipeline — Uploaded Render Cleanup & Batch Staging

| Variable | Default | Description |
|---|---|---|
| `AUTO_CLEANUP_UPLOADED_RENDERS` | `True` | When the scheduled sweep runs, delete render folders for clips already uploaded to YouTube (DB records are kept) |
| `AUTO_CLEANUP_VOD` | `False` | Also delete source VODs once every completed render for that video is uploaded; skipped while any render is pending/rendering |
| `AUTO_PIPELINE_INTERVAL_MINUTES` | `0` | Minutes between automatic maintenance sweeps via Celery beat (`0` disables scheduling) |

The sweep stages each downloaded video's next `AUTO_STAGE_TOP_N` highlights (highest-scoring video first), so the backlog is consumed in batches across repeated runs. Trigger it on demand with `POST /api/v1/renders/auto-pipeline`, or cleanup-only with `POST /api/v1/renders/cleanup-uploaded`. Scheduling requires Celery beat (`uv run celery -A app.worker.celery_app beat`); the Compose `celery_beat` service runs it automatically.

### 6.3 Zero-Input Ingest — Auto-Mine & OBS Watch Folder

Both features are also editable from the setup wizard (`/setup`) and persist to `data/settings.json`, so editing `.env` is optional.

| Variable | Default | Description |
|---|---|---|
| `AUTO_MINE_ON_INGEST` | `False` | Mine highlights automatically as soon as a download or OBS upload completes |
| `AUTO_MINE_GAME` | *(unset)* | Pin a detector profile (`marvel_rivals`, `fall_guys`, …); unset auto-detects from the video title/description |
| `AUTO_MINE_MIN_SCORE` | `0.5` | Minimum candidate score retained by the auto-mine scan |
| `AUTO_MINE_AUTO_RENDER_TOP_N` | *(unset)* | Candidates to auto-render after mining; unset falls back to `AUTO_STAGE_TOP_N` when `AUTO_STAGE_ENABLED=True`, otherwise `0` (mine only) |
| `WATCH_DIR` | *(unset)* | Folder to watch for finished OBS recordings; setting it enables the watch folder |
| `WATCH_POLL_INTERVAL_MINUTES` | `0` | Minutes between Celery beat watch-folder polls (`0` = manual `POST /api/v1/videos/watch/scan` only) |
| `WATCH_STABILITY_SECONDS` | `10` | A file is only ingested once its mtime is older than this, preventing truncated files while OBS is still writing |
| `WATCH_MIN_FILE_MB` | `1.0` | Ignore files smaller than this (partial/empty recordings) |
| `WATCH_DELETE_AFTER_INGEST` | `False` | `False` copies the recording into `data/downloads`; `True` moves it out of the watch folder |
| `WATCH_VIDEO_EXTENSIONS` | `.mp4 .mkv .mov .webm .flv .ts .m4v` | Accepted extensions (JSON array or comma-separated) |

Example zero-touch setup:

```dotenv
WATCH_DIR=/Users/you/Movies/OBS
WATCH_POLL_INTERVAL_MINUTES=5
AUTO_MINE_ON_INGEST=True
AUTO_STAGE_ENABLED=True
AUTO_STAGE_TOP_N=3
```

Record, stop, and the recording is picked up within five minutes, mined, and its three best moments are staged as Shorts with `publishAt` slots. Ingests are de-duplicated per source path using a `size:mtime` fingerprint in the `watch_ingests` table, so polls never re-ingest the same take — but a filename OBS overwrites with a new recording is picked up again. See [ROADMAP.md](ROADMAP.md) §Phase 10.

### 6.4 Branded Intro & Outro Cards

Every render can start with a channel card and end with a `SUBSCRIBE` card. Both are also editable from the setup wizard (`/setup`) and persist to `data/settings.json`.

| Variable | Default | Description |
|---|---|---|
| `BRANDING_ENABLED` | `False` | Master switch; off renders exactly the requested window |
| `BRANDING_CHANNEL_NAME` | *(unset)* | Handle/name printed on the intro card and under the outro headline (falls back to `DEFAULT_YOUTUBE_CHANNEL`) |
| `BRANDING_INTRO_ENABLED` | `True` | Include the intro card when branding is on |
| `BRANDING_OUTRO_ENABLED` | `True` | Include the outro card when branding is on |
| `BRANDING_INTRO_SECONDS` | `1.2` | Intro length (0.2–5.0 s) |
| `BRANDING_OUTRO_SECONDS` | `2.0` | Outro length (0.2–10.0 s) |
| `BRANDING_INTRO_TITLE` | *(unset)* | Intro headline; unset uses the channel name |
| `BRANDING_INTRO_SUBTITLE` | *(unset)* | Intro second line (hidden when empty) |
| `BRANDING_OUTRO_TITLE` | `SUBSCRIBE` | Outro headline |
| `BRANDING_OUTRO_SUBTITLE` | *(unset)* | Outro second line; unset uses the channel name |
| `BRANDING_BACKGROUND_COLOR` | `#0B0D13` | Card background |
| `BRANDING_ACCENT_COLOR` | `#F43F5E` | Accent rules and outro subtitle colour |
| `BRANDING_TEXT_COLOR` | `#FFFFFF` | Headline colour |
| `BRANDING_FONT_PATH` | *(unset)* | Optional TTF/OTF override for card typography |

How it renders: cards are drawn locally with Pillow at each output's exact size (one pair per requested format) and fed back into the same single FFmpeg pass as looped image inputs, so there is no second encode generation and no dependency on FFmpeg's `drawtext`/libfreetype. The clip audio is delayed by the intro and padded with silence so lip-sync stays correct behind both cards.

Notes:

- Bookends add `BRANDING_INTRO_SECONDS + BRANDING_OUTRO_SECONDS` to the clip. Nothing is trimmed automatically — if the total crosses 60 s the upload is no longer a Short, so shorten the clip window or the cards.
- `manifest.json` records the applied branding and the composed `outputs.*.duration`, which includes the cards.
- `docker-compose.yml` installs `fonts-dejavu-core` in the backend image; on bare macOS the system Arial face is used, and Pillow's bundled font is the last-resort fallback.

```dotenv
BRANDING_ENABLED=True
BRANDING_CHANNEL_NAME=@YourChannel
BRANDING_INTRO_SECONDS=1.2
BRANDING_OUTRO_SECONDS=2.0
```

---

## 7. Render Defaults (not .env)

Render tuning is request-level and code-located in [`app/rendering/config.py`](app/rendering/config.py), not environment-driven:

- **Crop padding presets:** `third_person` (33.33%), `cinematic` (25%), `direct_crop` (0%); custom value `crop_blur_padding` ∈ [0.0, 0.6].
- **Quality presets:** `high` (VideoToolbox 5 Mbit avg / libx264 CRF 21), `compact` (3.5 Mbit / CRF 24), `archive` (20 Mbit / CRF 17).
- **Output dimensions:** 1920×1080 landscape, 1080×1920 vertical.
- **Encoders:** `auto` selects `h264_videotoolbox` on Apple Silicon, `libx264` elsewhere (see [ADR 0005](docs/adr/0005-automatic-encoder-selection.md)).

Details: [docs/rendering.md](docs/rendering.md).

---

## 8. Docker Configuration

[`docker-compose.yml`](docker-compose.yml) runs five services:

| Service | Notes |
|---|---|
| `backend` | FastAPI on port 3001, volume-mounted `./data` |
| `worker` | Celery worker sharing the same image and data volume |
| `celery_beat` | Celery beat scheduler for the maintenance sweep; reads `AUTO_PIPELINE_INTERVAL_MINUTES` |
| `redis` | Broker + cache (`localhost:6379`) |
| `frontend` | Next.js on port 3000 |

Environment is provided via the compose file; references also use the same defaults above. See [docs/deployment.md](docs/deployment.md).
