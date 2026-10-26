# 🧪 Testing

Tests live in `tests/` and run with pytest. They are pure-local: no network downloads, no real uploads, no committed media fixtures.

```bash
uv run pytest                     # everything
uv run pytest tests/test_api.py -v  # one file, verbose
```

---

## 1. Test matrix

| File | Scope |
|---|---|
| `test_api.py` | Video catalog CRUD, channel sync, download dispatch, OBS upload, thumbnails/status |
| `test_renderer.py` | Render engine end-to-end on synthetic assets (all crop presets + quality tiers), manifest output |
| `test_youtube_upload.py` | OAuth status/flows and resumable upload service against stubbed Google clients |
| `test_phase8.py` | Auto-stage, LLM metadata, quota accounting, native `publishAt` scheduling |
| `test_auto_pipeline.py` | Uploaded-render cleanup, VOD-safety guard, batched stage sweep, maintenance endpoints |
| `test_highlight_api.py` | Highlight endpoints + detect dispatch |
| `test_killfeed.py`, `test_ultimate_meter.py`, `test_hero_identifier.py` | Deep visual extraction stages |
| `test_phase3_integration.py` | End-to-end Phase 3 visual orchestration |
| `test_audio_scanner.py` | Stage 1: ebur128/RMS bucketing, threshold logic |
| `test_roi_extractor.py` | Stage 2: HUD ROI sampling/cropping |
| `test_visual_matcher.py` | Stage 3: color gating + OCR matching incl. sanitizer |
| `test_detectors.py` | Detector registry + `marvel_rivals`/`generic` profiles |
| `test_cluster_engine.py` | Stage 4: window overlap clustering, padding, scoring |
| `test_logging_and_correlation.py` | Correlation-ID middleware + colored logger wiring |

## 2. Core patterns (follow these in every new test)

### In-memory SQLite with StaticPool

```python
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
```

Apply migrations/base metadata, then override the dependency:

```python
from app.main import app
from app.database import get_db

app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
```

`get_task_db_session()` respects these overrides too, so background executor functions stay testable.

### Synthetic media instead of downloads

Media fixtures are generated with FFmpeg `lavfi` at test time — deterministic and tiny (never a real gameplay VOD):

```bash
ffmpeg -f lavfi -i testsrc2=size=640x360:rate=30 -f lavfi -i sine=frequency=440:duration=5 -t 5 sample.mp4
```

This is the ground truth behind `tests/test_renderer.py` and the mining-stage tests. Never add an external media download to the suite.

### Stubbed third-party surfaces

Google API (`googleapiclient`/`google-auth`) calls in the YouTube uploader are monkeypatched/mocked — assertions cover request construction and state transitions, not live network behavior.

## 3. What to test for new features

- **Endpoint:** status code + envelope shape (`success`, payload under `response`) + error envelope for failure path ([response-envelope.md](response-envelope.md)).
- **Service:** business outcome, DB state transitions, and the Celery vs BackgroundTasks dispatch decision (call the `execute_*` function directly to stay offline).
- **Rendering/audio:** assert output files exist, probe-able dimensions/encoders match `RenderConfig`, and `manifest.json` parses.
- **Migration:** any model change ships with an Alembic migration and a quick upgrade/downgrade sanity check.

## 4. Frontend tests

The UI currently relies on `npm run lint` and TypeScript checks (`npm run build`) rather than a unit test suite; add component tests only if you wire up a test runner deliberately.
