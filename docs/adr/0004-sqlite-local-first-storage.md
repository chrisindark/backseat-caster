# ADR 0004 — SQLite Local-First Storage

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

BackseatCaster is a single-operator tool: one catalog, modest row counts (hundreds of videos/renders), zero concurrent writers. A network database would add setup friction with no benefit for the local-first philosophy.

## Decision

- **SQLite** at `./data/backseatcaster.db` via SQLAlchemy 2.0, with `connect_args={"check_same_thread": False}`.
- All persistent artifacts live under `./data` (downloads, renders, highlights, OAuth files).
- Schema changes ship as Alembic migrations (`uv run alembic revision --autogenerate`).
- All datetimes stored timezone-aware (`datetime.now(UTC)`).

## Consequences

- Positive: `docker compose up` or `uv run uvicorn` is the entire install; backup is a file copy; tests can run the same models in-memory (`sqlite:///:memory:` + `StaticPool`) with dependency overrides.
- Negative: single-node ceiling — multi-host Celery or heavy parallel writes would require migrating to Postgres (documented in [deployment notes](../deployment.md) as out of scope); long transactions should be kept short around worker writes.

## References

- [CONFIGURATION.md](../../CONFIGURATION.md)
- [docs/testing.md](../testing.md)
