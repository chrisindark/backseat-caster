# ADR 0003 — Celery + Redis with Automatic BackgroundTasks Fallback

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

Downloads, renders, mining runs, and uploads take minutes; they cannot run inside HTTP requests. A full Celery+Redis deployment is great for Docker but demands too much setup from a hobbyist running the project on a laptop for the first time — and the "local-first" principle says the default install should just work.

## Decision

All heavy work dispatches through a single check:

```python
if is_celery_broker_online():
    task = my_celery_task.delay(*args)
else:
    background_tasks.add_task(execute_x, *args)
```

- Brokers are probed cheaply (`is_celery_broker_online`, `app/worker/helpers.py`) — probe failure means "offline", never a broken request.
- Both paths invoke the same `execute_*` service functions; Celery tasks in services are thin wrappers (see `app/worker/tasks.py` re-export note).
- Background DB access uses `get_task_db_session()` (test-override aware) with `finally` cleanup.

## Consequences

- Positive: zero configuration per deployment tier; identical business logic; status polling works regardless of executor; local dev stays lightweight.
- Negative: no persistence/observability of queued work in fallback mode — job state lives in the DB (`pending → processing → completed/failed`), which is the single source of truth for both paths; long-running fallback tasks tie up worker process capacity of the web server.

## References

- [docs/background-tasks.md](../background-tasks.md)
- [docs/caching.md](../caching.md)
- [docs/deployment.md](../deployment.md)
