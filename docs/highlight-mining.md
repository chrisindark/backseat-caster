# 🏆 Highlight Mining (Candidate Detection)

`app/services/highlight/` runs a staged pipeline over a local VOD to rank likely-highlight windows. It is a **suggestion engine**: candidates are proposals that creators approve in the studio — nothing is auto-rendered or auto-published. Decision record: [ADR 0007](adr/0007-stage-gate-highlight-mining.md).

---

## 1. Pipeline stages

```
[1 Audio Energy Scanner] ─► [2 ROI Extractor] ─► [3 Color & OCR Visual Matcher]
                                                             │
[5 Staging API & Worker] ◄── [4 Clustering & Scoring] ◄── [3.5 Deep Visual Extraction]
```

| Stage | Module | What it does |
|---|---|---|
| 1. Audio excitement & silence scan | `audio_scanner.py` | FFmpeg `ebur128`/RMS pass bucketed in 0.5s slices; rolling top-percentile threshold finds team fights and prunes lobbies/loading screens (fast: ~100x realtime) |
| 2. ROI extraction | `roi_extractor.py` | Samples frames (~1-2 FPS cap) inside candidate windows and crops HUD regions: banners plus, for deep extraction, killfeed, ultimate meter, hero portrait and ability row |
| 3. Visual matcher | `visual_matcher.py` + `detectors/` | Color mask gating + OCR trigger matching per game profile (8x-faster tightened color gating, adaptive sampling, regex sanitization, scoreboard rejection) |
| 3.5 Deep visual extraction | `deep_visuals.py` + `killfeed.py`, `ultimate_meter.py`, `hero_identifier.py` | Structured killfeed rows and player multi-kill chains, ultimate charge/ready/cast tracking with kill payoff correlation, hero portrait and ability cooldown identification |
| 4. Clustering & scoring | `cluster_engine.py` | Groups overlapping windows, pads cinematically to 15–45s, ranks by combined audio+visual+deep score with persistence weighting, and enriches candidate details |
| 5. Service & worker | `service.py` | Persists `HighlightRun` + `HighlightCandidate` rows; dispatches via the Celery/BackgroundTasks rule |

### Deep visual extraction (Phase 3)

`deep_visuals.py` runs over the ROI batch already extracted for Stage 3 and shares one OCR engine across its stages:

- **Killfeed chains** (`killfeed.py`): groups OCR tokens into rows by vertical center, splits actor/victim on the widest column gap, classifies actions (elimination / knock / assist), infers friendly (blue) vs enemy (red) combatants from row pixel colour, deduplicates rows that persist on screen, and attributes rapid kill chains to the player via `player_names` or a consistent friendly actor. Multi-kill chains become first-class highlight events, so a detected three-kill chain can surface a candidate even when the banner OCR missed it.
- **Ultimate tracking** (`ultimate_meter.py`): reads numeric charge (`42%`), falls back to a circular gauge ring-fill estimate, detects `READY` flashes, and registers a cast when charge drops sharply. Casts are then correlated with post-cast eliminations to prove the ultimate converted into a multi-kill.
- **Hero & abilities** (`hero_identifier.py`): zero-normalized cross-correlation template matching (FFT-accelerated, no OpenCV required) for the hero portrait and ability icons. A cooldown → available colourfulness transition registers an ability activation.

Hero/ability identification needs creator-supplied templates because hero art is not distributable:

```
data/hero_templates/<game>/heroes/<hero>.png
data/hero_templates/<game>/abilities/<ability>.png
```

Hero portrait templates are authored at the portrait ROI resolution (120×120 at 1080p); ability icons can be any size smaller than the ability-row ROI. When the folders are missing the identifiers return `None`/`[]` and the pipeline behaves exactly as before.

## 2. Detector profiles

`detectors/registry.py` resolves the game profile:

- `marvel_rivals` — HUD banner OCR, structured killfeed chains, ultimate meter casts, and hero/ability template identification.
- `generic` — audio-energy-only fallback for any game.

`detectors/base.py` defines the interface (ROI definitions, color palettes, OCR trigger regexes). Adding a game = adding a module + registry entry — never wire game quirks into generic stages.

## 3. API surface

Nested under each video: `/api/v1/videos/{video_id}/highlights`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/runs` | Detection run history |
| `POST` | `/detect` | Start a mining job (background dispatch) |
| `GET` | `/status` | Live run status |
| `GET` | `` | Ranked candidate list |
| `DELETE` | `` | Clear candidates/runs for the video |
| `GET` | `/{candidate_id}/thumb.jpg` | Candidate thumbnail |

Run/candidate payloads are documented by `app/schemas/highlight.py`; the UI drawer is `ui/src/components/HighlightCandidatesDrawer.tsx`. Candidate `details` now include `hero_name`, `multi_kill_chain`, `abilities_used`, `killfeed_chain` (rows + attribution) and `ultimate_casts` (cast timing and post-cast kills) when Phase 3 signals are available.

## 4. Artifacts

- `./data/highlights/` (configured via `HIGHLIGHTS_DIR`) holds run payloads and extracted thumbnail frames.
- `./data/hero_templates/` (configured via `HERO_TEMPLATES_DIR`) holds optional hero/ability templates for Phase 3 identification.
- Clustering/scoring math determinism: same VOD + same detector version ⇒ same candidates (helps regression tests).

## 5. Testing

Stage-level suites isolate each module (`test_audio_scanner.py`, `test_roi_extractor.py`, `test_visual_matcher.py`, `test_killfeed.py`, `test_ultimate_meter.py`, `test_hero_identifier.py`, `test_cluster_engine.py`, `test_detectors.py`) and `test_highlight_api.py` covers the endpoints, all with synthetic media (no real gameplay fixtures committed). `test_phase3_integration.py` covers deep-visual orchestration, candidate enrichment and detector wiring.
