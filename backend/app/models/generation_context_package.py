"""Generation Context Package ORM model.

An immutable, versioned snapshot of all inputs resolved before job dispatch.
Once created, a context package is NEVER modified — enabling full
reproducibility and audit of what inputs produced what output.

All generation surfaces (Brain, API, MCP, scheduled, batch) use the same
canonical Generation_Context_Package boundary.

Validates: Requirements R60.1, R60.2, R60.3, R60.4, R60.5, R60.6
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class GenerationContextPackage(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Immutable generation context package.

    Captures the complete state of all inputs at the moment of job creation.
    Once stored, no field may be modified. Stale reference detection is
    performed at validation time — if any referenced entity has changed
    state (deleted, quarantined, revoked), the package is invalid.

    Always scoped to org_id. Cross-tenant access returns 404.
    """

    __tablename__ = "generation_context_packages"

    # Version auto-increments per org
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Auto-incrementing version number per org",
    )

    # Talent snapshot
    talent_record: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Frozen talent data: id, name, type, identity_classification, "
            "adult_status, creative_dna_version at time of package creation"
        ),
    )

    # Creative DNA version reference
    creative_dna_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Creative DNA version ID used for this generation",
    )

    # Source assets (references with checksums)
    source_assets: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Array of source asset references: "
            "[{asset_id, storage_key, checksum, role}]"
        ),
    )

    # Model and LoRA selections
    model_lora_selections: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Model/LoRA configuration: "
            "{model_id, model_version, loras: [{id, version, strength, type}]}"
        ),
    )

    # Prompt instructions
    prompt_instructions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Prompt configuration: "
            "{positive_prompt, negative_prompt, cfg_scale, steps, sampler, "
            "scheduler, seed, dimensions}"
        ),
    )

    # Consent verification result
    consent_verification_result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Consent check outcome: "
            "{verified: bool, scopes_checked, scopes_present, "
            "fictional_exemption: bool, evaluated_at}"
        ),
    )

    # Safety evaluation result
    safety_evaluation_result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Safety policy evaluation: "
            "{passed: bool, content_rating, policy_level, "
            "checks_performed, evaluated_at}"
        ),
    )

    # Workflow template
    workflow_template: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Workflow configuration: "
            "{workflow_id, workflow_version, template_name, "
            "parameters_injected}"
        ),
    )

    # Project constraints
    project_constraints: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Project-level constraints: "
            "{project_id, budget_limit_usd, quality_tier, "
            "privacy_restrictions, deadline}"
        ),
    )

    # Initiating surface (for audit)
    initiated_by: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Generation surface: brain, api, mcp, scheduled, batch",
    )

    # User who created the package
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User who initiated the generation request",
    )
