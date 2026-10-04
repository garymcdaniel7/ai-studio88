"""Secret-safe MCP tools for provider credentials and configuration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.aios.mcp.phase2_common import (
    MCPExecutionContext,
    MCPToolError,
    idempotent_result,
    reject_org_selectors,
    remember_result,
    require_role,
)
from backend.credentials import CredentialService, ProviderType
from backend.execution.provider_registry import list_providers

_PROVIDER_ALIASES = {
    "thunder": "thunder_compute",
    "thunder_compute": "thunder_compute",
    "runcomfy": "runcomfy",
    "run_comfy": "runcomfy",
    "gemini": "gemini",
    "openai": "openai",
    "anthropic": "anthropic",
    "elevenlabs": "elevenlabs",
    "replicate": "replicate",
    "ollama": "ollama",
    "deepseek": "deepseek",
    "vast": "vast_ai",
    "vast_ai": "vast_ai",
    "runpod": "runpod",
    "fanvue": "fanvue",
    "onlyfans": "onlyfans",
    "loyalfans": "loyalfans",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "youtube": "youtube",
    "x": "x",
}


def _provider(value: Any) -> ProviderType:
    """Resolve a public provider name to the encrypted credential namespace."""
    normalized = str(value or "").strip().lower()
    name = _PROVIDER_ALIASES.get(normalized)
    if not name:
        raise MCPToolError("Unsupported provider", "INVALID_PROVIDER", 422)
    try:
        return ProviderType(name)
    except ValueError as exc:
        raise MCPToolError("Unsupported provider", "INVALID_PROVIDER", 422) from exc


def _expiry(value: Any) -> str:
    """Return an explicit timezone-aware expiry, defaulting to 90 days."""
    if value is None:
        return (datetime.now(UTC) + timedelta(days=90)).isoformat()
    if not isinstance(value, str):
        raise MCPToolError("expires_at must be an ISO-8601 timestamp", "INVALID_INPUT", 422)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MCPToolError("expires_at must be an ISO-8601 timestamp", "INVALID_INPUT", 422) from exc
    if parsed.tzinfo is None:
        raise MCPToolError("expires_at must include a timezone", "INVALID_INPUT", 422)
    return parsed.isoformat()


async def add_api_key(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Encrypt and store a customer API key, returning masked metadata only."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    provider_name = str(params.get("provider", params.get("provider_name", ""))).lower()
    provider = _provider(provider_name)
    secret = params.get("api_key", params.get("secret"))
    if not isinstance(secret, str) or len(secret) < 8:
        raise MCPToolError("api_key must contain at least 8 characters", "INVALID_INPUT", 422)
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "add_api_key", key)
    if prior:
        return prior
    metadata = {"label": str(params.get("label", ""))[:100], "source": "mcp"}
    result = CredentialService.store(
        org_id=context.org_id,
        provider=provider,
        secret=secret,
        environment=str(params.get("environment", "production")),
        actor=context.user_id,
        key_id=str(params.get("key_id", ""))[:120],
        metadata=metadata,
        expires_at=_expiry(params.get("expires_at")),
    )
    output = {"status": "stored", "credential": result}
    return remember_result(context, "add_api_key", key, output)


async def list_api_keys(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List masked credential metadata for the authenticated tenant."""
    reject_org_selectors(params)
    provider = _provider(params["provider"]) if params.get("provider") else None
    rows = CredentialService.get_status(
        org_id=context.org_id,
        provider=provider,
        environment=str(params.get("environment", "production")),
    )
    return {"items": rows, "total": len(rows)}


async def remove_api_key(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Revoke an API key without returning or logging its encrypted material."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    provider = _provider(params.get("provider"))
    environment = str(params.get("environment", "production"))
    key = params.get("idempotency_key") or f"{provider.value}:{environment}"
    prior = idempotent_result(context, "remove_api_key", key)
    if prior:
        return prior
    revoked = CredentialService.revoke(
        org_id=context.org_id,
        provider=provider,
        environment=environment,
        actor=context.user_id,
    )
    output = {"status": "revoked" if revoked else "not_found", "provider": provider.value}
    return remember_result(context, "remove_api_key", key, output)


async def test_api_key(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Validate configured credentials and provider metadata without secret disclosure."""
    reject_org_selectors(params)
    provider = _provider(params.get("provider"))
    result = CredentialService.validate(
        org_id=context.org_id,
        provider=provider,
        environment=str(params.get("environment", "production")),
        actor=context.user_id,
    )
    return {"provider": provider.value, **result}


async def get_default_provider(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Return provider selection/capability metadata without credential values."""
    reject_org_selectors(params)
    configured = CredentialService.get_status(org_id=context.org_id)
    providers = list_providers()
    return {
        "default": str(params.get("workload", "image")),
        "configured_providers": [row.get("provider") for row in configured],
        "providers": providers,
        "credentials": [{key: value for key, value in row.items() if key != "org_id"} for row in configured],
    }
