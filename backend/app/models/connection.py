"""Connection ORM model.

Represents a workspace or user integration connection (OAuth, API key, SSH, MCP).
Connections link external services (AI providers, storage, social, compute,
developer tools, business tools) to workspaces with explicit ownership and
lifecycle tracking.

Validates: Requirements R85.1, R85.3, R85.4, R92.1, R92.2, R92.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ConnectionOwnership(str, Enum):
    """Connection ownership classification.

    USER: Belongs to individual, follows them across workspaces.
    WORKSPACE: Belongs to org, stays when members leave.
    """

    USER = "user"
    WORKSPACE = "workspace"


class ConnectionLifecycle(str, Enum):
    """Connection lifecycle state machine.

    CONNECTING → CONNECTED → DEGRADED/REAUTH_REQUIRED → DISCONNECTED/REVOKED
    """

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"


class ConnectionCategory(str, Enum):
    """Connection category — determines capability surface."""

    AI_PROVIDER = "ai_provider"
    STORAGE = "storage"
    SOCIAL = "social"
    COMPUTE = "compute"
    DEVELOPER = "developer"
    BUSINESS = "business"


class ConnectionAuthMethod(str, Enum):
    """Supported authentication methods for connections."""

    OAUTH = "oauth"
    API_KEY = "api_key"
    SSH = "ssh"
    MCP = "mcp"


class Connection(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Connection entity — a workspace or user integration.

    Always scoped to org_id. USER connections also filter by user_id.
    Cross-tenant access returns 404.
    """

    __tablename__ = "connections"

    # Ownership & identity
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="NULL for workspace connections, set for user connections",
    )
    ownership: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Connection ownership: user or workspace",
    )
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Connection category: ai_provider, storage, social, compute, developer, business",
    )
    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Provider identifier: openai, instagram, runpod, etc.",
    )
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable display name",
    )

    # Lifecycle
    lifecycle_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="connecting",
        comment="Lifecycle state: connecting, connected, degraded, reauth_required, disconnected, revoked",
    )

    # Authentication
    auth_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Auth method: oauth, api_key, ssh, mcp",
    )
    oauth_token_ref: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Reference to encrypted token in workspace_credentials table",
    )

    # Capabilities & access control
    capabilities: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="Discovered provider capabilities (JSON array)",
    )
    allowed_roles: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default="{owner,admin,editor}",
        comment="Roles allowed to use this connection",
    )
    tool_policy: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Per-tool allow/deny policy (JSON object)",
    )

    # Health monitoring
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last health check",
    )
    health_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Last health check result: healthy, degraded, unreachable",
    )

    # Table-level indexes (beyond TenantMixin's org_id index)
    __table_args__ = (
        Index(
            "ix_connections_user_id",
            "user_id",
            postgresql_where="user_id IS NOT NULL",
        ),
        Index("ix_connections_org_category", "org_id", "category"),
    )
