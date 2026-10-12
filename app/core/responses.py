"""Standardized API response models and exception handling."""

from __future__ import annotations

import logging
from typing import Generic, TypeVar

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

DataT = TypeVar("DataT")


def default_error_code_for_status(status_code: int) -> str:
    """Map common HTTP status codes to standardized error code strings."""
    status_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        408: "REQUEST_TIMEOUT",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    return status_code_map.get(status_code, f"HTTP_{status_code}")


class BaseResponse(BaseModel, Generic[DataT]):
    """
    Unified base response schema for all HTTP endpoints.

    Contains:
    - success: bool indicating request success
    - status_code: HTTP status code
    - response: payload data on success, or None on failure
    - error_message: error description on failure, or None on success
    - error_code: standardized string error code on failure, or None on success
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)

    success: bool = Field(
        ..., description="Indicates whether the request was successful"
    )
    status_code: int = Field(..., description="HTTP status code")
    response: DataT | None = Field(default=None, description="Response payload data")
    error_message: str | None = Field(
        default=None, description="Error message if request failed"
    )
    error_code: str | None = Field(
        default=None, description="Machine-readable error code if request failed"
    )

    @classmethod
    def success_response(
        cls,
        response: DataT | None = None,
        status_code: int = status.HTTP_200_OK,
    ) -> BaseResponse[DataT]:
        """Generate a standardized success response."""
        return cls(
            success=True,
            status_code=status_code,
            response=response,
            error_message=None,
            error_code=None,
        )

    @classmethod
    def error_response(
        cls,
        error_message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str | None = None,
        response: DataT | None = None,
    ) -> BaseResponse[DataT]:
        """Generate a standardized error response."""
        return cls(
            success=False,
            status_code=status_code,
            response=response,
            error_message=error_message,
            error_code=error_code or default_error_code_for_status(status_code),
        )


class APIException(HTTPException):
    """
    Custom application exception that carries an explicit error code
    alongside status_code and detail message.
    """

    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: str = "An error occurred",
        error_code: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code or default_error_code_for_status(status_code)


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers conforming to BaseResponse."""

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content=BaseResponse.error_response(
                error_message=exc.detail,
                status_code=exc.status_code,
                error_code=exc.error_code,
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        error_code = getattr(exc, "error_code", None) or default_error_code_for_status(
            exc.status_code
        )
        error_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=BaseResponse.error_response(
                error_message=error_msg,
                status_code=exc.status_code,
                error_code=error_code,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        error_messages = "; ".join(
            f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg')}"
            for err in exc.errors()
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=BaseResponse.error_response(
                error_message=f"Validation error: {error_messages}",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_code="VALIDATION_ERROR",
                response={"errors": exc.errors()},
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=BaseResponse.error_response(
                error_message=f"Internal server error: {exc!s}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code="INTERNAL_SERVER_ERROR",
            ).model_dump(),
        )
