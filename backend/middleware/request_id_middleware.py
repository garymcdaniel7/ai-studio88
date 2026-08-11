"""Request ID middleware for X-Request-ID header propagation.

Generates a UUID v4 for every request and adds it to:
    - request.state.request_id (for downstream access)
    - X-Request-ID response header (for client correlation)
    - structlog context vars (for structured logging)

If the client provides a valid X-Request-ID header, it is reused for
distributed tracing. Otherwise, a new UUID is generated.

Requirements: R16.4, R45.1, R45.2
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that adds X-Request-ID (UUID v4) to every response.

    Behavior:
        1. Accept incoming X-Request-ID if present and valid UUID
        2. Generate a new UUID v4 if not provided or invalid
        3. Store in request.state.request_id for downstream access
        4. Bind to structlog context vars so all logs include it
        5. Add to response X-Request-ID header

    Requirements: R16.4, R45.1, R45.2
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Add request ID to request state, structlog context, and response."""
        # Try client-provided header first (distributed tracing)
        request_id = request.headers.get("x-request-id")

        # Validate if provided; generate if missing or invalid
        if request_id:
            try:
                uuid.UUID(request_id)
            except (ValueError, AttributeError):
                request_id = str(uuid.uuid4())
        else:
            request_id = str(uuid.uuid4())

        # Store in request state for downstream access
        request.state.request_id = request_id

        # Bind to structlog context vars so ALL logs include request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Clear context vars after request completes (prevent leakage)
        structlog.contextvars.clear_contextvars()

        return response
