# ⚙️ BackseatCaster — Configuration

Configuration lives in [`app/config.py`](app/config.py) as a Pydantic `Settings` object backed by environment variables and optional `.env` files.

---

## 1. Environment Files

Settings are loaded from the first match in: `.env`, `app/.env`, `../.env` (cwd-relative). Unknown env keys are ignored (`extra="ignore"`). The backend has no committed `.env.example` (the frontend does, in `ui/.env.example`); copy the table below into a local root `.env` as needed.

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
| `GEMINI_API_KEY` | `None` | Gemini key for Shorts copy; falls back to `GOOGLE_API_KEY`, then to deterministic metadata |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for metadata generation |
| `LLM_METADATA_ENABLED` | `True` | Master switch for LLM copy (deterministic generator always available) |
| `YOUTUBE_DAILY_QUOTA_UNITS` | `10000` | Daily YouTube Data API unit budget |
| `YOUTUBE_UPLOAD_QUOTA_COST` | `1600` | Units consumed per upload (6 uploads/day at defaults) |
| `YOUTUBE_QUOTA_TIMEZONE` | `America/Los_Angeles` | Timezone whose midnight resets the quota day |

Staging behaviour: clips are rendered as private vertical Shorts, metadata is generated with Gemini (or the deterministic generator), and staggered `publishAt` slots are assigned so YouTube releases them without the local machine staying online. See [ROADMAP.md](ROADMAP.md) §Phase 8.

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

[`docker-compose.yml`](docker-compose.yml) runs four services:

| Service | Notes |
|---|---|
| `backend` | FastAPI on port 3001, volume-mounted `./data` |
| `worker` | Celery worker sharing the same image and data volume |
| `redis` | Broker + cache (`localhost:6379`) |
| `frontend` | Next.js on port 3000 |

Environment is provided via the compose file; references also use the same defaults above. See [docs/deployment.md](docs/deployment.md).
