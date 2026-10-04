"""Authenticated MCP adapters for publishing, calendar, and connections."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.services.connection_service import ConnectionService
from app.services.platform_registry import list_platform_definitions
from app.services.publishing_policy_service import PublishPolicyInput, evaluate_publish_policy
from backend.aios.mcp.phase2_common import (
    MCPExecutionContext,
    MCPToolError,
    idempotent_result,
    parse_uuid,
    reject_org_selectors,
    remember_result,
    require_role,
    safe_record,
)
from backend.app.db.session import get_session_factory
from backend.publishing.service import PublishingService, PublishingServiceError


def _connection_view(connection: Any) -> dict[str, Any]:
    """Return connection metadata without token references or secret fields."""
    data = safe_record(connection)
    for key in ("oauth_token_ref", "access_token", "refresh_token", "api_key"):
        data.pop(key, None)
    return data


async def _with_connection_service(
    context: MCPExecutionContext,
    operation: Callable[[ConnectionService], Awaitable[Any]],
) -> Any:
    """Run a connection service operation in a managed async DB session."""
    try:
        factory = get_session_factory()
        async with factory() as db:
            service = ConnectionService(db=db, org_id=UUID(context.org_id))
            result = await operation(service)
            await db.commit()
            return result
    except MCPToolError:
        raise
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        detail = getattr(exc, "detail", None)
        if status_code:
            code = getattr(exc, "headers", {}).get("X-Error-Code", "CONNECTION_ERROR")
            raise MCPToolError(str(detail or "Connection operation failed"), code, int(status_code)) from exc
        raise MCPToolError("Connection service unavailable", "CONNECTION_SERVICE_UNAVAILABLE", 503) from exc


def _publishing_error(exc: PublishingServiceError) -> MCPToolError:
    """Map a publishing service error to a structured MCP error."""
    status = 404 if exc.code == "PUBLISH_NOT_FOUND" else 422
    if exc.code.endswith("UNAVAILABLE"):
        status = 503
    return MCPToolError(exc.message, exc.code, status)


async def list_platforms(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List truthful platform capabilities and rollout policy metadata."""
    reject_org_selectors(params)
    return {"platforms": list_platform_definitions()}


