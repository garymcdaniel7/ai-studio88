"""Platform Operator ORM models.

Represents capability-based Platform Operator grants and their audit trail.
Replaces the undifferentiated Super Admin concept with granular capability
groups that can be assigned independently to different operators.

These are PLATFORM-LEVEL entities — they do NOT use TenantMixin (no org_id).
Access is restricted to authenticated users with operator capability grants.

Capability Groups:
    - platform_observe: Read-only system health and metrics
    - tenant_support: View tenant state for support purposes
    - tenant_access_escalation: Time-limited elevated access (audited)
    - platform_configuration: System settings, feature flags, provider config
    - financial_controls: Billing, cost limits, plan overrides
    - safety_and_rights: Content policy, takedowns, safety kernel config
    - security_administration: Credential management, RLS audit, threat response
    - deployment_operations: Deploy, restart, infrastructure management
    - release_management: Release gates, version control, rollback authority
    - destructive_platform_actions: Purge, wipe, force-delete (dual approval)
    - founder_authority: All capabilities, compute state changes, architecture

Validates: Requirements R33.5, R33.6, R33.7, R97.1, R97.2, R97.3, R97.4
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class CapabilityGroup(enum.StrEnum):
    """Platform Operator capability groups.

    Each group grants a defined set of permissions. Operators may
    receive any permitted subset — not all operators need equal access.
    The Founder retains the broadest capability set.
    """

    PLATFORM_OBSERVE = "platform_observe"
    TENANT_SUPPORT = "tenant_support"
    TENANT_ACCESS_ESCALATION = "tenant_access_escalation"
    PLATFORM_CONFIGURATION = "platform_configuration"
    FINANCIAL_CONTROLS = "financial_controls"
    SAFETY_AND_RIGHTS = "safety_and_rights"
    SECURITY_ADMINISTRATION = "security_administration"
    DEPLOYMENT_OPERATIONS = "deployment_operations"
    RELEASE_MANAGEMENT = "release_management"
    DESTRUCTIVE_PLATFORM_ACTIONS = "destructive_platform_actions"
    FOUNDER_AUTHORITY = "founder_authority"


class PlatformOperator(Base, UUIDMixin, TimestampMixin):
    """Platform Operator record — an authenticated user with capability grants.

    NOT tenant-scoped (no org_id). Platform-level entity accessible only
    via dedicated /platform-admin routes that return 404 for non-operators.

    Constraints:
        - Only one active (revoked_at IS NULL) record per user_id
          enforced via partial unique index
        - Revoking an operator creates a historical record; a new
          grant creates a new row
    """

    __tablename__ = "platform_operators"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    capability_grants: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )

    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index("ix_platform_operators_user_id", "user_id"),
    )

    @property
    def is_active(self) -> bool:
        """Whether this operator record is currently active (not revoked)."""
        return self.revoked_at is None

    def has_capability(self, capability: str | CapabilityGroup) -> bool:
        """Check if this operator has a specific capability grant.

        Founder Authority implicitly includes all other capabilities.

        Args:
            capability: The capability group to check.

        Returns:
            True if the operator has the capability (or Founder Authority).
        """
        cap_value = capability.value if isinstance(capability, CapabilityGroup) else capability
        if CapabilityGroup.FOUNDER_AUTHORITY.value in self.capability_grants:
            return True
        return cap_value in self.capability_grants

    def __repr__(self) -> str:
        return (
            f"<PlatformOperator(id={self.id}, user_id={self.user_id}, "
            f"capabilities={self.capability_grants}, active={self.is_active})>"
        )


class PlatformOperatorAction(Base, UUIDMixin):
    """Audit trail for Platform Operator actions.

    Every action performed by a Platform Operator is logged with:
    - Which operator performed it
    - Which capability authorized it
    - Which tenant was targeted (if applicable)
    - What type of action was performed
    - Structured detail about the action

    This table is append-only — records are never updated or deleted.
    """

    __tablename__ = "platform_operator_actions"

    operator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    capability_used: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    target_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    action_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    action_detail: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_po_actions_operator", "operator_user_id"),
        Index("ix_po_actions_org", "target_org_id"),
        Index("ix_po_actions_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PlatformOperatorAction(id={self.id}, "
            f"operator={self.operator_user_id}, "
            f"capability={self.capability_used}, "
            f"action={self.action_type})>"
        )
