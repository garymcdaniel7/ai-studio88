"""Workspace Privacy Configuration ORM model.

Stores per-workspace privacy restrictions controlling which providers
and infrastructure a workspace's data can flow through.

Restriction types:
- local_models_only: No external LLM calls
- customer_compute_only: No platform GPU
- approved_llm_only: Whitelist of allowed LLM providers
- no_external_llm_for_project: Project-scoped LLM restriction
- approved_storage_only: Whitelist of allowed storage providers
- talent_provider_restriction: Per-talent provider rules
- project_privacy: Project-scoped privacy settings

Brain/Hermes, LLM routing, job dispatch all check these restrictions.

Validates: Requirements R103.1, R103.2, R103.3
"""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


# Valid restriction types — mirrors the CHECK constraint in the migration
VALID_RESTRICTION_TYPES = frozenset({
    "local_models_only",
    "customer_compute_only",
    "approved_llm_only",
    "no_external_llm_for_project",
    "approved_storage_only",
    "talent_provider_restriction",
    "project_privacy",
})


class WorkspacePrivacyConfigModel(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Per-workspace privacy restriction record.

    Each row represents one active restriction for a workspace. A workspace
    may have multiple restrictions of different types active simultaneously.

    restriction_target is used for scoped restrictions:
    - no_external_llm_for_project → project_id
    - talent_provider_restriction → talent_id
    - NULL means workspace-wide restriction
    """

    __tablename__ = "workspace_privacy_config"

    restriction_type: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        comment="Type of privacy restriction being applied",
    )
    restriction_target: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
        comment="Optional target (project_id, talent_id) for scoped restrictions",
    )
    allowed_providers: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
        server_default="{}",
        comment="Provider names explicitly allowed (whitelist)",
    )
    denied_providers: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
        server_default="{}",
        comment="Provider names explicitly denied (blocklist)",
    )
