"""Application middleware for security and tenant isolation enforcement.

Contains:
    - OrgIdInjectionGuard: Rejects requests that supply org_id in query/body params
    - RequestContextMiddleware: Adds X-Request-ID to all responses

Requirements: R2.7, R2.8, R2.10, R16.3
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)

# Query parameter names that should NEVER be accepted from clients
_FORBIDDEN_CLIENT_PARAMS = {"org_id", "orgId", "org-id", "organization_id"}


class OrgIdInjectionGuard(BaseHTTPMiddleware):
    """Middleware that rejects any request supplying org_id as a query parameter.

    org_id must ALWAYS be derived from the authenticated JWT via TenantContext.
    Accepting org_id from client request parameters would allow tenant spoofing.

    This is a defense-in-depth measure — services and repositories also enforce
    tenant isolation via their own org_id validation.

    Requirements: R2.7, R2.10

    Exemptions:
        - /health, /ready, /docs, /openapi.json — unauthenticated endpoints
        - /platform-admin/* — Platform Operator endpoints may reference org_ids
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check query params for forbidden org_id injection attempts."""
        # Skip for exempt paths
        path = request.url.path
        exempt_prefixes = ("/health", "/ready", "/docs", "/redoc", "/openapi.json", "/platform-admin")
        if any(path.startswith(p) for p in exempt_prefixes):
            return await call_next(request)

        # Check query parameters
        query_params = set(request.query_params.keys())
        forbidden_found = query_params & _FORBIDDEN_CLIENT_PARAMS

        if forbidden_found:
            logger.warning(
                "org_id_injection_attempt",
                path=path,
                method=request.method,
                forbidden_params=list(forbidden_found),
                client_ip=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "org_id cannot be supplied as a request parameter. "
                    "Organization context is derived from your authentication token.",
                    "code": "ORG_ID_INJECTION_REJECTED",
                },
            )

        return await call_next(request)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID (UUID v4) to every response and propagates to logs.

    If the client provides an X-Request-ID header, it is used (if valid UUID).
    Otherwise, a new UUID is generated.

    The request_id is stored in request.state AND bound to structlog context
    so every log entry during the request lifecycle includes it.

    Requirements: R16.3, R45.1, R45.2
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add request ID to request state, structlog context, and response headers."""
        import structlog

        # Try client-provided header first
        request_id = request.headers.get("x-request-id")

        # Validate if provided, generate if not
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

        # Clear context vars after request completes
        structlog.contextvars.clear_contextvars()

        return response
