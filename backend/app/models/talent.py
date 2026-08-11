"""AI Talent ORM model.

Represents an AI persona/character within a workspace.
Supports identity classification (FICTIONAL, REAL_PERSON_SELF, REAL_PERSON_AUTHORIZED)
and soft-delete via deleted_at.

Requirements: R10.1, R10.4, R10.5, R10.6
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDMixin


class AiTalent(Base, UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """AI Talent entity — an AI persona within a workspace.

    Always scoped to org_id. Cross-tenant access returns 404.
    Soft-delete via deleted_at timestamp; excluded from queries automatically.

    Validates: R10.1, R10.4, R10.5, R10.6
    """

    __tablename__ = "talent"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    talent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    identity_classification: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
