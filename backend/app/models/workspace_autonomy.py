"""Workspace Autonomy Profile ORM model.

Stores per-workspace agent autonomy level and mandatory controls.
This is a tenant-scoped table — each workspace has at most one config row.

Autonomy levels:
    ADVISORY: Recommend only — no mutations without explicit user instruction.
    ASSISTED: Low-risk auto-execute, high-risk requires confirmation.
    AUTONOMOUS_WITHIN_LIMITS: Delegated actions within configured limits.

Mandatory controls are ALWAYS enforced regardless of autonomy level:
    - Safety kernel actions
    - Security-sensitive operations
    - Consent verification
    - Budget-exceeding operations
    - Destructive operations

Validates: Requirements R98.1, R98.2, R30.12, R30.13
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class WorkspaceAutonomyProfileModel(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Per-workspace agent autonomy profile.

    Stores the autonomy level (advisory/assisted/autonomous_within_limits)
    and a JSONB object of mandatory control configurations.

    One row per workspace (org_id is unique). Upsert on update.
    """

    __tablename__ = "workspace_autonomy_profiles"

    autonomy_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="advisory",
        comment="Agent autonomy level: advisory, assisted, or autonomous_within_limits",
    )
    mandatory_controls: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Mandatory controls enforced regardless of autonomy level",
    )
    last_updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User ID who last updated this configuration",
    )