async def check_platform_policy(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Evaluate platform capability/policy gates without publishing content."""
    reject_org_selectors(params)
    platform = str(params.get("platform", "")).strip().lower()
    if not platform:
        raise MCPToolError("platform is required", "INVALID_INPUT", 422)
    evidence = PublishPolicyInput(
        **{key: params[key] for key in PublishPolicyInput.__dataclass_fields__ if key in params}
    )
    try:
        decision = evaluate_publish_policy(platform, evidence)
    except Exception as exc:
        code = getattr(exc, "code", "PLATFORM_POLICY_DENIED")
        status = 409 if code == "PLATFORM_UNAVAILABLE" else 422
        raise MCPToolError(str(exc), code, status) from exc
    return decision.as_dict()


async def connect_platform(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Start OAuth or create a provider-key connection under the MCP tenant."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    provider = str(params.get("provider_name", params.get("platform", ""))).strip().lower()
    if not provider:
        raise MCPToolError("provider_name is required", "INVALID_INPUT", 422)
    ownership = str(params.get("ownership", "user")).lower()
    if ownership == "workspace" and context.role not in {"owner", "admin"}:
        raise MCPToolError("Workspace connections require admin or owner role", "ROLE_NOT_ALLOWED", 403)
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "connect_platform", key)
    if prior:
        return prior

    async def operation(service: ConnectionService) -> Any:
        if params.get("api_key"):
            return await service.create_api_key_connection(
                provider_name=provider,
                category=str(params.get("category", "social")),
                ownership=ownership,
                display_name=str(params.get("display_name", provider.title())),
                api_key=str(params["api_key"]),
                user_id=UUID(context.user_id),
                allowed_roles=params.get("allowed_roles"),
                tool_policy=params.get("tool_policy"),
            )
        return await service.initiate_oauth(
            provider_name=provider,
            category=str(params.get("category", "social")),
            ownership=ownership,
            display_name=str(params.get("display_name", provider.title())),
            user_id=UUID(context.user_id),
        )

    result = await _with_connection_service(context, operation)
    output = {"status": "connected" if hasattr(result, "lifecycle_state") else "authorization_required"}
    output.update(_connection_view(result) if hasattr(result, "lifecycle_state") else safe_record(result))
    return remember_result(context, "connect_platform", key, output)


async def disconnect_platform(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Revoke a tenant-owned platform connection without exposing credentials."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    connection_id = parse_uuid(params.get("connection_id"), "connection_id")
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "disconnect_platform", key)
    if prior:
        return prior
    result = await _with_connection_service(
        context,
        lambda service: service.revoke_connection(connection_id=UUID(connection_id), actor=UUID(context.user_id)),
    )
    output = {"status": "revoked", "connection": _connection_view(result)}
    return remember_result(context, "disconnect_platform", key, output)


async def list_connected_platforms(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List only connections belonging to the authenticated MCP tenant."""
    reject_org_selectors(params)
    result = await _with_connection_service(
        context,
        lambda service: service.list_connections(limit=100, offset=0),
    )
    items, total = result
    return {"items": [_connection_view(item) for item in items], "total": total}


async def get_connection_status(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Read one tenant-owned connection without probing provider credentials."""
    reject_org_selectors(params)
    connection_id = parse_uuid(params.get("connection_id"), "connection_id")
    result = await _with_connection_service(
        context,
        lambda service: service.get_connection(UUID(connection_id)),
    )
    return {"connection": _connection_view(result)}


async def check_connection_health(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Check a tenant-owned connection and expose only lifecycle health."""
    reject_org_selectors(params)
    connection_id = parse_uuid(params.get("connection_id"), "connection_id")
    result = await _with_connection_service(
        context,
        lambda service: service.health_check(UUID(connection_id)),
    )
    return {"connection": _connection_view(result)}


async def reauthorize_connection(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Start a state-bound reauthorization flow for a tenant-owned connection."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    connection_id = parse_uuid(params.get("connection_id"), "connection_id")
    result = await _with_connection_service(
        context,
        lambda service: service.reauthorize(UUID(connection_id), UUID(context.user_id)),
    )
    return {"status": "authorization_required", "connection_id": connection_id, "redirect_url": result["redirect_url"], "state": result["state"]}


async def revoke_connection(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Revoke encrypted connection credentials and retain tenant audit state."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    connection_id = parse_uuid(params.get("connection_id"), "connection_id")
    result = await _with_connection_service(
        context,
        lambda service: service.revoke_connection(UUID(connection_id), UUID(context.user_id)),
    )
    return {"status": "revoked", "connection": _connection_view(result)}


async def schedule_post(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Schedule a policy-approved post with org-scoped persistence and idempotency."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "schedule_post", key)
    if prior:
        return prior
    platform = str(params.get("platform", "")).strip().lower()
    evidence = PublishPolicyInput(
        **{name: params[name] for name in PublishPolicyInput.__dataclass_fields__ if name in params}
    )
    try:
        evaluate_publish_policy(platform, evidence)
        result = PublishingService(context.org_id).create_or_schedule(
            platform=platform,
            content=str(params.get("content", params.get("caption", ""))),
            scheduled_for=str(params.get("scheduled_for", "")),
            asset_id=str(params["asset_id"]) if params.get("asset_id") else None,
            post_id=str(params["post_id"]) if params.get("post_id") else None,
        )
    except PublishingServiceError as exc:
        raise _publishing_error(exc) from exc
    except Exception as exc:
        code = getattr(exc, "code", "PLATFORM_POLICY_DENIED")
        status = 409 if code == "PLATFORM_UNAVAILABLE" else 422
        raise MCPToolError(str(exc), code, status) from exc
    output = {"status": "scheduled", "post": result, "org_id": context.org_id}
    return remember_result(context, "schedule_post", key, output)


async def list_scheduled_posts(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List scheduled posts for the authenticated tenant."""
    reject_org_selectors(params)
    try:
        items = PublishingService(context.org_id).list_scheduled(params.get("status"))
    except PublishingServiceError as exc:
        raise _publishing_error(exc) from exc
    return {"items": items, "total": len(items)}


async def get_publishing_calendar(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Return the tenant-scoped publishing calendar."""
    return await list_scheduled_posts(params, context)


async def cancel_scheduled_post(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Cancel a scheduled post idempotently within the authenticated tenant."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    post_id = parse_uuid(params.get("post_id"), "post_id")
    key = params.get("idempotency_key") or f"post:{post_id}"
    prior = idempotent_result(context, "cancel_scheduled_post", key)
    if prior:
        return prior
    try:
        result = PublishingService(context.org_id).cancel(post_id)
    except PublishingServiceError as exc:
        raise _publishing_error(exc) from exc
    output = {"status": "cancelled", "post": result}
    return remember_result(context, "cancel_scheduled_post", key, output)


async def get_publishing_status(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Read one tenant-owned publishing status without provider credentials."""
    reject_org_selectors(params)
    post_id = parse_uuid(params.get("post_id"), "post_id")
    try:
        return {"post": PublishingService(context.org_id).get_status(post_id)}
    except PublishingServiceError as exc:
        raise _publishing_error(exc) from exc
