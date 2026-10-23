# ADR 0007 — Stage-Gated Highlight Mining (Detector Registry)

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

Finding highlights automatically in hours of gameplay can only succeed if it is decomposed: a monolithic "find the good parts" classifier is unreproducible, hard to unit-test, and hard to tune per game. False positives (scoreboards counted as fights) were the first domain problem in practice, and speed mattered — the pipeline had to scan multi-hour VODs in realistic time.

## Decision

Mining is a fixed, stage-gated pipeline with game behavior isolated behind a detector registry:

```
[1 audio_scanner] ─► [2 roi_extractor] ─► [3 visual_matcher] ─► [4 cluster_engine] ─► [5 service]
```

- **Stage 1** (audio `ebur128`/RMS bucketing) shrinks the search space ~100x using audio energy.
- **Stage 3** does color gating + OCR only on sampled ROI frames (~1–2 FPS), with per-game rules supplied by a **detector** module (`marvel_rivals`, `generic`) resolved by `detectors/registry.py`; generic stages never embed game quirks.
- Each stage is independently testable with deterministic synthetic fixtures; stage outputs feed the next stage as pure data.
- Scoring/clustering produce ranked `HighlightCandidate` rows persisted per `HighlightRun` — suggestions only.

## Consequences

- Positive: adding a game = one module + registry entry; performance work lands in one stage (the 8x Stage 3 tightening came from gating color checks); every candidate's provenance (scores per stage) is auditable; the creator stays in the loop.
- Negative: tuning per game requires detector-specific fixture maintenance (the chosen cost vs. cross-game false positives in a generic matcher); candidate recomputation requires a new run rather than incremental patching.

## References

- [docs/highlight-mining.md](../highlight-mining.md)
- [ROADMAP.md](../../ROADMAP.md) (Phases 3–5 build AI layers on top of these proposals)
