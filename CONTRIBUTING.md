# 🤝 BackseatCaster — Contributing

Thanks for helping improve BackseatCaster! This document explains how to work in this repo: environment setup, conventions, and review expectations.

---

## 1. Setup

```bash
# Python deps + dev tooling
uv sync
uv run alembic upgrade head

# Frontend deps
cd ui && npm install
```

Install the pre-commit hooks:

```bash
uv run pre-commit install
```

---

## 2. Ground Rules

- **Read [AGENTS.md](AGENTS.md) & [DEVELOPMENT.md](DEVELOPMENT.md) first** — they define the architecture, the service-layer rule, the `BaseResponse[T]` envelope, and the Celery/BackgroundTasks fallback pattern. PRs that violate these won't pass review.
- **Routers stay thin.** Business logic belongs in `app/services/**` (or `app/rendering/**` for media work).
- **Every endpoint** (except file streams) returns `BaseResponse[T]` via `BaseResponse.success_response(...)` or raises `APIException`.
- **Database model changes need an Alembic migration**, generated with `uv run alembic revision --autogenerate -m "..."` in the same PR.
- **No hardcoded encoder flags** in FFmpeg code — respect `RenderConfig` and `detect_available_encoders()`.
- **Storage stays in `./data`** and code uses `pathlib.Path`.

---

## 3. Branching & Commits

- Branch names: `feat/...`, `fix/...`, `docs/...`, `perf/...`, `chore/...`.
- Keep one logical change per PR; split large features into staged PRs (the highlight mining work is the canonical example of staged delivery — see [ROADMAP.md](ROADMAP.md)).
- Write imperative, descriptive commit messages; include reasoning in the body when behavior is non-obvious.

---

## 4. Tests

- Pass `uv run pytest` for every change that touches backend code.
- Patterns to follow (existing files are templates):
  - In-memory SQLite (`sqlite:///:memory:`) with `StaticPool` + `app.dependency_overrides` for `get_db` — see `tests/test_api.py`.
  - Synthetic media via `lavfi` (`testsrc`/`sine`) instead of downloaded fixtures — see `tests/test_renderer.py`.
  - Stubs for Google APIs / network — see `tests/test_youtube_upload.py`.
- Bug fixes should come with a regression test that fails before and passes after the fix.

---

## 5. Lint & Format

```bash
uv run ruff check --fix   # auto-fix what's fixable
uv run ruff format        # format
cd ui && npm run lint     # frontend lint
```

---

## 6. Documentation

- Update docs when you change behavior that the docs describe. File map lives in the [README](README.md#documentation).
- Architectural decisions require an **ADR** in `docs/adr/` (next in sequence, dated, with status and consequences). See the existing ADRs as templates.
- User-visible changes must be recorded in [CHANGELOG.md](CHANGELOG.md) under "Unreleased".

---

## 7. Security-Adjacent Contributions

Anything touching OAuth tokens, yt-dlp inputs, file upload validation, or path handling must be reviewed under [SECURITY.md](SECURITY.md) rules (validate extensions, stay inside configured data roots, never widen scopes casually).

---

## 8. Bug Reports

Include: what you ran (`docker compose` vs local `uvicorn`), app version (from `GET /`), relevant backend log lines with the `X-Correlation-ID`, the video source type (YouTube URL vs local upload), and expected vs actual behavior. Security issues: follow the reporting note in [SECURITY.md](SECURITY.md).
