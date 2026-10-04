"""Shared safety contracts for the authenticated Phase 2 MCP surface."""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from backend.aios.mcp.auth import MCPClientIdentity

_ORG_SELECTOR_KEYS = frozenset({"org_id", "orgId", "org-id", "organization_id", "organizationId"})
_SECRET_KEY_PARTS = ("api_key", "apikey", "secret", "token", "password", "credential")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_IDEMPOTENCY_LOCK = threading.Lock()
_IDEMPOTENCY_RESULTS: dict[tuple[str, str, str], dict[str, Any]] = {}


class MCPToolError(Exception):
    """Structured, client-safe failure from an MCP tool."""

    def __init__(self, message: str, code: str, status_code: int = 422) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class MCPExecutionContext:
    """Trusted request context derived only from an authenticated MCP identity."""

    identity: MCPClientIdentity

    @property
    def org_id(self) -> str:
        """Return the authenticated organization or fail closed."""
        return require_org(self.identity.org_id)

    @property
    def user_id(self) -> str:
        """Return the authenticated actor identifier."""
        if not self.identity.issued_by:
            raise MCPToolError("Authenticated actor is required", "ACTOR_CONTEXT_REQUIRED", 403)
        return self.identity.issued_by

    @property
    def role(self) -> str:
        """Return the normalized MCP role."""
        return (self.identity.role or "").strip().lower()


def require_org(org_id: str | None) -> str:
    """Validate trusted tenant context before any database/provider access."""
    if not org_id or not isinstance(org_id, str):
        raise MCPToolError("Active workspace membership required", "WORKSPACE_CONTEXT_REQUIRED", 403)
    try:
        return str(uuid.UUID(org_id))
    except (TypeError, ValueError) as exc:
        raise MCPToolError("Active workspace membership required", "WORKSPACE_CONTEXT_REQUIRED", 403) from exc


def context_for(identity: MCPClientIdentity | None) -> MCPExecutionContext:
    """Require an authenticated MCP identity for Phase 2 tenant operations."""
    if identity is None:
        raise MCPToolError("Authenticated MCP identity required", "MCP_AUTH_REQUIRED", 401)
    return MCPExecutionContext(identity)


def reject_org_selectors(params: dict[str, Any]) -> None:
    """Reject organization selectors instead of silently accepting spoofable input."""
    supplied = _ORG_SELECTOR_KEYS.intersection(params)
    if supplied:
        raise MCPToolError(
            "Organization scope comes from MCP authentication",
            "ORG_SELECTOR_NOT_ALLOWED",
            422,
        )


def require_role(context: MCPExecutionContext, *allowed: str) -> None:
    """Enforce the MCP credential role before a mutation or sensitive read."""
    if context.role not in {role.lower() for role in allowed}:
        raise MCPToolError(
            f"Role '{context.role or 'unknown'}' is not permitted for this tool",
            "ROLE_NOT_ALLOWED",
            403,
        )


def parse_uuid(value: Any, field: str) -> str:
    """Parse a UUID input and return its canonical string representation."""
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise MCPToolError(f"{field} must be a valid UUID", "INVALID_INPUT", 422) from exc


def parse_safe_id(value: Any, field: str) -> str:
    """Validate non-UUID job/workflow identifiers without accepting path syntax."""
    if not isinstance(value, str) or not value or not _SAFE_ID.fullmatch(value):
        raise MCPToolError(f"{field} is invalid", "INVALID_INPUT", 422)
    return value


def require_mapping(value: Any, field: str = "parameters") -> dict[str, Any]:
    """Require a JSON object for a tool's parameters."""
    if not isinstance(value, dict):
        raise MCPToolError(f"{field} must be an object", "INVALID_INPUT", 422)
    return value


def safe_copy(value: Any) -> Any:
    """Recursively redact secret-like values for logs, audit, and MCP output."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                result[key] = "[REDACTED]"
            else:
                result[key] = safe_copy(item)
        return result
    if isinstance(value, list):
        return [safe_copy(item) for item in value]
    if isinstance(value, tuple):
        return [safe_copy(item) for item in value]
    if isinstance(value, str):
        words = value.split()
        secret_prefixes = ("sk-", "sk-ant-", "eyJ", "mcp_", "xoxb-", "hf_", "xi_")
        return " ".join(
            "[REDACTED]"
            if len(word) > 40 or len(word) > 24 and word.startswith(secret_prefixes)
            else word
            for word in words
        )
    return value


def safe_record(value: Any) -> dict[str, Any]:
    """Convert a service record to a secret-free JSON mapping."""
    if isinstance(value, dict):
        record = value
    elif hasattr(value, "__dict__"):
        record = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    else:
        return {"value": safe_copy(value)}
    return safe_copy(record)


def idempotent_result(
    context: MCPExecutionContext,
    tool_name: str,
    key: Any,
) -> dict[str, Any] | None:
    """Return a prior mutation result for the authenticated tenant, if present."""
    if not isinstance(key, str) or not key.strip():
        return None
    with _IDEMPOTENCY_LOCK:
        result = _IDEMPOTENCY_RESULTS.get((context.org_id, tool_name, key.strip()))
    return dict(result) if result is not None else None


def remember_result(
    context: MCPExecutionContext,
    tool_name: str,
    key: Any,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Store a safe mutation result under an org-threaded idempotency key."""
    if isinstance(key, str) and key.strip():
        with _IDEMPOTENCY_LOCK:
            _IDEMPOTENCY_RESULTS[(context.org_id, tool_name, key.strip())] = dict(result)
    return result


def clear_idempotency() -> None:
    """Clear in-memory MCP idempotency state for isolated tests."""
    with _IDEMPOTENCY_LOCK:
        _IDEMPOTENCY_RESULTS.clear()
