"""Add consent_records table for first-class consent subsystem.

Consent is NOT a boolean flag. It is a versioned, scoped, revocable,
auditable record with provenance tracking and enforcement through the
Governance Boundary.

Key features:
    - Scoped: LIKENESS, VOICE, TRAINING, GENERATION, ADULT_CONTENT,
      COMMERCIAL, PUBLISHING, CLIENT_WORK
    - Versioned: incrementing version per talent
    - Revocable: revoked_at preserves audit trail
    - Provenance-tracked: SELF_ATTESTED, REPRESENTATIVE, PLATFORM_VERIFIED, IMPORTED
    - Scope-specific evaluation: only relevant scopes checked per operation
    - Fictional talent exemption (enforced at service layer)

Implements:
    - R10.2: Consent required for real-person talent operations
    - R10.3: Consent scopes independently manageable
    - R10.11: Consent revocation
    - R10.12: Consent expiration
    - A2-004: First-class consent architecture

Revision ID: 20260818001
Revises: 20260817001
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260818001"
down_revision: Union[str, None] = "20260817001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create consent_records table with indexes."""
    op.create_table(
        "consent_records",
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
            "talent_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Talent this consent applies to",
        ),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            comment=(
                "Consent scopes: LIKENESS, VOICE, TRAINING, GENERATION, "
                "ADULT_CONTENT, COMMERCIAL, PUBLISHING, CLIENT_WORK"
            ),
        ),
        sa.Column(
            "evidence_type",
            sa.String(100),
            nullable=True,
            comment="signed_document, email, platform_attestation, verbal_recorded",
        ),
        sa.Column(
            "evidence_url",
            sa.Text(),
            nullable=True,
            comment="Reference to stored evidence document",
        ),
        sa.Column(
            "grantor_identity",
            sa.String(255),
            nullable=True,
            comment="Who granted consent (name/email/identifier)",
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When consent was granted",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When consent expires (NULL = no expiry)",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When consent was revoked (NULL = active)",
        ),
        sa.Column(
            "revocation_reason",
            sa.Text(),
            nullable=True,
            comment="Documented reason for revocation",
        ),
        sa.Column(
            "restrictions",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="JSON conditions/limitations on the consent",
        ),
        sa.Column(
            "provenance",
            sa.String(50),
            nullable=False,
            comment="SELF_ATTESTED, REPRESENTATIVE, PLATFORM_VERIFIED, IMPORTED",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Incrementing version for this talent's consent",
        ),
        sa.Column(
            "verification_state",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'unverified'"),
            comment="unverified, pending_review, verified, disputed",
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
    )

    # Primary tenant isolation index
    op.create_index(
        "ix_consent_records_org_id",
        "consent_records",
        ["org_id"],
    )

    # Composite index for per-org per-talent queries
    op.create_index(
        "ix_consent_records_org_talent",
        "consent_records",
        ["org_id", "talent_id"],
    )

    # Index for talent_id lookups
    op.create_index(
        "ix_consent_records_talent_id",
        "consent_records",
        ["talent_id"],
    )

    # Partial index for active consent records (fast evaluation)
    op.execute(sa.text("""
        CREATE INDEX ix_consent_records_active
        ON consent_records (org_id, talent_id)
        WHERE revoked_at IS NULL;
    """))

    # Enable RLS
    op.execute(sa.text("""
        ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;
    """))

    # RLS policy: tenant isolation
    op.execute(sa.text("""
        CREATE POLICY "consent_tenant_isolation" ON consent_records
            FOR ALL
            USING (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ))
            WITH CHECK (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ));
    """))


def downgrade() -> None:
    """Drop consent_records table and associated objects."""
    op.execute(sa.text(
        "DROP POLICY IF EXISTS \"consent_tenant_isolation\" ON consent_records;"
    ))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_consent_records_active;"))
    op.drop_index("ix_consent_records_talent_id", table_name="consent_records")
    op.drop_index("ix_consent_records_org_talent", table_name="consent_records")
    op.drop_index("ix_consent_records_org_id", table_name="consent_records")
    op.drop_table("consent_records")
