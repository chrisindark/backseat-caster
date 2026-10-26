# 🐳 Deployment

BackseatCaster runs happily as a **local-first laptop app** and as **self-hosted Docker**. Anything else (public URL behind auth proxy, NAS, server) works but follows the same rules below.

---

## 1. Local-first (development mode)

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 3001
# optional worker (better throughput for renders + downloads)
uv run celery -A app.worker.celery_app worker --loglevel=info
```

Without Redis the app self-degrades to `BackgroundTasks` ([background-tasks.md](background-tasks.md)) — local-first means the default install needs essentially nothing.

## 2. Docker Compose (recommended self-host)

```bash
docker compose up --build
```

| Service | Role | Port |
|---|---|---|
| `backend` | FastAPI | 3001 |
| `worker` | Celery worker (same image, shares `./data`) | — |
| `celery_beat` | Celery beat scheduler for the maintenance sweep (set `AUTO_PIPELINE_INTERVAL_MINUTES`; `0` disables) | — |
| `redis` | broker + cache | 6379 |
| `frontend` | Next.js | 3000 |

Notes:

- `./data` is volume-mounted, so DB, downloads, renders, highlights, and OAuth credentials survive rebuilds ([CONFIGURATION.md](../CONFIGURATION.md) paths).
- Uploaded render folders can be purged on demand or by the beat sweep; see [publishing.md](publishing.md#5-observability--recovery) for what is retained and when source VODs are safe to delete.
- The `ffmpeg` toolchain must exist inside the backend/worker image — verify with `docker compose exec backend ffmpeg -version` and check that `libx264` is present (`-encoders` list).
- The first `uv run alembic upgrade head` migration inside the fresh container has to have been baked in (or run once at startup) before routes can touch the DB.

## 3. Production checklist

- **Bind address:** set `HOST`/`PORT` deliberately; behind a reverse proxy, prefer `uvicorn` without `--reload` and let the proxy own TLS.
- **CORS:** keep `CORS_ORIGINS` a literal list matching your frontend origin; never ship the comma-fallback wildcard (`*`) to a shared network.
- **Celery on one broker:** run exactly one Redis instance shared by backend + worker (the compose file does this); don't point `REDIS_URL` and `CELERY_BROKER_URL` at different instances unintentionally.
- **Migrations:** run `alembic upgrade head` as a deploy step (or entrypoint) rather than relying on autogenerate at runtime.
- **Backups:** `data/backseatcaster.db` (SQLite — take a file-level backup while idle), plus `./data` if you want your renders preserved.
- **Timezone-awareness:** nothing needs TZ configuration; all stored timestamps are UTC.

## 4. Scaling expectations

- SQLite + a single worker is the design envelope — heavy parallel renders will queue (which is fine locally). Multi-node Celery would require swapping to Postgres and configuring a shared filesystem for `./data`; this is out of scope today.
- GPU acceleration: Apple Silicon machines get `h264_videotoolbox` for free; Linux hosts fall back to `libx264` unless NVENC/VAAPI support is added in `RenderConfig` explicitly ([rendering.md](rendering.md), [ADR 0005](adr/0005-automatic-encoder-selection.md)).

## 5. Health & smoke tests after deploy

```bash
curl -s https://your-host/api/v1/health
curl -s https://your-host/ | jq   # envelope with app + version
uv run pytest -k "not integration"  # from a dev checkout against a copy of prod data
```

And a manual E2E: sync a channel → download → render one clip → confirm `/renders` shows it with a valid manifest ([manifest-format.md](manifest-format.md)).
