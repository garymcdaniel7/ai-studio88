"""Global exception handlers for FastAPI.

Ensures ALL errors follow the standard format:
    {"detail": "...", "code": "SNAKE_CASE_ERROR_CODE", "request_id": "..."}

Rules:
    - Never return stack traces to the client
    - Log full exceptions internally with request context
    - Include X-Request-ID in every error response header AND body
    - Validation errors return structured detail list with field info
    - Unhandled exceptions → 500 INTERNAL_ERROR (generic, no leak)

Structured Error Response Format:
    {
        "detail": "Human-readable message",
        "code": "SNAKE_CASE_ERROR_CODE",
        "request_id": "uuid-v4-string"
    }

Validation Error Response Format:
    {
        "detail": "Validation failed",
        "code": "VALIDATION_ERROR",
        "request_id": "uuid-v4-string",
        "errors": [{"field": "name", "message": "...", "type": "..."}]
    }

Requirements: R16.1, R16.2, R16.3, R16.4
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

import structlog

logger = structlog.get_logger(__name__)


def _get_request_id(request: Request) -> str:
    """Extract request_id from request state, or empty string."""
    return getattr(request.state, "request_id", "")


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors (422).

    Returns structured response with field-level error info.
    Never exposes internal model structure beyond field names.

    Response format:
        {"detail": "Validation failed", "code": "VALIDATION_ERROR",
         "request_id": "...", "errors": [{field, message, type}]}
    """
    request_id = _get_request_id(request)

    # Build a user-friendly error list from pydantic errors
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        # Skip the 'body' prefix that FastAPI adds
        field_path = ".".join(str(part) for part in loc if part != "body")
        errors.append({
            "field": field_path or "unknown",
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        })

    logger.info(
        "validation_error",
        path=request.url.path,
        method=request.method,
        error_count=len(errors),
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "code": "VALIDATION_ERROR",
            "request_id": request_id or None,
            "errors": errors,
        },
        headers={"X-Request-ID": request_id},
    )


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Handle explicit HTTP exceptions (4xx/5xx raised by route handlers).

    Preserves the detail message and maps to a SNAKE_CASE error code.
    Never includes internal paths or stack traces.

    Response format:
        {"detail": "...", "code": "SNAKE_CASE", "request_id": "..."}
    """
    request_id = _get_request_id(request)

    # If the exception already has a code header (set by our middleware/deps), use it
    code = ""
    if hasattr(exc, "headers") and exc.headers:
        code = exc.headers.get("X-Error-Code", "")

    # Derive code from status if not explicitly set
    if not code:
        code = _status_to_code(exc.status_code)

    detail = exc.detail if exc.detail else "An error occurred"

    # Log 5xx errors at error level, 4xx at info
    if exc.status_code >= 500:
        logger.error(
            "http_exception",
            status_code=exc.status_code,
            code=code,
            path=request.url.path,
            method=request.method,
        )
    else:
        logger.info(
            "http_exception",
            status_code=exc.status_code,
            code=code,
            path=request.url.path,
            method=request.method,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": detail,
            "code": code,
            "request_id": request_id or None,
        },
        headers={"X-Request-ID": request_id},
    )


async def handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle all unhandled exceptions (500 Internal Server Error).

    Logs the full stack trace internally but NEVER sends it to the client.
    Returns a generic error message with the correlation request_id.

    Response format:
        {"detail": "Internal server error", "code": "INTERNAL_ERROR",
         "request_id": "..."}
    """
    request_id = _get_request_id(request)

    # Log full exception with traceback for debugging
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=request.url.path,
        method=request.method,
        traceback=traceback.format_exc(),
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "code": "INTERNAL_ERROR",
            "request_id": request_id or None,
        },
        headers={"X-Request-ID": request_id},
    )


def _status_to_code(status_code: int) -> str:
    """Map HTTP status codes to standard SNAKE_CASE error codes."""
    status_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    return status_map.get(status_code, "UNKNOWN_ERROR")


def register_error_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application.

    Call this during application setup, after creating the FastAPI instance.
    """
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unhandled_exception)
