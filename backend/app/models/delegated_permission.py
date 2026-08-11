"""Delegated Permission ORM model.

Stores capability-specific delegated permissions that allow Hermes
to execute actions autonomously within configured limits.

Delegated permissions are:
    - Capability-specific (scoped to named action classes)
    - Connection-specific (scoped to named integrations, or NULL for all)
    - Revocable (immediately via revoked_at)
    - Auditable (full trail of grants and revocations)
    - Role-scoped (cannot exceed delegator's own permissions)
    - Subject to the Governance Boundary (R59)

Validates: Requirements R30.14, R98.3
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class DelegatedPermissionModel(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Delegated permission granting Hermes autonomous action within limits.

    Each row represents a single delegation of a specific action class
    to Hermes, optionally scoped to a specific connection and with an
    optional cost ceiling per invocation.

    Columns:
        id: UUID primary key.
        org_id: Workspace (tenant) scope.
        delegated_by: UUID of the user who granted this delegation.
        action_class: The specific action type delegated (e.g. 'generate_image').
        connection_scope: Optional UUID of a specific connection this applies to.
            NULL means the delegation applies to any connection.
        max_cost_usd: Maximum cost per single invocation under this delegation.
            NULL means no per-action cost limit (still subject to budget limits).
        expires_at: Optional expiration timestamp. NULL means no expiry.
        revoked_at: Set when the delegation is revoked. NULL means active.
    """

    __tablename__ = "delegated_permissions"

    delegated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User who granted this delegated permission",
    )
    action_class: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Action class delegated (e.g. generate_image, schedule_post)",
    )
    connection_scope: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=None,
        comment="Specific connection UUID, or NULL for all connections",
    )
    max_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        default=None,
        comment="Maximum cost per invocation in USD, or NULL for no per-action limit",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Expiration timestamp, or NULL for no expiry",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Revocation timestamp, or NULL if still active",
    )
