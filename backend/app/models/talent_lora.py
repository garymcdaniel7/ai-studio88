"""Talent-LoRA Junction ORM model.

Represents the association between a talent and a LoRA model.
Enforces a maximum of 5 LoRAs per talent (application-level constraint).

Requirements: R10.8, R10.9
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class TalentLora(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Junction table: talent ↔ LoRA model association.

    Each talent can have up to 5 associated LoRAs (enforced at service layer).
    LoRAs marked always_on are automatically injected into generation workflows.

    Validates: R10.8, R10.9
    """

    __tablename__ = "talent_loras"

    talent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    lora_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="identity"
    )
    strength: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, default=0.8
    )
    always_on: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
