"""Add rights_cases table for rights/takedown case management.

Rights cases are PLATFORM-LEVEL entities — NO tenant RLS.
Access is restricted to Platform Operators with safety_and_rights capability.

Case lifecycle:
    RECEIVED → TRIAGED → ACTION_REQUIRED/NO_ACTION →
    RESTRICTED/REMOVED/RESOLVED → CLOSED
    With APPEALED branch: APPEALED → RE_REVIEWED → CLOSED

Key features:
    - CSAM auto-escalation to critical priority
    - Legal holds prevent permanent deletion
    - Append-only actions_taken JSONB for tamper-evident audit
    - Reporter contact encrypted at rest (Supabase column-level encryption)

Implements:
    - R40.1: Report intake endpoint
    - R40.2: Case record creation
    - R40.3: Status transitions
    - R40.4: Takedown action enforcement
    - R40.5: Legal holds
    - R40.7: Appeals
    - R40.8: Action logging
    - R40.9: Append-oriented event log
    - A2-005: Rights/Takedown case lifecycle

Revision ID: 20260819002
Revises: 20260818001
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260819002"
down_revision: Union[str, None] = "20260818001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create rights_cases table with indexes and check constraints."""
    op.create_table(
        "rights_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "case_type",
            sa.Text(),
            nullable=False,
            comment="copyright, trademark, likeness, privacy, illegal, csam, other",
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'received'"),
            comment="Case lifecycle status",
        ),
        sa.Column(
            "priority",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'normal'"),
            comment="critical, high, normal, low",
        ),
        sa.Column(
            "reporter_contact",
            postgresql.JSONB(),
            nullable=True,
            comment="Reporter email, name (encrypted at rest)",
        ),
        sa.Column(
            "target_org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Workspace containing reported content",
        ),
        sa.Column(
            "target_talent_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="Talent IDs referenced in the complaint",
        ),
        sa.Column(
            "target_asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="Asset IDs referenced in the complaint",
        ),
        sa.Column(
            "reported_urls",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="URLs reported in the complaint",
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="References to stored evidence documents",
        ),
        sa.Column(
            "assigned_operator",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Platform Operator handling this case",
        ),
        sa.Column(
            "actions_taken",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="Append-only audit trail of actions taken",
        ),
        sa.Column(
            "resolution",
            sa.Text(),
            nullable=True,
            comment="Final resolution description",
        ),
        sa.Column(
            "appeal_state",
            sa.Text(),
            nullable=True,
            comment="Appeal metadata if case was appealed",
        ),
        sa.Column(
            "legal_hold_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Prevents permanent deletion of affected content",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Check constraints
        sa.CheckConstraint(
            "case_type IN ('copyright', 'trademark', 'likeness', 'privacy', "
            "'illegal', 'csam', 'other')",
            name="ck_rights_cases_case_type",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'triaged', 'action_required', 'no_action', "
            "'restricted', 'removed', 'resolved', 'appealed', 're_reviewed', 'closed')",
            name="ck_rights_cases_status",
        ),
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'normal', 'low')",
            name="ck_rights_cases_priority",
        ),
    )

    # Indexes per design spec
    op.create_index(
        "ix_rights_cases_status",
        "rights_cases",
        ["status"],
    )
    op.create_index(
        "ix_rights_cases_org",
        "rights_cases",
        ["target_org_id"],
    )
    op.create_index(
        "ix_rights_cases_priority",
        "rights_cases",
        ["priority", "status"],
    )

    # NOTE: NO RLS on this table — it is a platform-level entity.
    # Access is controlled at the application layer via Platform Operator
    # capability checks (safety_and_rights).
    # Per design: "Platform-level entities (rights_cases, support_sessions,
    # platform_operators, feature_rollouts, compute config) use explicit
    # privileged paths with service-role queries, NOT tenant RLS."


def downgrade() -> None:
    """Drop rights_cases table and associated objects."""
    op.drop_index("ix_rights_cases_priority", table_name="rights_cases")
    op.drop_index("ix_rights_cases_org", table_name="rights_cases")
    op.drop_index("ix_rights_cases_status", table_name="rights_cases")
    op.drop_table("rights_cases")
