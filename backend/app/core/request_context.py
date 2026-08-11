"""Request context binding for structured logging.

Binds request_id, org_id, and user_id to structlog's context vars so that
ALL log entries emitted during request processing automatically include them.

This middleware runs after AuthMiddleware (which sets request.state.request_id
and request.state.jwt_payload), so auth context is available.

Requirements: R45.1, R45.2
"""

from __future__ import annotations

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that binds request-scoped context to structlog context vars.

    After this middleware runs, all structlog loggers automatically include:
        - request_id: UUID v4 (from AuthMiddleware)
        - org_id: resolved org UUID (if authenticated)
        - user_id: JWT sub claim (if authenticated)
        - method: HTTP method
        - path: request path

    This eliminates the need to pass request_id/org_id to every logger call.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Bind context vars before request processing, clear after."""
        # Clear any stale context from a previous request (connection reuse)
        structlog.contextvars.clear_contextvars()

        # Bind request-level context
        request_id = getattr(request.state, "request_id", "")
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # Bind auth context if available (set by AuthMiddleware)
        jwt_payload = getattr(request.state, "jwt_payload", None)
        if jwt_payload:
            structlog.contextvars.bind_contextvars(
                user_id=jwt_payload.sub,
            )
            # org_id may be in app_metadata
            raw = getattr(jwt_payload, "raw", {}) or {}
            app_metadata = raw.get("app_metadata", {})
            org_id = app_metadata.get("org_id", "")
            if org_id:
                structlog.contextvars.bind_contextvars(org_id=str(org_id))

        response = await call_next(request)
        return response
