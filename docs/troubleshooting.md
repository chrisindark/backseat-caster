# 🧲 Troubleshooting

Common failure modes and their fixes, grouped by where they bite.

---

## 1. API / Redis

| Symptom | Cause → Fix |
|---|---|
| `uvicorn` starts but every POST hangs | Redis configured but unreachable → ensure `redis-server` is running **or** let the fallback path kick in; the broker probe has a hard timeout and degrades to `BackgroundTasks` |
| Cache misses constantly / no speedup | Redis is down — cache calls never raise; check `GET /api/v1/health` and the ping logs |
| `500` on a fresh install | Missing migrations → `uv run alembic upgrade head`; missing dirs are self-healing at startup |
| Reject after failed `redis` container | `REDIS_TTL` must parse as int (int like `"3600"`); stale `.env` values are a common culprit |

## 2. Ingestion

| Symptom | Cause → Fix |
|---|---|
| `POST /videos/upload` returns 400 | Non-media extension — verify `.mp4`/`.mkv`/`.mov`/`.webm` etc. |
| Sync finds nothing | Missing/wrong channel handle — check `DEFAULT_YOUTUBE_CHANNEL` and the request body; yt-dlp may also rate-limit: retry later |
| Download stays pending forever | yt-dlp subprocess died — check worker logs with the correlation ID; ensure ffmpeg present in the worker image |
| Thumbnail 404s | Extraction failed — confirm the local file exists and ffprobe succeeds on it |

## 3. Rendering

| Symptom | Cause → Fix |
|---|---|
| Render job fails instantly | Invalid params — `validation_error` from `app/rendering/validator.py` (padding out of range, zero duration) |
| Output looks blurry at tiny sizes | Expected — boxblur padding scales; use `direct_crop` for pixel-true center crop |
| Wrong encoder used | `RenderConfig.preferred_encoder` or the resolved encoder from `detect_available_encoders()`; check the manifest for the resolved encoder value |
| Lost frames / audio drift after ducking | Voiceover WAV sample rate mismatch — check the audio section of `manifest.json` |

## 4. Highlight mining

| Symptom | Cause → Fix |
|---|---|
| No candidates at all | Audio threshold too strict — check run payload stats; if a game profile relies on HUD OCR that isn't matching, look at extracted ROI thumbnails under `./data/highlights/` |
| Low-score junk candidates | Tuning risk — `marvel_rivals` detector thresholds need tightening for that capture (detector version bump recommended) |
| Slow to finish | Stage 1 runs ~100x realtime; Stage 2–3 are the slow part (1-2 FPS sampling); watch the run status endpoint for stage timing |
| `test_detectors` mismatch | Detector signature changes — update to `detectors/base.py` conventions |

## 5. YouTube

| Symptom | Fix |
|---|---|
| `401` on any upload endpoint | Link the account: `GET /api/v1/youtube/auth/status` then `/auth/url` consent flow |
| `redirect_uri_mismatch` | `YOUTUBE_REDIRECT_URI` must match exactly what Google Cloud console lists |
| Refresh loop errors | `POST /auth/revoke`, then re-consent |
| Batch upload stalls | `?sync=false` (default) means results arrive in the queue later — poll `GET /upload/queue` rather than waiting on the POST |

## 6. Docker

| Symptom | Fix |
|---|---|
| Frontend can't reach backend | `NEXT_PUBLIC_API_URL` inside the frontend container must point at the backend service name (`http://backend:3001`), not localhost |
| Stale `libx264` errors on Linux/ARM hosts | `libx264` fallback is what Docker/Linux uses; verify with `ffmpeg -encoders | grep 264` |
| Stale DB after deleting compose | `./data` is a bind mount — recreate the volume only deliberately |

## 7. Diagnostics tools

- `GET /api/v1/health` — app + Redis + storage status
- Every response's `X-Correlation-ID` → find the one log line chain (backend + worker)
- `manifest.json` for any completed render — resolved encoder, filters, timings
- `uv run pytest` for isolating a broken area against synthetic assets
