# ADR 0001 — Service-Oriented Architecture (thin routers)

- **Status:** Accepted (standard from day one)
- **Date:** 2026-10 (repo era of initial Phase 1 buildout)

---

## Context

Early prototypes of video pipelines tend to put ffprobe/FFmpeg calls and SQLAlchemy sessions straight in HTTP handlers. That mixes transport concerns with media logic, makes background execution impossible without refactoring, and turns each new endpoint into its own convention.

## Decision

All business logic lives in service modules under `app/services/` (plus the dedicated `app/rendering/` engine); FastAPI routers in `app/routers/` remain thin — parse request schemas, delegate, wrap the result in `BaseResponse`, and map domain exceptions to status codes.

- Services own: DB queries, yt-dlp invocations, FFmpeg orchestration, Google API calls, Redis cache I/O.
- Routers own: request/response schema wiring, HTTP status mapping, `BackgroundTasks` pass-through.

## Consequences

- Positive: every service is directly unit-testable (offline), background jobs call the same functions as requests, and reviewers can navigate one layer at a time.
- Negative: slightly more boilerplate per feature (a schema + a service + a router).
- Enforcement: review rule — "no DB queries or subprocesses in routers"; see [AGENTS.md](../../AGENTS.md#5-architectural-conventions--guidelines) and [DEVELOPMENT.md](../../DEVELOPMENT.md).

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/response-envelope.md](../response-envelope.md)
- [docs/background-tasks.md](../background-tasks.md)
