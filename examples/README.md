# 🧪 Examples

Working, copy-pasteable usage of the BackseatCaster pipeline. Replace `127.0.0.1:3001` with your host if deployed elsewhere. See [API_REFERENCE.md](../API_REFERENCE.md) for the full surface.

---

## 1. cURL — full pipeline walkthrough

```bash
BASE=http://127.0.0.1:3001/api/v1

# Health (Redis + storage)
curl "$BASE/health"

# Sync a YouTube channel into the catalog
curl -X POST "$BASE/videos/sync" -H "Content-Type: application/json" \
  -d '{"channel_url": "https://www.youtube.com/@yourchannel"}'

# (Browse) paginated catalog with search
curl "$BASE/videos?search=grand+finals&limit=10"

# Queue a VOD download (background job)
curl -X POST "$BASE/videos/<video_id>/download"

# Poll download progress
curl "$BASE/videos/<video_id>/status"

# Render a clip: third_person preset, high quality, 60-105s
curl -X POST "$BASE/renders" -H "Content-Type: application/json" \
  -d '{
    "video_id": "<video_id>",
    "start": 60,
    "end": 105,
    "modes": ["third_person"],
    "quality_preset": "high"
  }'

# Poll render status
curl "$BASE/renders/<clip_id>/status"

# Fetch the manifest written by the engine
curl "$BASE/renders/<clip_id>/manifest"

# Stage the vertical crop for upload
curl -X POST "$BASE/renders/<clip_id>/upload-selection" \
  -H "Content-Type: application/json" -d '{"video_type": "vertical_crop"}'
```

## 2. Local OBS recording upload (multipart)

```bash
curl -X POST "$BASE/videos/upload" \
  -F "file=@./gameplay_2026-10-20.mp4" \
  -F "title=Ranked Session Highlights" \
  -F "channel_name=OBS Studio"
```

## 3. Highlight mining

```bash
# Kick off a mining run on a downloaded/uploaded VOD
curl -X POST "$BASE/videos/<video_id>/highlights/detect" \
  -H "Content-Type: application/json" -d '{}'

# Poll run status, then list ranked candidates
curl "$BASE/videos/<video_id>/highlights/status"
curl "$BASE/videos/<video_id>/highlights"

# Thumbnail for a candidate (for previews)
curl -o candidate.jpg "$BASE/videos/<video_id>/highlights/<candidate_id>/thumb.jpg"
```

## 4. Python — status polling loop

```python
import httpx
import time

BASE = "http://127.0.0.1:3001/api/v1"

def poll(prefix: str, identifier: str, timeout_s: int = 1800):
    """Poll until a pending/processing job resolves."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = httpx.get(f"{BASE}/{prefix}/{identifier}/status").json()
        job = payload["response"]
        status = job.get("status")
        print(f"status={status}")
        if status in {"completed", "failed"}:
            return job
        time.sleep(3)
    raise TimeoutError(f"{prefix}/{identifier} did not settle in {timeout_s}s")

render = poll("renders", "<clip_id>")
print(render)
```

Poll pattern works the same for downloads (`videos/{id}/status`), render jobs, and highlight runs.

## 5. Standalone render CLI (no API)

```bash
uv run python -m app.rendering.cli \
  --input ./data/downloads/example_vod.mp4 \
  --start 90 --end 145 \
  --mode third_person \
  --quality high
```

Outputs `landscape.mp4`, `vertical_blur.mp4`, `vertical_crop.mp4`, `manifest.json` into the configured renders directory. See [docs/rendering.md](../docs/rendering.md).

## 6. OpenAPI client generation

```bash
npx openapi-typescript http://127.0.0.1:3001/openapi.json -o ui/src/types/api.ts
```

Background: [docs/openapi-support.md](../docs/openapi-support.md).

---

Feel free to add runnable examples here when you ship new flows (one shell/Python snippet per flow, keeping the envelope assumptions visible).
