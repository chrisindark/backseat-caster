import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import correlation_id_ctx_var

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract correlation ID from headers or generate one
        correlation_id = request.headers.get("x-correlation-id")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Set the correlation ID in the context variable
        token = correlation_id_ctx_var.set(correlation_id)

        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            end_time = time.perf_counter()
            process_time = end_time - start_time
            client = request.scope.get("client")
            client_ip = f"{client[0]}:{client[1]}" if client else "unknown"
            method = request.scope.get("method", "")
            path = request.scope.get("path", "")
            http_version = request.scope.get("http_version", "1.1")

            logger.info(
                f'{client_ip} - "{method} {path} HTTP/{http_version}" {status_code} '
                f"({process_time:.3f}s)"
            )
            correlation_id_ctx_var.reset(token)
