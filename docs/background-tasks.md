# 🏗️ Background Tasks & Celery Fallback

Heavy work never runs inside a request handler. Decision record: [ADR 0003](adr/0003-celery-with-backgroundtasks-fallback.md).

---

## 1. The dispatch rule

Every service that offloads work (downloads, renders, highlight detection, uploads, bulk deletes) follows the same pattern:

```python
from app.worker.helpers import is_celery_broker_online

if is_celery_broker_online():
    task = my_celery_task.delay(*args)
    # Optionally record task.id for observability
else:
    background_tasks.add_task(my_sync_or_async_task, *args)
```

`is_celery_broker_online()` performs a cheap broker probe against `CELERY_BROKER_URL`. The result is that:

- **Docker / production:** Celery + Redis takes the work.
- **Lightweight local dev (no Redis):** FastAPI `BackgroundTasks` runs the same service function in-process.

Both paths call the same underlying executor functions (`execute_download_job`, `execute_render_job`, `execute_highlight_detection_job`, `execute_bulk_delete_job`) so logic is duplicated zero times.

## 2. Task registry

[`app/worker/tasks.py`](../app/worker/tasks.py) re-exports the Celery tasks that now live in their service modules (to avoid circular imports):

| Task | Source module |
|---|---|
| `download_video_celery_task` | `app.services.videos` |
| `render_clip_celery_task`, `bulk_delete_renders_celery_task` | `app.services.renders` |
| `detect_highlights_celery_task` | `app.services.highlight.service` |
| `upload_clip_celery_task`, `batch_upload_clips_celery_task` | `app.services.youtube_uploader` |

## 3. Database access in workers

Background code runs outside FastAPI's dependency injection, so it must not use the request-scoped `get_db`. Instead:

```python
from app.database import get_task_db_session

def background_job(...):
    session = get_task_db_session()   # honors dependency_overrides in tests
    try:
        ...  # job state transitions
    finally:
        session.close()
```

Always close sessions in `finally` — worker processes are long-lived.

## 4. Job lifecycle & progress

- Render/highlight jobs persist phase state on their ORM models (`pending → processing → completed/failed`) so `GET /renders/{clip_id}/status` and `GET /videos/{id}/highlights/status` can poll regardless of which worker ran the job.
- Download progress is similarly serviced (percent + ETA) since yt-dlp reports incremental updates.

## 5. Failure modes

| Mode | Behavior |
|---|---|
| Redis briefly offline | New dispatches fall back automatically; in-flight Celery tasks keep their retry semantics |
| Broker check failure (exception) | Treated as offline → `BackgroundTasks` path (never blocks the request) |
| Render task crash | Job model marked `failed` with the error surfaced in the status endpoint / UI |
| Retry | `POST /renders/jobs/{job_id}/retry` re-dispatches through the same rule |

## 6. Guides for new background work

1. Write the service function first (`execute_x(...)`), no Celery imports.
2. Add a thin Celery task wrapper in the service module (see existing `_celery_task` functions).
3. Use the dispatch block above in the router/service.
4. Add tests exercising the synchronous `execute_*` path directly — see `tests/test_renderer.py` and `tests/test_highlight_api.py` for the pattern.
