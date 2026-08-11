"""Workspace Fallback Configuration ORM model.

Stores per-workspace LLM fallback preferences and privacy-denied providers.
This is a tenant-scoped table — each workspace has at most one config row.

Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class WorkspaceFallbackConfigModel(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Per-workspace LLM fallback configuration.

    Stores the fallback_mode (auto/ask/strict) and a list of provider names
    that are denied by privacy policy for this workspace.

    One row per workspace (org_id is unique). Upsert on update.
    """

    __tablename__ = "workspace_fallback_config"

    fallback_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="auto",
        comment="Fallback behavior: auto, ask, or strict",
    )
    denied_providers: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=list,
        comment="Provider names blocked by privacy policy",
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User ID who last updated this configuration",
    )
