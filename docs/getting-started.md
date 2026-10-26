# 🚀 Getting Started

> Prerequisites: Python 3.11+ with [uv](https://docs.astral.sh/uv/), [FFmpeg](https://ffmpeg.org/) + ffprobe on `PATH`, Node.js (LTS) for the UI. Optional: Redis, Docker, a Google Cloud project for YouTube publishing.

---

## 1. Clone & Install

```bash
git clone <your-fork-url> backseat-caster
cd backseat-caster

# Backend
uv sync

# Frontend
cd ui && npm install && cd ..
```

## 2. Configure

Configuration is env-driven (see [CONFIGURATION.md](../CONFIGURATION.md)). Sensible defaults work out of the box; common settings:

```dotenv
# .env (repo root) — optional; all have defaults
DEBUG=True
API_PREFIX=/api/v1
DEFAULT_YOUTUBE_CHANNEL=<your-channel-handle>   # used by /videos/sync when unset per-request
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///./data/backseatcaster.db
# YouTube publishing (only needed for uploads)
YOUTUBE_CLIENT_SECRETS_FILE=./data/client_secrets.json
YOUTUBE_TOKEN_FILE=./data/youtube_token.json
```

Runtime directories auto-create on startup: `data/downloads`, `data/renders`, `data/highlights`, `data/hero_templates` (optional Phase 3 hero/ability templates).

## 3. Migrate

```bash
uv run alembic upgrade head
```

## 4. Run

**Backend only:**

```bash
uv run uvicorn app.main:app --reload --port 3001
```

- API root: `http://127.0.0.1:3001/api/v1/health`
- Swagger UI: `http://127.0.0.1:3001/docs`

**With Celery worker (optional, needs `redis-server`):**

```bash
redis-server &
uv run celery -A app.worker.celery_app worker --loglevel=info
# optional: periodic cleanup + auto-stage sweep
uv run celery -A app.worker.celery_app beat --loglevel=info
```

Without Redis the app transparently uses FastAPI background tasks — nothing to configure. See [background-tasks.md](background-tasks.md).

**Frontend:**

```bash
cd ui && npm run dev   # http://localhost:3000
```

**Everything at once (Docker):**

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Next.js UI | http://localhost:3000 |
| FastAPI | http://localhost:3001 (docs at `/docs`) |
| Celery beat | — (set `AUTO_PIPELINE_INTERVAL_MINUTES` to enable the maintenance sweep) |
| Redis | localhost:6379 |

Data persists under `./data`.

## 5. First End-to-End Run

1. **Get a VOD** — either `POST /api/v1/videos/sync` (scrape your YouTube channel) then `POST /api/v1/videos/{id}/download`, or drag-drop a local OBS recording in the UI (`POST /api/v1/videos/upload`). See [ingestion.md](ingestion.md).
2. **(Optional) Mine highlights** — `POST /api/v1/videos/{id}/highlights/detect`, then browse ranked candidates in the studio drawer. See [highlight-mining.md](highlight-mining.md).
3. **Open the Studio** — `ui` route `/studio/[id]`: pick a time range, choose crop mode, preview.
4. **Render** — creates a job; outputs `landscape.mp4`, `vertical_blur.mp4`, `vertical_crop.mp4` + `manifest.json` under `./data/renders/<clip_id>/`. See [rendering.md](rendering.md) and [manifest-format.md](manifest-format.md).
5. **Publish (optional)** — link YouTube via OAuth (`/youtube` page), then upload staged clips as Shorts. See [youtube-authentication.md](youtube-authentication.md) and [publishing.md](publishing.md).

## 6. Verify the Install

```bash
uv run pytest            # full test suite should pass
uv run ruff check        # lint should be clean
curl -s localhost:3001/api/v1/health
```

## Next Steps

- [concepts.md](concepts.md) — the vocabulary of the pipeline
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — how the pieces fit
- [../API_REFERENCE.md](../API_REFERENCE.md) — every endpoint
- [../examples/](../examples/) — copy-paste API & CLI examples
