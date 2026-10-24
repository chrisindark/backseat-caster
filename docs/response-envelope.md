# 📦 The BaseResponse Envelope

Every BackseatCaster HTTP endpoint (except file streams and redirects) wraps responses in a uniform envelope defined in [`app/core/responses.py`](../app/core/responses.py). Decision record: [ADR 0002](adr/0002-base-response-envelope.md).

---

## 1. Shape

```json
{
  "success": true,
  "response": { "...payload..." },
  "error": null
}
```

Error variant (produced either by `APIException` or the global handlers):

```json
{
  "success": false,
  "response": null,
  "error": {
    "status_code": 404,
    "detail": "Resource not found",
    "error_code": "NOT_FOUND",
    "correlation_id": "8f3a..."
  }
}
```

Field names here are illustrative — the authoritative schema is `BaseResponse` / `APIException` in `app/core/responses.py`. Correlation IDs propagate from [`CorrelationIdMiddleware`](../app/core/middlewares.py), so a failing request can always be matched to a single colored log line.

## 2. Producing responses (routers)

```python
from app.core.responses import BaseResponse

@router.get("/example", response_model=BaseResponse[ExampleResponse])
def get_example():
    return BaseResponse.success_response(response=ExampleService.get_data())
```

Useful variants:

- `BaseResponse.success_response(response=..., status_code=...)` — used for `201 Created` flows like uploads.
- Router code must declare `response_model=BaseResponse[ConcreteSchema]` so OpenAPI stays accurate ([openapi-support.md](openapi-support.md)).

## 3. Producing errors

Raise an `APIException(status_code=..., detail=..., error_code=...)` from anywhere in services to get the standard envelope. Domain-level `HTTPException`s raised by routers are also normalized by the registered global handlers (`register_exception_handlers(app)` in `main.py`), so nothing falls through to FastAPI's default `{"detail": ...}` shape.

## 4. Frontend contract

[`ui/src/lib/api.ts`](../ui/src/lib/api.ts) is the single place the envelope is unwrapped — components call typed helpers and receive the inner `response` payload. Adding a front-end "swallow the envelope" shortcut elsewhere is a review failure because it bypasses unified error handling.

## 5. When not to use it

- File streams (`/videos/{id}/stream`, `/renders/{clip_id}/stream/{video_type}`, `/thumbnail`, candidate `thumb.jpg`) — the caller wants bytes.
- The manual OAuth redirect `GET /youtube/auth/callback` — it must hand the browser back the real redirect.
- `GET /renders/{clip_id}/manifest` — returns the `manifest.json` payload directly for tooling convenience.

## 6. Testing

`tests/test_api.py` and `tests/test_highlight_api.py` assert the envelope shape for success and error paths — when you add an endpoint, add assertions that the envelope (and the error envelope) parse cleanly.
