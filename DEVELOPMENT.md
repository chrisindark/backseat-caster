# 🛠️ BackseatCaster — Development Guide

> Quick setup: [docs/getting-started.md](docs/getting-started.md) · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · API: [API_REFERENCE.md](API_REFERENCE.md)

Always use [uv](https://docs.astral.sh/uv/) for Python package management. Python 3.11+ (minimum pinned in `requires-python`, dev interpreter in `.python-version`).

---

## 1. Backend Commands

```bash
# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "describe_migration"

# Start FastAPI development server
uv run uvicorn app.main:app --reload --port 3001

# (Optional) Start Celery worker (requires Redis)
uv run celery -A app.worker.celery_app worker --loglevel=info
```

FastAPI docs: `http://127.0.0.1:3001/docs` (OpenAPI support: [docs/openapi-support.md](docs/openapi-support.md)).

---

## 2. Frontend Commands (`ui/`)

```bash
cd ui

npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

Convenience script: `./dev.sh` at the repo root.

---

## 3. Testing & Code Quality

```bash
# Run all tests
uv run pytest

# Run a specific test file
uv run pytest tests/test_api.py -v

# Lint checks
uv run ruff check

# Auto-fix lint issues
uv run ruff check --fix

# Format
uv run ruff format
```

Pre-commit hooks are configured in `.pre-commit-config.yaml`. Test suite layout:

| Test file | Coverage |
|---|---|
| `tests/test_api.py` | Video catalog / download / upload endpoints |
| `tests/test_renderer.py` | FFmpeg render engine (synthetic assets) |
| `tests/test_youtube_upload.py` | OAuth + resumable upload service |
| `tests/test_phase8.py` | Auto-stage, LLM metadata, quota accounting, `publishAt` scheduling |
| `tests/test_auto_pipeline.py` | Uploaded-render cleanup + batched auto-stage sweep |
| `tests/test_highlight_api.py` | Highlight mining endpoints |
| `tests/test_audio_scanner.py`, `test_roi_extractor.py`, `test_visual_matcher.py`, `test_cluster_engine.py`, `test_detectors.py` | Mining pipeline stages |
| `tests/test_killfeed.py`, `test_ultimate_meter.py`, `test_hero_identifier.py`, `test_phase3_integration.py` | Deep visual extraction (killfeed, ultimate OCR, hero/ability templates) |
| `tests/test_logging_and_correlation.py` | Middleware & logging |

Full testing patterns: [docs/testing.md](docs/testing.md).

---

## 4. Coding Conventions

### Services own the logic; routers stay thin
- No DB queries, FFmpeg calls, or complex logic in routers. Delegate to `app/services/**` and map domain exceptions to HTTP status codes there.

### Unified response envelope
Every endpoint (except file streams/redirects) returns `BaseResponse[T]`:

```python
from app.core.responses import BaseResponse

@router.get("/example", response_model=BaseResponse[ExampleResponse])
def get_example():
    return BaseResponse.success_response(response=ExampleService.get_data())
```

Raise `APIException(status_code=..., detail=..., error_code=...)` for domain errors. The frontend's `ui/src/lib/api.ts` unwraps `response.response` automatically. Details: [docs/response-envelope.md](docs/response-envelope.md).

### Background task dispatch
Always use the broker check pattern so local dev works without Redis:

```python
from app.worker.helpers import is_celery_broker_online

if is_celery_broker_online():
    task = my_celery_task.delay(*args)
else:
    background_tasks.add_task(my_sync_or_async_task, *args)
```

- Obtain DB sessions in background jobs via `get_task_db_session()`.
- Always close sessions in `finally` blocks. Details: [docs/background-tasks.md](docs/background-tasks.md).

### FFmpeg rendering
- Per-clip outputs: `landscape.mp4`, `vertical_blur.mp4`, `vertical_crop.mp4`, `manifest.json`.
- Never hardcode encoder flags — call `detect_available_encoders()` / respect `RenderConfig.preferred_encoder`.
- Voiceover narration triggers sidechain ducking with smooth attack/release curves. Details: [docs/rendering.md](docs/rendering.md), [docs/audio-pipeline.md](docs/audio-pipeline.md).

### Database
- SQLite active database; keep `connect_args={"check_same_thread": False}`.
- All datetimes are timezone-aware (`datetime.now(UTC)` / `timezone.utc`).
- Model changes always ship with a matching Alembic migration.

---

## 5. Storage & Path Conventions

- Everything persistent lives under `./data` (or configured paths — see [CONFIGURATION.md](CONFIGURATION.md)):
  - `./data/backseatcaster.db` (SQLite)
  - `./data/downloads/` (VODs, thumbnails)
  - `./data/renders/<clip_id>/` (clips + manifests)
  - `./data/client_secrets.json`, `./data/youtube_token.json` (OAuth)
- Use `pathlib.Path` for all filesystem operations.
- Ensure directories exist with `.mkdir(parents=True, exist_ok=True)`.

---

## 6. Commit Hygiene

- Format with `uv run ruff format` before committing (pre-commit enforces this).
- Keep PRs focused; add tests for new services/endpoints following the existing fixture patterns (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- Record user-facing changes in [CHANGELOG.md](CHANGELOG.md).
