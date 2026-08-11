"""Model/LoRA Lifecycle ORM models.

Tables:
    - model_registry: Tracks model/LoRA lifecycle state and metadata
    - model_transitions: Immutable audit log of all state transitions

Lifecycle states (R67.1):
    IMPORTED/TRAINED → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED

Risk classes (R67.4):
    STANDARD: auto-promote through integrity/compatibility checks
    HIGH_RISK: human approval required before APPROVED state

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ModelRegistryEntry(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A model or LoRA tracked through the promotion lifecycle.

    Each entry represents a model artifact (checkpoint, LoRA, etc.)
    progressing through the promotion gate lifecycle. State can only
    advance forward or jump to QUARANTINED.

    Validates: R67.1, R67.2, R34.8
    """

    __tablename__ = "model_registry"

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Human-readable model name"
    )
    model_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="lora",
        comment="Type: lora, checkpoint, embedding",
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="imported",
        index=True,
        comment="Current lifecycle state per R67.1",
    )
    risk_class: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="standard",
        comment="Risk classification: standard or high_risk",
    )
    base_model_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Identifier of the base model this LoRA/model is for",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of the model file for integrity verification",
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="B2 storage key for the model artifact",
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        nullable=True, comment="File size in bytes"
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Additional metadata (format, compatibility info, etc.)",
    )
    quarantine_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for quarantine (populated when state=quarantined)",
    )
    quarantined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when model was quarantined",
    )


class ModelTransition(Base, UUIDMixin, TenantMixin):
    """Immutable audit log of model lifecycle state transitions.

    Every promotion, deprecation, or quarantine action is logged here.
    Records are append-only — never updated or deleted.

    Validates: R67.6
    """

    __tablename__ = "model_transitions"

    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK to model_registry.id",
    )
    from_state: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="State before transition"
    )
    to_state: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="State after transition"
    )
    actor: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Identity of who/what performed the transition",
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="human",
        comment="Actor type: human or system",
    )
    risk_class: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Risk class at time of transition"
    )
    evidence: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Supporting evidence/gate check results",
    )
    gate_checks_performed: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="List of gate checks that were run",
    )
    gate_checks_passed: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="List of gate checks that passed",
    )
    success: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment="Whether the transition succeeded",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if transition failed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Transition timestamp",
    )
