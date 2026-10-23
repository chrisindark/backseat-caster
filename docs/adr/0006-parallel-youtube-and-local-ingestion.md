# ADR 0006 — Parallel YouTube and Local (OBS) Ingestion

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

The first ingestion path — `yt-dlp` scraping and downloading from a YouTube channel — covered a "content sourced from elsewhere" workflow but ignored the primary user workflow: recording gameplay locally with OBS and immediately working on it. Retroactively force-fitting local files into the YouTube sync flow (simulate a channel) would be fragile and depend on network connectivity.

## Decision

Support **two sibling ingestion paths** that converge on one catalog model:

1. **YouTube:** `POST /videos/sync` (metadata) → `POST /videos/{id}/download` (`yt-dlp`, background).
2. **Local:** `POST /videos/upload` (multipart direct upload, probe + thumbnail generation, `201`).

Both produce the same `Video` record with local file paths; downstream stages (studio, mining, rendering, publishing) never branch on origin.

## Consequences

- Positive: offline-first usage works end to end without yt-dlp/YouTube; the UI gets one dropzone-based path; tests cover both paths offline (synthetic media).
- Negative: two sets of failure modes to document ([docs/ingestion.md](../ingestion.md)); upload size limits are governed by the HTTP layer/proxy rather than yt-dlp, so deployment tuning must consider multipart limits.

## References

- [docs/ingestion.md](../ingestion.md)
- [ADR 0003 — background dispatch](adr-0003-celery-with-backgroundtasks-fallback.md) (download & upload jobs)
