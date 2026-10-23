# 🛡️ OpenAPI Support

BackseatCaster is a native OpenAPI consumer-producer built on FastAPI. The Swagger UI is live for every build, and the served `/openapi.json` can be used to generate SDK stubs.

---

## 1. Interactive Docs (built-in)

| URL | Purpose |
|---|---|
| `http://127.0.0.1:3001/docs` | Swagger UI (interactive calls) |
| `http://127.0.0.1:3001/redoc` | ReDoc reference view |
| `http://127.0.0.1:3001/openapi.json` | Machine-readable schema |

Metadata is fed from settings (`PROJECT_NAME`, `VERSION`) in `app/main.py`:

```python
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="BackseatCaster backend for YouTube ingestion, video management, and highlight clip rendering",
    lifespan=lifespan,
)
```

## 2. Envelope contracts in the docs

Every entity endpoint declares an accurate response model:

```python
@router.get("", response_model=BaseResponse[VideoListResponse])
def list_videos(...):
    return BaseResponse.success_response(response=...)
```

Because `BaseResponse` is generic, the rendered schema shows the exact payload that will appear under `response` — for example Swagger UI will explain both the outer envelope and the inner `VideoListResponse` structure.

Two exceptions exist by design (documented in [API_REFERENCE.md](../API_REFERENCE.md)):

- File streams (`/videos/{id}/stream`, `/renders/{clip_id}/stream/{type}`, thumbnails) — raw binary.
- `GET /renders/{clip_id}/manifest` — a raw JSON manifest override.

## 3. Ingestion helpers

FastAPI's `UploadFile` / `Form` / `File` support makes multipart ingestion (OBS recordings) appear in the schema automatically with the field names the UI's dropzone uses.

## 4. Client generation

Point any OpenAPI generator at `openapi.json`:

```bash
# Example: generate a TypeScript client for the UI folder
npx openapi-typescript http://127.0.0.1:3001/openapi.json -o ui/src/types/api.ts
```

Keep generated clients out of version control or vendored per template depending on your codegen setup.

## 5. Documented accuracy checklist

Keep the docs exactly correct whenever you touch backend routing:

- Ensure `response_model=BaseResponse[...]` always matches the actual payload returned by the service.
- Add `tags` to routers (currently: `Health`, `Videos`, `Renders`, `youtube`, `Highlights`).
- Document upload flows via explicit `status_code` and `response_class` for multipart.
