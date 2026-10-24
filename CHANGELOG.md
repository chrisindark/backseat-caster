# 📋 Changelog

All notable changes to BackseatCaster are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/). Release process details: [RELEASES.md](RELEASES.md).

---

## [Unreleased]

### Added
- **Autonomous auto-stage & scheduler pipeline (Phase 8):** highlight detection can now auto-render the top N candidates as vertical Shorts (`AUTO_STAGE_*` settings or `auto_render_top_n` per request), generate Gemini-tailored title/description/tags with a deterministic fallback (`app/services/llm_metadata.py`), and assign staggered native YouTube `publishAt` slots (`app/services/auto_stage.py`).
  - New `RenderJob` columns `auto_staged`, `highlight_candidate_id`, `scheduled_publish_at`, plus a `youtube_quota_usage` table and Alembic migration.
  - Quota accounting service (`app/services/youtube_quota.py`) tracks the 10,000 unit/day YouTube budget with midnight-Pacific resets and rejects dispatch with `429` when exhausted.
  - New endpoints: `GET /api/v1/youtube/quota`, `GET /api/v1/youtube/staging`, `POST /api/v1/youtube/staging/{clip_id}/schedule`, `POST /api/v1/youtube/staging/{clip_id}/publish-now`, `POST /api/v1/youtube/auto-stage`; uploads accept an explicit `publish_at`.
  - Renders UI gains an auto-staged banner, quota bar and review drawer with per-clip scheduling and 1-click publish (`ui/src/components/AutoStagePanel.tsx`).
  - New dependencies: `google-genai`.
- **Deep visual event extraction (Phase 3):** structured killfeed row parser with friendly/enemy colour inference and attributed multi-kill chains (`killfeed.py`), ultimate meter OCR with circular gauge fallback, ready-flash detection, cast detection and post-cast kill correlation (`ultimate_meter.py`), plus hero portrait and ability cooldown/activation template matching (`hero_identifier.py`) orchestrated through `deep_visuals.py`.
  - New HUD regions: `hero_portrait`, `ability_row`; new `HERO_TEMPLATES_DIR` (`./data/hero_templates`) for creator-supplied `<game>/heroes` and `<game>/abilities` templates. Identification degrades to a no-op when templates are absent.
  - Candidates now carry `hero_name`, `multi_kill_chain`, `killfeed_chain`, `ultimate_casts` and `abilities_used`, with score boosts for killfeed-corroborated and ultimate-payoff clips.
- Documentation set: root guides (ARCHITECTURE, CONFIGURATION, DEVELOPMENT, API_REFERENCE, SECURITY, ROADMAP, RELEASES, CONTRIBUTING), `docs/` deep dives, `docs/adr/` decision records, and `examples/`.
- MIT license ([LICENSE](LICENSE)).

### Changed
- README restructured to index the new documentation layout.

## [0.1.0] — Initial operational release

### Added
- **Local rendering engine (Phase 1):** 16:9 landscape master, 9:16 vertical outputs (`vertical_blur`, preset crops `third_person` / `cinematic` / `direct_crop`), Lanczos scaling, quality presets (`high`, `compact`, `archive`), automatic `h264_videotoolbox` / `libx264` encoder selection, standalone CLI (`app/rendering/cli.py`), probe & validation suites.
- **Audio pipeline:** sidechain ducking for narration voiceovers, peak limiting, EBU R128 `loudnorm` targeting -14 LUFS.
- **Creator studio UI (Phase 6):** `/studio/[id]` timeline scrubbing, crop guide overlays, comparison player, `/renders` catalog with bulk delete, manifest viewer.
- **Ingestion (Phase 7 + Phase 2):** YouTube channel scraping & VOD download via `yt-dlp` (`/videos/sync`, `/videos/{id}/download`), drag-and-drop OBS upload (`/videos/upload`) with probe & thumbnail generation.
- **Highlight mining (Phase 2 + 2.5):** audio energy scanner, ROI extractor, color/OCR visual matcher with Marvel Rivals detector set, window clustering & scoring API/UI drawer; anti-false-positive hardening with 8x faster Stage 3, adaptive sampling, scoreboard rejection, persistence scoring.
- **Publishing (Phase 7):** Google OAuth 2.0 flow, upload staging queue, resumable YouTube Shorts publishing via YouTube Data API v3.
- **Worker engine (Infra):** Celery + Redis with automatic zero-config fallback to FastAPI `BackgroundTasks`; `is_celery_broker_online` health gating.
- **Platform:** FastAPI + Pydantic v2 routers under `/api/v1`, `BaseResponse[T]` envelope with global exception handlers, correlation-ID middleware + colored logging, SQLAlchemy 2.0 / SQLite / Alembic migrations, Docker Compose full stack (backend, worker, redis, frontend), pytest suite with synthetic media assets.
