# 🎙️ BackseatCaster — Agent Development Guide (`GEMINI.md`)

Welcome to the **BackseatCaster** repository. This document serves as the primary context, architectural blueprint, and coding standard for AI agents and pair programmers working on this project.

---

## 1. Project Overview & Philosophy

**BackseatCaster** is a local-first AI video editing pipeline designed to transform gameplay recordings (VODs) into high-impact gaming clips, highlights, and YouTube Shorts.

### Core Tenets
- **Local-First Processing:** Video probing, clipping, audio ducking, and rendering execute locally via FFmpeg, taking advantage of Apple Silicon hardware acceleration (`h264_videotoolbox`) when available.
- **Creator Control:** Human-in-the-loop review and approval workflow before any clips are exported or published.
- **Graceful Degradation:** Heavy worker tasks (downloads, rendering, uploads) run through Celery + Redis when online, with an automatic, zero-configuration fallback to FastAPI `BackgroundTasks` when Redis is unavailable.
- **Unified API Contract:** All API endpoints strictly envelope responses using `BaseResponse[T]`.

---

## 2. Technology Stack

### Backend
- **Language & Runtime:** Python 3.11+ (running on Python 3.14 managed by [`uv`](https://docs.astral.sh/uv/))
- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- **Validation & Settings:** Pydantic v2 + `pydantic-settings`
- **Database & ORM:** SQLAlchemy 2.0 + SQLite (`data/backseatcaster.db`)
- **Database Migrations:** Alembic
- **Asynchronous Processing:** Celery (Redis broker) with fallback to FastAPI `BackgroundTasks`
- **Video & Media Processing:** `yt-dlp` (metadata scraping & downloads), FFmpeg / ffprobe (rendering, filtering, ducking)
- **External Integrations:** Google APIs Client Library / OAuth 2.0 for YouTube Data API v3 uploads
- **Testing:** `pytest`, `pytest-asyncio`, `httpx` (FastAPI `TestClient`)
- **Linting & Formatting:** `ruff`, `pre-commit`

### Frontend (`ui/`)
- **Framework:** Next.js 16 (App Router, React 19, TypeScript)
- **UI Components:** `@radix-ui/themes`, `@base-ui/react`
- **Styling:** Tailwind CSS v4, Dark gaming aesthetic
- **Icons & Animation:** `lucide-react`, `framer-motion`

---

## 3. Repository Architecture & Directory Layout

```
backseat-caster/
├── app/
│   ├── main.py                  # FastAPI application entry point, middleware, lifecycle
│   ├── config.py                # Pydantic Settings (paths, DB, Celery, YouTube, CORS)
│   ├── database.py              # SQLite SQLAlchemy engine, SessionLocal, get_db, get_task_db_session
│   ├── core/                    # Core infrastructure
│   │   ├── responses.py         # BaseResponse envelope, APIException, global exception handlers
│   │   ├── middlewares.py       # Correlation ID and request tracing middleware
│   │   └── logger.py            # Colored logging setup
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── video.py             # Video metadata, download state, file paths
│   │   └── render_job.py        # Render job lifecycle, crop settings, upload staging
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── video.py             # Video catalog and download schemas
│   │   ├── render.py            # Clip rendering parameters, manifests, job status
│   │   └── youtube.py           # OAuth auth status, upload requests, batch responses
│   ├── services/                # Business logic layer (keep routers thin)
│   │   ├── videos.py            # VideoService: DB queries, download triggers, local file info
│   │   ├── renders.py           # RenderService: render job creation, manifest formatting, deletions
│   │   ├── youtube.py           # YtdlpService: YouTube channel scraping and yt-dlp handling
│   │   └── youtube_uploader.py  # YouTubeUploaderService: OAuth consent, token storage, resumable upload
│   ├── routers/                 # FastAPI controllers (registered under /api/v1)
│   │   ├── videos.py            # /api/v1/videos
│   │   ├── renders.py           # /api/v1/renders
│   │   └── youtube.py           # /api/v1/youtube
│   ├── rendering/               # FFmpeg rendering engine
│   │   ├── engine.py            # RenderEngine: orchestration, progress tracking, manifest output
│   │   ├── config.py            # RenderConfig, quality presets, padding presets, clipping modes
│   │   ├── filters.py           # FFmpeg video filter graphs (blur padding, crop layouts)
│   │   ├── audio.py             # FFmpeg audio filter graphs (ducking, sidechain, limiting)
│   │   ├── probe.py             # Media probing via ffprobe
│   │   ├── validator.py         # Render parameter validation
│   │   ├── manifest.py          # manifest.json builder and writer
│   │   └── cli.py               # Standalone CLI entry point for rendering clips
│   └── worker/                  # Background execution & Celery
│       ├── celery_app.py        # Celery app instance
│       ├── tasks.py             # Celery task definitions (downloads, renders, uploads)
│       └── helpers.py           # Celery broker health check (is_celery_broker_online)
├── ui/                          # Next.js frontend application
│   ├── src/app/                 # App Router pages (videos, studio, renders, youtube, channel)
│   ├── src/components/          # Modals, Video cards, Render rows, Pagination
│   ├── src/lib/api.ts           # Centralized API client unwrapping BaseResponse
│   └── src/types/video.ts       # TypeScript models matching backend schemas
├── alembic/                     # Database schema migrations
├── data/                        # Local runtime storage (gitignored: downloads, renders, sqlite db)
├── tests/                       # Pytest test suite (test_api.py, test_renderer.py, test_youtube_upload.py)
├── pyproject.toml               # Python project configuration & dependencies
├── Dockerfile                   # Backend Docker build
└── docker-compose.yml           # Full-stack Docker orchestration (backend, worker, redis, frontend)
```

---

## 4. Development Commands & Workflows

Always use `uv` for Python package management and virtual environment execution.

### Backend

```bash
# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "describe_migration"

# Start FastAPI development server
uv run uvicorn app.main:app --reload --port 8000

# (Optional) Start Celery worker
uv run celery -A app.worker.celery_app worker --loglevel=info
```

### Frontend (`ui/`)

```bash
cd ui

# Install dependencies
npm install

# Run Next.js development server
npm run dev

# Build production bundle
npm run build

# Run linter
npm run lint
```

### Testing & Code Quality

```bash
# Run all tests
uv run pytest

# Run a specific test file
uv run pytest tests/test_api.py -v

# Run lint checks
uv run ruff check

# Apply automatic lint fixes
uv run ruff check --fix

# Format code
uv run ruff format
```

---

## 5. Architectural Conventions & Guidelines

### 1. Service-Oriented Architecture
- **Routers must remain thin:** Do not embed database queries, FFmpeg calls, or complex logic inside router functions.
- Delegate all business logic to dedicated classes in `app/services/` (`VideoService`, `RenderService`, `YouTubeUploaderService`, `YtdlpService`).
- Exception handling in routers should catch domain exceptions and convert them into standard HTTP status codes.

### 2. Standardized Response Envelope (`BaseResponse[T]`)
Every HTTP endpoint (except direct file streams or redirects) must return `BaseResponse[T]`:
```python
from app.core.responses import BaseResponse


@router.get("/example", response_model=BaseResponse[ExampleResponse])
def get_example():
    data = ExampleService.get_data()
    return BaseResponse.success_response(response=data)
```
- On exceptions, raise `APIException(status_code=..., detail=..., error_code=...)` or let global exception handlers format standard JSON error envelopes.
- Frontend's `ui/src/lib/api.ts` automatically unwraps `response.response`.

### 3. Background Task Dispatching & Celery Fallback
To ensure BackseatCaster works both in Docker/production with Redis and in lightweight local development without Redis, always use this pattern:
```python
from app.worker.helpers import is_celery_broker_online

if is_celery_broker_online():
    task = my_celery_task.delay(*args)
    # track task.id
else:
    background_tasks.add_task(my_sync_or_async_task, *args)
```
- In background tasks running outside a request context, obtain a database session via `get_task_db_session()` (which handles FastAPI test overrides automatically).
- Always close sessions in `finally` blocks within background jobs.

### 4. FFmpeg Video & Audio Rendering
- Output formats generated per clip:
  - `landscape.mp4` (1920x1080)
  - `vertical_blur.mp4` (1080x1920 with background blur padding)
  - `vertical_crop.mp4` (1080x1920 configurable crop preset: `third_person`, `cinematic`, `direct_crop`)
  - `manifest.json` (metadata, probe information, timing, and output paths)
- Hardware Acceleration: The rendering engine automatically selects `h264_videotoolbox` on macOS when available, falling back to `libx264` on Linux/Docker. Do not hardcode encoder flags without inspecting `detect_available_encoders()`.
- Audio Ducking: When a narration voiceover WAV is provided, sidechain ducking must lower gameplay audio volume by configured dB during speech, with smooth attack and release curves.

### 5. Database & Concurrency
- SQLite is the active database. Always include `connect_args={"check_same_thread": False}`.
- All stored datetime objects must be timezone-aware (use `datetime.now(UTC)` / `timezone.utc`).
- When modifying database models, always create a corresponding Alembic migration.

### 6. Testing Patterns
- Use in-memory SQLite (`sqlite:///:memory:`) configured with `StaticPool` for all API and unit tests.
- When testing media rendering or video probing, use synthetic FFmpeg commands (`lavfi` with `testsrc` / `testsrc2` and `sine`) to generate tiny, deterministic test assets rather than downloading external files.
- Test client dependencies must override `get_db` using `app.dependency_overrides`.

---

## 6. Storage & Path Conventions

- All persistent files must reside in the `./data` directory (or configured via environment variables):
  - SQLite database: `./data/backseatcaster.db`
  - VOD downloads: `./data/downloads/`
  - Rendered clips: `./data/renders/<clip_id>/`
  - YouTube OAuth credentials: `./data/client_secrets.json` & `./data/youtube_token.json`
- Always use `Path` objects from `pathlib` for file system operations.
- Ensure directories are created using `.mkdir(parents=True, exist_ok=True)`.
