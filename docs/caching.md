# ⚡ Redis & Caching

Redis plays three roles in BackseatCaster: Celery broker, result backend, and a small runtime KV cache — with the invariant that **every Redis outage degrades gracefully**.

---

## 1. Where Redis is required (optional for local dev)

- `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` — task queue when the broker is online ([background-tasks.md](background-tasks.md)).
- `REDIS_URL` — runtime cache client.

Both point to `redis://localhost:6379/0` by default (see [CONFIGURATION.md](../CONFIGURATION.md)).

## 2. The cache client

[`app/services/redis.py`](../app/services/redis.py) (`RedisService`) is a thin, **never-raises** wrapper over `redis.asyncio`:

| Method | Notes |
|---|---|
| `ping()` | Health check with a hard 2s timeout (`REDIS_PING_TIMEOUT_SECONDS`) so a black-holed host can't stall startup or requests |
| `get(key)` | Exact-match cache hit; logs hits; returns `None` on any failure |
| `set(key, value, ttl?)` | TTL defaults to `settings.REDIS_TTL` (3600s) |
| `delete(key)` / `expire(key, seconds)` | Maintenance helpers |
| `incr` / `incrby` / `decr` / `decrby` | Counter primitives (available for future rate accounting) |
| `close()` | Idempotent pool shutdown via `aclose()` fallback |

The connection is initialized in the app `DependencyContainer` lifespan and closed on shutdown; every call is timed with the `log_latency` decorator.

## 3. Degradation guarantees

All cache methods catch exceptions internally and return `None` rather than raising — a Redis outage only costs caching, never correctness. Callers (e.g. sync/lookup service paths) must treat a `None` as "cache miss" and do the work the slow way. This complements the Celery→BackgroundTasks fallback: the same "Redis exists but might not" philosophy applies everywhere.

## 4. Usage rules

- Only store JSON-serializable strings (values are strings back and forth; keys are namespaced per feature).
- TTLs come from `REDIS_TTL` unless a feature dictates otherwise — no immortal keys.
- Don't use the cache for data that can't be reconstructed from `./data` plus DB state.

## 5. Health surface

`GET /api/v1/health` reflects Redis connectivity (via the ping probe with its 2s cap) alongside storage status — useful to confirm that the Docker `redis` service and the backend can see each other.
