"""Application middleware for security and tenant isolation enforcement.

Contains:
    - OrgIdInjectionGuard: Rejects requests that supply org_id in query/body params
    - RequestContextMiddleware: Adds X-Request-ID to all responses

Requirements: R2.7, R2.8, R2.10, R16.3
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

try:
    from app.core.auth_policy import PUBLIC_PROBE_ALLOWLIST, get_auth_policy
    from app.core.config import get_settings
    from app.core.logging import get_logger
except ModuleNotFoundError:  # Runtime import when launched as backend.main.
    from backend.app.core.auth_policy import PUBLIC_PROBE_ALLOWLIST, get_auth_policy
    from backend.app.core.config import get_settings
    from backend.app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = ["AuthMiddleware", "OrgIdInjectionGuard", "PUBLIC_PROBE_ALLOWLIST", "RequestIdMiddleware"]

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
        # CORS handles valid preflight requests before this middleware. Keep
        # OPTIONS exempt here as well for direct ASGI/test invocations.
        policy = get_auth_policy(get_settings())
        if policy.is_public(request.url.path, request.method):
            return await call_next(request)

        # Check query parameters using exact key matching. Repeated values are
        # rejected because ``keys()`` still contains the forbidden key.
        path = request.url.path
        query_params = set(request.query_params.keys())
        forbidden_found = query_params & _FORBIDDEN_CLIENT_PARAMS

        request.state.security_events = [*getattr(request.state, "security_events", []), "org"]
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


class AuthMiddleware(BaseHTTPMiddleware):
    """Validate bearer JWTs and attach a trusted payload to request state.

    The middleware uses the same authoritative policy as route dependencies.
    It is defense in depth: route dependencies still enforce identity and
    membership before tenant-owned handlers run.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Authenticate protected requests and add a request ID to responses."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response
        try:
            settings = get_settings()
            policy = get_auth_policy(settings)
            request.state.security_events = ["auth"]
            if policy.is_public(request.url.path, request.method):
                policy.telemetry(
                    outcome="public_or_preflight",
                    path=request.url.path,
                    method=request.method,
                    request_id=request_id,
                )
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                return response

            if policy.allows_dev_fallback:
                payload = _load_dev_payload()
                if payload is not None:
                    request.state.jwt_payload = payload
                    policy.telemetry(
                        outcome="development_fallback",
                        path=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    )
                    response = await call_next(request)
                    response.headers["X-Request-ID"] = request_id
                    return response

            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not auth[7:].strip():
                if policy.observes_only:
                    policy.telemetry(
                        outcome="missing_auth_observed",
                        path=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    )
                    response = await call_next(request)
                    response.headers["X-Request-ID"] = request_id
                    return response
                policy.telemetry(
                    outcome="missing_auth_rejected",
                    path=request.url.path,
                    method=request.method,
                    request_id=request_id,
                )
                return _auth_error("Authentication required", "UNAUTHORIZED", request_id)
            try:
                from app.core.security import (
                    ExpiredTokenError,
                    InvalidTokenError,
                    decode_supabase_jwt,
                )
            except ModuleNotFoundError:
                from backend.app.core.security import (
                    ExpiredTokenError,
                    InvalidTokenError,
                    decode_supabase_jwt,
                )

            try:
                request.state.jwt_payload = decode_supabase_jwt(auth[7:].strip())
            except ExpiredTokenError:
                policy.telemetry(
                    outcome="expired_auth_observed" if policy.observes_only else "expired_auth_rejected",
                    path=request.url.path,
                    method=request.method,
                    request_id=request_id,
                )
                if policy.observes_only:
                    response = await call_next(request)
                    response.headers["X-Request-ID"] = request_id
                    return response
                return _auth_error("Token expired", "TOKEN_EXPIRED", request_id)
            except InvalidTokenError as exc:
                code = "INVALID_TOKEN" if "empty" in str(exc).lower() else "UNAUTHORIZED"
                detail = "Invalid token claims" if code == "INVALID_TOKEN" else "Invalid token"
                policy.telemetry(
                    outcome="invalid_auth_observed" if policy.observes_only else "invalid_auth_rejected",
                    path=request.url.path,
                    method=request.method,
                    request_id=request_id,
                )
                if policy.observes_only:
                    response = await call_next(request)
                    response.headers["X-Request-ID"] = request_id
                    return response
                return _auth_error(detail, code, request_id)

            policy.telemetry(
                outcome="authenticated",
                path=request.url.path,
                method=request.method,
                request_id=request_id,
            )
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception("auth_middleware_failure")
            return _auth_error("Internal server error", "INTERNAL_ERROR", request_id, status=500)


def _auth_error(detail: str, code: str, request_id: str, status: int = 401) -> JSONResponse:
    """Build a structured auth error with request correlation."""
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "code": code},
        headers={"X-Request-ID": request_id},
    )


def _load_dev_payload() -> Any | None:
    """Load the first real org member for local-only auth development mode."""
    try:
        try:
            from app.core.security import JWTPayload
        except ModuleNotFoundError:
            from backend.app.core.security import JWTPayload
        from backend.database import get_supabase_client, is_supabase_configured

        if not is_supabase_configured():
            return None
        result = (
            get_supabase_client()
            .table("org_members")
            .select("user_id,org_id,role")
            .order("created_at")
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        member = result.data[0]
        now = int(__import__("time").time())
        return JWTPayload(
            sub=str(member["user_id"]),
            exp=now + 3600,
            role=member.get("role", "authenticated"),
            raw={"sub": str(member["user_id"]), "exp": now + 3600, "app_metadata": {"org_id": member["org_id"]}},
        )
    except Exception:
        logger.exception("dev_auth_member_lookup_failed")
        return None


def validate_auth_dev_mode_startup() -> None:
    """Validate the complete authoritative authentication policy at startup."""
    settings = get_settings()
    get_auth_policy(settings)
