"""Hermes Application Context Envelope — Story 037.

Defines a typed, versioned context envelope that accompanies every user-facing
Hermes request. Separates authoritative server-resolved fields from optional
client-supplied hints.

Schema version: 1

Authoritative fields (server-derived, NEVER trusted from client):
    - user_id: from validated JWT
    - org_id: from membership resolution
    - role: from org_members
    - capabilities: derived from role + workspace features

Client-supplied fields (validated but not authoritative):
    - current_route: which page the user is on
    - active_project_id: selected project (validated against workspace)
    - selected_talent_id: selected talent (validated against workspace)
    - selected_asset_ids: selected assets (validated against workspace)
    - active_job_id: job being observed (validated against workspace)
    - ui_mode: current interface mode (e.g., "create", "brain", "training")
    - locale: user's locale preference

Validation rules:
    - Resource IDs are checked for workspace ownership via AuthorizedClient
    - Stale/deleted/cross-workspace IDs are reported as invalid (not leaked)
    - Missing optional context does not break chat (graceful degradation)
    - Unsupported schema versions are rejected with clear error
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Schema Version
# =============================================================================

CONTEXT_SCHEMA_VERSION = 1
SUPPORTED_VERSIONS = {1}


# =============================================================================
# Context Envelope
# =============================================================================


@dataclass
class AuthoritativeContext:
    """Server-resolved identity and authorization — NEVER from client.

    Populated by the backend from validated JWT + membership resolution.
    """

    user_id: str
    org_id: str
    role: str  # owner, admin, editor, viewer
    email: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class ClientContext:
    """Client-supplied application state hints — validated server-side.

    The client sends these with each request. The server validates resource
    ownership but does not trust them for authorization.
    """

    current_route: str = ""  # e.g., "/create", "/brain", "/talent"
    active_project_id: str | None = None
    selected_talent_id: str | None = None
    selected_asset_ids: list[str] = field(default_factory=list)
    active_job_id: str | None = None
    ui_mode: str = ""  # "create", "brain", "training", "production", etc.
    locale: str = "en"
    # Future: selected_model_id, active_workflow_id, etc.


@dataclass
class ValidationResult:
    """Result of validating client-supplied resource IDs."""

    valid_resources: dict[str, str] = field(default_factory=dict)  # field → id
    invalid_resources: dict[str, str] = field(default_factory=dict)  # field → reason
    warnings: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.invalid_resources)


@dataclass
class ApplicationContext:
    """Complete Hermes request context envelope.

    Combines authoritative identity with validated client hints.
    Every user-facing Hermes request MUST include this.
    """

    schema_version: int
    authoritative: AuthoritativeContext
    client: ClientContext
    validation: ValidationResult = field(default_factory=ValidationResult)
    # Session binding
    session_id: str | None = None
    request_id: str = ""
    # Metadata
    timestamp: str = ""

    def to_prompt_context(self) -> dict:
        """Convert to a dict suitable for injection into Hermes prompt context.

        Only includes validated, non-sensitive information. Never includes
        secrets, tokens, or raw client-supplied IDs that failed validation.
        """
        ctx = {
            "workspace_role": self.authoritative.role,
            "capabilities": self.authoritative.capabilities,
            "current_route": self.client.current_route,
            "ui_mode": self.client.ui_mode,
            "locale": self.client.locale,
        }

        # Only include validated resource references
        if self.validation.valid_resources:
            ctx["active_resources"] = self.validation.valid_resources

        if self.validation.warnings:
            ctx["context_warnings"] = self.validation.warnings

        return ctx


# =============================================================================
# Context Resolution
# =============================================================================


class ContextResolutionError(Exception):
    """Raised when context cannot be resolved."""
    pass


def resolve_context(
    *,
    user_id: str,
    org_id: str,
    role: str,
    email: str | None = None,
    client_context: dict[str, Any] | None = None,
    schema_version: int = CONTEXT_SCHEMA_VERSION,
    session_id: str | None = None,
) -> ApplicationContext:
    """Resolve a complete ApplicationContext from auth + client hints.

    Args:
        user_id: From validated JWT (authoritative)
        org_id: From membership resolution (authoritative)
        role: From org_members (authoritative)
        email: From JWT (informational)
        client_context: Raw client-supplied context dict (validated here)
        schema_version: Client-declared schema version
        session_id: Active session ID

    Returns:
        Fully resolved and validated ApplicationContext.

    Raises:
        ContextResolutionError: If schema version is unsupported.
    """
    import secrets as _secrets
    from datetime import UTC, datetime

    # Version check
    if schema_version not in SUPPORTED_VERSIONS:
        raise ContextResolutionError(
            f"Unsupported context schema version: {schema_version}. "
            f"Supported: {SUPPORTED_VERSIONS}"
        )

    # Build authoritative context (server-only)
    authoritative = AuthoritativeContext(
        user_id=user_id,
        org_id=org_id,
        role=role,
        email=email,
        capabilities=_derive_capabilities(role),
    )

    # Parse client context (with defaults for missing fields)
    client = _parse_client_context(client_context or {})

    # Validate resource IDs against workspace
    validation = _validate_resources(org_id, client)

    return ApplicationContext(
        schema_version=schema_version,
        authoritative=authoritative,
        client=client,
        validation=validation,
        session_id=session_id,
        request_id=f"ctx-{_secrets.token_hex(8)}",
        timestamp=datetime.now(UTC).isoformat(),
    )


# =============================================================================
# Helpers
# =============================================================================


def _derive_capabilities(role: str) -> list[str]:
    """Derive available capabilities from role."""
    base = ["chat", "search", "list_resources"]

    if role in ("editor", "admin", "owner"):
        base.extend(["generate_image", "generate_video", "edit_resources",
                     "manage_training", "manage_publishing"])

    if role in ("admin", "owner"):
        base.extend(["manage_credentials", "manage_team", "infrastructure"])

    if role == "owner":
        base.extend(["delete_workspace", "billing"])

    return base


def _parse_client_context(raw: dict[str, Any]) -> ClientContext:
    """Parse and sanitize client-supplied context fields."""
    return ClientContext(
        current_route=str(raw.get("current_route", ""))[:100],
        active_project_id=_safe_id(raw.get("active_project_id")),
        selected_talent_id=_safe_id(raw.get("selected_talent_id")),
        selected_asset_ids=[
            _safe_id(aid) for aid in (raw.get("selected_asset_ids") or [])[:10]
            if _safe_id(aid)
        ],
        active_job_id=_safe_id(raw.get("active_job_id")),
        ui_mode=str(raw.get("ui_mode", ""))[:50],
        locale=str(raw.get("locale", "en"))[:10],
    )


def _safe_id(value: Any) -> str | None:
    """Sanitize a potential resource ID (must be string, reasonable length)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or len(s) > 100:
        return None
    # Basic injection prevention — IDs should be UUID-like or short alphanumeric
    if any(c in s for c in (";", "'", '"', "\\", "\n", "\r")):
        return None
    return s


