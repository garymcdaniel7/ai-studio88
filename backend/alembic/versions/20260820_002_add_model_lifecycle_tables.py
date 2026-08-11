"""Add model_registry and model_transitions tables for promotion gates.

Implements the model/LoRA promotion gate lifecycle (R67):
    IMPORTED/TRAINED → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED

Tables:
    - model_registry: Tracks model artifacts and their lifecycle state
    - model_transitions: Immutable audit log of all state transitions

Key features:
    - Two risk classes: STANDARD (auto-promote) and HIGH_RISK (human approval)
    - Quarantine from any state (immediate unavailability)
    - Full audit trail: model_id, from_state, to_state, actor, evidence, timestamp
    - RLS policies for tenant isolation

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8

Revision ID: 20260820002
Revises: 20260820001
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260820002"
down_revision: Union[str, None] = "20260820001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create model_registry and model_transitions tables."""

    # ── model_registry ────────────────────────────────────────────────────────
    op.create_table(
        "model_registry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope (tenant isolation)",
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="Human-readable model name",
        ),
        sa.Column(
            "model_type",
            sa.String(50),
            nullable=False,
            server_default="lora",
            comment="Type: lora, checkpoint, embedding",
        ),
        sa.Column(
            "lifecycle_state",
            sa.String(30),
            nullable=False,
            server_default="imported",
            comment="Current lifecycle state per R67.1",
        ),
        sa.Column(
            "risk_class",
            sa.String(20),
            nullable=False,
            server_default="standard",
            comment="Risk classification: standard or high_risk",
        ),
        sa.Column(
            "base_model_id",
            sa.String(200),
            nullable=True,
            comment="Base model identifier for LoRA",
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(64),
            nullable=True,
            comment="SHA-256 hash for integrity verification",
        ),
        sa.Column(
            "storage_key",
            sa.String(500),
            nullable=True,
            comment="B2 storage key for the model artifact",
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            nullable=True,
            comment="File size in bytes",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="Additional metadata",
        ),
        sa.Column(
            "quarantine_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for quarantine",
        ),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When quarantined",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CHECK constraints
        sa.CheckConstraint(
            "lifecycle_state IN ('imported', 'trained', 'integrity_verified', "
            "'evaluated', 'approved', 'active', 'deprecated', 'quarantined')",
            name="ck_model_registry_lifecycle_state",
        ),
        sa.CheckConstraint(
            "risk_class IN ('standard', 'high_risk')",
            name="ck_model_registry_risk_class",
        ),
        sa.CheckConstraint(
            "model_type IN ('lora', 'checkpoint', 'embedding')",
            name="ck_model_registry_model_type",
        ),
    )

    # Indexes for model_registry
    op.create_index(
        "ix_model_registry_org_id",
        "model_registry",
        ["org_id"],
    )
    op.create_index(
        "ix_model_registry_lifecycle_state",
        "model_registry",
        ["lifecycle_state"],
    )
    op.create_index(
        "ix_model_registry_org_state",
        "model_registry",
        ["org_id", "lifecycle_state"],
    )

    # ── model_transitions ─────────────────────────────────────────────────────
    op.create_table(
        "model_transitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope (tenant isolation)",
        ),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to model_registry.id",
        ),
        sa.Column(
            "from_state",
            sa.String(30),
            nullable=False,
            comment="State before transition",
        ),
        sa.Column(
            "to_state",
            sa.String(30),
            nullable=False,
            comment="State after transition",
        ),
        sa.Column(
            "actor",
            sa.String(200),
            nullable=False,
            comment="Identity performing the transition",
        ),
        sa.Column(
            "actor_type",
            sa.String(20),
            nullable=False,
            server_default="human",
            comment="Actor type: human or system",
        ),
        sa.Column(
            "risk_class",
            sa.String(20),
            nullable=False,
            comment="Risk class at time of transition",
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="Supporting evidence and gate check results",
        ),
        sa.Column(
            "gate_checks_performed",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Gate checks that were run",
        ),
        sa.Column(
            "gate_checks_passed",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Gate checks that passed",
        ),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether transition succeeded",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if transition failed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Transition timestamp",
        ),
    )

    # Indexes for model_transitions
    op.create_index(
        "ix_model_transitions_org_id",
        "model_transitions",
        ["org_id"],
    )
    op.create_index(
        "ix_model_transitions_model_id",
        "model_transitions",
        ["model_id"],
    )
    op.create_index(
        "ix_model_transitions_model_created",
        "model_transitions",
        ["model_id", "created_at"],
    )

    # ── RLS Policies ──────────────────────────────────────────────────────────
    op.execute("ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY model_registry_org_isolation ON model_registry
            FOR ALL
            USING (org_id = (current_setting('app.current_org_id', true))::uuid)
            WITH CHECK (org_id = (current_setting('app.current_org_id', true))::uuid)
        """
    )

    op.execute("ALTER TABLE model_transitions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY model_transitions_org_isolation ON model_transitions
            FOR ALL
            USING (org_id = (current_setting('app.current_org_id', true))::uuid)
            WITH CHECK (org_id = (current_setting('app.current_org_id', true))::uuid)
        """
    )


def downgrade() -> None:
    """Drop model_transitions and model_registry tables."""
    op.execute("DROP POLICY IF EXISTS model_transitions_org_isolation ON model_transitions")
    op.execute("DROP POLICY IF EXISTS model_registry_org_isolation ON model_registry")

    op.drop_index("ix_model_transitions_model_created", table_name="model_transitions")
    op.drop_index("ix_model_transitions_model_id", table_name="model_transitions")
    op.drop_index("ix_model_transitions_org_id", table_name="model_transitions")
    op.drop_table("model_transitions")

    op.drop_index("ix_model_registry_org_state", table_name="model_registry")
    op.drop_index("ix_model_registry_lifecycle_state", table_name="model_registry")
    op.drop_index("ix_model_registry_org_id", table_name="model_registry")
    op.drop_table("model_registry")
