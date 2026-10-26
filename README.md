# 🎙️ BackseatCaster (`backseat-caster`)

> AI Gaming Video Editor: Browse gameplay VODs, download highlights via `yt-dlp`, process them into AI-narrated short-form clips, and publish them to YouTube Shorts — all locally.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-green.svg)](https://ffmpeg.org/)

---

## 📚 Documentation

| Document | Purpose |
|---|---|
| [docs/getting-started.md](docs/getting-started.md) | Install, configure, and run the full stack |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture and processing pipeline |
| [API_REFERENCE.md](API_REFERENCE.md) | HTTP endpoint reference |
| [CONFIGURATION.md](CONFIGURATION.md) | Environment variables & settings |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Development workflows, testing, linting |
| [ROADMAP.md](ROADMAP.md) | Phases, status, and planned features |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) / [RELEASES.md](RELEASES.md) | Change history and release process |
| [SECURITY.md](SECURITY.md) | Security model and reporting |
| [AGENTS.md](AGENTS.md) | Guide for AI agents & pair programmers |
| [docs/](docs/) | Deep dives: rendering, audio, mining, OAuth, deployment, ADRs |
| [examples/](examples/) | Runnable API, CLI, and Python examples |

---

## 🏗️ Architecture Stack

- **Backend:**
  - **Runtime & Package Manager:** Python 3.11+ managed via [`uv`](https://docs.astral.sh/uv/)
  - **API Framework:** [FastAPI](https://fastapi.tiangolo.com/) with [Uvicorn](https://www.uvicorn.org/)
  - **Data Validation & Settings:** [Pydantic v2](https://docs.pydantic.dev/) + `pydantic-settings`
  - **ORM & Database:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) + SQLite (`data/backseatcaster.db`)
  - **Database Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
  - **Background Worker & Task Queue:** [Celery](https://docs.celeryq.dev/) with resilient FastAPI `BackgroundTasks` fallback
  - **YouTube Ingestion:** [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) for channel metadata extraction and high-quality MP4 downloads
  - **Media Engine:** FFmpeg / ffprobe (rendering, filtering, ducking, loudness normalization)
  - **Publishing:** Google OAuth 2.0 + YouTube Data API v3 resumable uploads
  - **Testing:** `pytest` + `httpx`

- **Frontend (`ui/`):**
  - **Framework:** [Next.js](https://nextjs.org/) (App Router, TypeScript)
  - **Component Library & Theme:** [`@radix-ui/themes`](https://www.radix-ui.com/themes), [`@base-ui/react`](https://base-ui.com/)
  - **Animations:** [`framer-motion`](https://www.framer.com/motion/)
  - **Icons:** [`lucide-react`](https://lucide.dev/)
  - **Aesthetics:** Dark gaming theme with YouTube-style 16:9 video cards, duration badges, and interactive modals.

---

## 🚀 Quick Start

### 1. Backend Setup

```bash
# Clone and enter directory
cd backseat-caster

# Install dependencies using uv
uv sync

# Run database migrations
uv run alembic upgrade head

# Start FastAPI server
uv run uvicorn app.main:app --reload --port 3001
```

The API docs will be live at [http://127.0.0.1:3001/docs](http://127.0.0.1:3001/docs). See [docs/getting-started.md](docs/getting-started.md) for environment variables.

#### (Optional) Celery Worker with Redis

```bash
# Start Redis (if installed)
redis-server

# Run Celery worker
uv run celery -A app.worker.celery_app worker --loglevel=info
```

*Note: If Redis is offline, downloads automatically execute via FastAPI background tasks without interruption.*

---

### 🐳 Full Stack Docker Setup (All Services)

You can launch the entire stack (FastAPI backend, Celery worker, Celery beat scheduler, Redis, Next.js frontend) with a single command:

```bash
# Build and run all services
docker compose up --build
```

- **Next.js UI:** [http://localhost:3000](http://localhost:3000)
- **FastAPI API:** [http://localhost:3001](http://localhost:3001) (Docs at `/docs`)
- **Redis:** `localhost:6379`
- **Data Volume:** Persisted under `./data` (downloads and sqlite database)


---

### 2. Frontend Setup

```bash
# Navigate to ui directory
cd ui

# Install dependencies
npm install

# Run Next.js development server
npm run dev
```

The dashboard will be available at [http://localhost:3000](http://localhost:3000).

---

## 📡 API Overview

Full details in [API_REFERENCE.md](API_REFERENCE.md).

| Group | Prefix | Highlights |
|---|---|---|
| Health | `/api/v1/health` | Healthcheck and storage status |
| Videos | `/api/v1/videos` | Catalog search, channel sync, yt-dlp download, OBS upload, streaming, storage cleanup |
| Renders | `/api/v1/renders` | Clip rendering jobs, formats, manifests, bulk delete, uploaded-render cleanup, maintenance sweep |
| Highlights | `/api/v1/videos/{id}/highlights` | Candidate mining runs, detection, thumbnails |
| YouTube | `/api/v1/youtube` | OAuth 2.0, upload staging queue, resumable Shorts publishing, auto-stage + LLM metadata, native `publishAt` scheduling, quota tracking |

---

## 🧪 Testing

```bash
uv run pytest
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full test workflow.
