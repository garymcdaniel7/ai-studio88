"""Talent Relationship ORM model.

Represents a typed relationship between two talent entities within a workspace.
Enforces uniqueness on (source_talent_id, target_talent_id, relationship_type).

Requirements: R10.7
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class TalentRelationship(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Typed relationship between two talent entities.

    Types: associated, friends, couple, wears, uses, lives_in,
           holds, appears_with, pairs_with, variant_of.

    Enforces uniqueness: only one relationship of a given type
    can exist between two specific talent entities.

    Validates: R10.7
    """

    __tablename__ = "talent_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_talent_id",
            "target_talent_id",
            "relationship_type",
            name="uq_talent_relationships_src_tgt_type",
        ),
    )

    source_talent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    target_talent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="associated"
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
