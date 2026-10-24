# ADR 0002 — Unified `BaseResponse[T]` Envelope

- **Status:** Accepted
- **Date:** 2026-10

---

## Context

FastAPI's default error shape (`{"detail": ...}`) differs from success payloads, which forces every frontend consumer — and every external script — to special-case failures. As endpoints multiplied (videos, renders, highlights, YouTube), ad-hoc response shapes became the largest source of UI bugs.

## Decision

Every HTTP response is a `BaseResponse[T]` envelope:

```json
{ "success": true, "response": { ... }, "error": null }
```

- Implemented generically in `app/core/responses.py` and declared per-route via `response_model=BaseResponse[...]`.
- Success built with `BaseResponse.success_response(...)`.
- Errors raised as `APIException(status_code=..., detail=..., error_code=...)` or produced by global exception handlers so even unexpected 500s match the envelope.
- Exempt: file streams (video, thumbnails, manifest raw JSON) and the OAuth browser redirect.

## Consequences

- Positive: one contract everywhere; the frontend unwraps exactly once (`ui/src/lib/api.ts`); OpenAPI documents the real payload per endpoint; correlation IDs ride along in error envelopes.
- Negative: slightly larger payloads (two fixed fields) and a rule to remember when adding routes — enforced by tests asserting envelope shape (`tests/test_api.py`, `tests/test_highlight_api.py`).

## References

- [API_REFERENCE.md](../../API_REFERENCE.md)
- [docs/response-envelope.md](../response-envelope.md)
- [docs/openapi-support.md](../openapi-support.md)