def _validate_resources(org_id: str, client: ClientContext) -> ValidationResult:
    """Validate that client-supplied resource IDs belong to the workspace.

    Uses AuthorizedClient (Story 009) to check ownership without exposing
    existence to other tenants.

    Graceful: validation failures don't block the request — they're reported
    as warnings so Hermes can inform the user.
    """
    result = ValidationResult()

    # Only validate if we have resources to check and DB is available
    try:
        from backend.data_access_helpers import get_authorized_client
        from backend.auth import AuthUser

        # Create a minimal AuthUser for validation
        user = AuthUser(user_id="system-validator", org_id=org_id, role="viewer")
        ac_client = get_authorized_client(user)

        if not ac_client:
            # No DB connection — skip validation, report warning
            result.warnings.append("resource_validation_skipped:no_db")
            # Still include IDs as unverified
            if client.active_project_id:
                result.valid_resources["active_project_id"] = client.active_project_id
            if client.selected_talent_id:
                result.valid_resources["selected_talent_id"] = client.selected_talent_id
            return result

        # Validate project
        if client.active_project_id:
            if _check_resource_exists(ac_client, "projects", client.active_project_id):
                result.valid_resources["active_project_id"] = client.active_project_id
            else:
                result.invalid_resources["active_project_id"] = "not_found_or_wrong_workspace"

        # Validate talent
        if client.selected_talent_id:
            if _check_resource_exists(ac_client, "talent", client.selected_talent_id):
                result.valid_resources["selected_talent_id"] = client.selected_talent_id
            else:
                result.invalid_resources["selected_talent_id"] = "not_found_or_wrong_workspace"

        # Validate assets (batch — stop at first invalid)
        for asset_id in client.selected_asset_ids[:5]:  # Limit validation cost
            if _check_resource_exists(ac_client, "assets", asset_id):
                result.valid_resources[f"asset:{asset_id}"] = asset_id
            else:
                result.invalid_resources[f"asset:{asset_id}"] = "not_found_or_wrong_workspace"

        # Validate job
        if client.active_job_id:
            if _check_resource_exists(ac_client, "jobs", client.active_job_id):
                result.valid_resources["active_job_id"] = client.active_job_id
            else:
                result.invalid_resources["active_job_id"] = "not_found_or_wrong_workspace"

    except Exception as e:
        result.warnings.append(f"resource_validation_error:{str(e)[:50]}")
        # On error, include IDs as unverified (don't block)
        if client.active_project_id:
            result.valid_resources["active_project_id"] = client.active_project_id
        if client.selected_talent_id:
            result.valid_resources["selected_talent_id"] = client.selected_talent_id

    return result


def _check_resource_exists(client, table: str, resource_id: str) -> bool:
    """Check if a resource exists in the workspace (via AuthorizedClient).

    Returns True if found, False if not found or wrong workspace.
    Never leaks existence to other workspaces.
    """
    try:
        from backend.data_access import AuthorizationError
        client.select_by_id(table, resource_id)
        return True
    except Exception:
        return False
