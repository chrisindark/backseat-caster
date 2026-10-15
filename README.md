# 🎙️ BackseatCaster (`backseat-caster`)

> AI Gaming Video Editor: Browse gameplay VODs, download highlights via `yt-dlp`, and process them into AI-narrated short-form clips.

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

# Create environment file
cp .env.example .env

# Install dependencies using uv
uv sync

# Run database migrations
uv run alembic upgrade head

# Start FastAPI server
uv run uvicorn app.main:app --reload --port 3001
```

The API docs will be live at [http://127.0.0.1:3001/docs](http://127.0.0.1:3001/docs).

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

You can launch the entire stack (FastAPI backend, Celery worker, Redis, Next.js frontend) with a single command:

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

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Healthcheck and storage status |
| `GET` | `/api/videos` | Paginated video list with search & status filters |
| `POST` | `/api/videos/sync` | Scrape & sync latest videos from YouTube channel |
| `GET` | `/api/videos/{id}` | Video details and local file path |
| `POST` | `/api/videos/{id}/download` | Queue VOD download via `yt-dlp` |
| `GET` | `/api/videos/{id}/status` | Live download percentage & ETA |
| `DELETE` | `/api/videos/{id}/download` | Remove downloaded file from local disk |

---

## 🧪 Testing

```bash
uv run pytest
```
