"""Add brain memory 4-layer architecture tables.

Creates the brain memory layer tables:
    - brain_user_memory: Per-user private memory with provenance tracking
    - brain_workspace_knowledge: Workspace-level knowledge promoted from user memory
    - brain_conversations: Multi-mode conversation sessions (replaces brain_sessions)
    - brain_messages: Messages within conversations with actor and tool refs

Implements:
    - R93.1: Brain sessions must be per-user, never shared across users
    - R94.1: Cross-tenant learning isolation as security boundary
    - R29.1: Brain memory layers — session, user-private, workspace, platform

Revision ID: 20260812001
Revises: 20260811001
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260812001"
down_revision: Union[str, None] = "20260811002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create brain memory 4-layer tables with indexes and RLS."""
    # =========================================================================
    # 1. brain_user_memory — Per-user private memory with provenance
    # =========================================================================
    op.create_table(
        "brain_user_memory",
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
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "memory_type",
            sa.Text(),
            nullable=False,
            comment="Category of memory: preference, style, history, context, skill",
        ),
        sa.Column(
            "content",
            postgresql.JSONB,
            nullable=False,
            comment="Structured memory content",
        ),
        sa.Column(
            "provenance",
            sa.Text(),
            nullable=False,
            comment="How this memory was acquired",
        ),
        sa.Column(
            "confidence",
            sa.Numeric(precision=3, scale=2),
            nullable=True,
            comment="Confidence score 0.00-1.00 (NULL for USER_CONFIRMED)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Soft disable without deletion",
        ),
        sa.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Conversation that originated this memory (NULL for imports)",
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

    # CHECK constraint for provenance values
    op.execute(sa.text("""
        ALTER TABLE brain_user_memory
        ADD CONSTRAINT ck_brain_user_memory_provenance
        CHECK (provenance IN (
            'USER_CONFIRMED', 'OBSERVED', 'IMPORTED', 'INFERRED', 'SUGGESTED'
        ));
    """))

    # Indexes
    op.create_index(
        "ix_brain_user_memory_org_user",
        "brain_user_memory",
        ["org_id", "user_id"],
    )
    op.create_index(
        "ix_brain_user_memory_org_id",
        "brain_user_memory",
        ["org_id"],
    )

    # =========================================================================
    # 2. brain_workspace_knowledge — Workspace-level promoted knowledge
    # =========================================================================
    op.create_table(
        "brain_workspace_knowledge",
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
        ),
        sa.Column(
            "knowledge_type",
            sa.Text(),
            nullable=False,
            comment="Type of knowledge: style_guide, brand_voice, workflow_pattern, domain_fact",
        ),
        sa.Column(
            "content",
            postgresql.JSONB,
            nullable=False,
            comment="Structured knowledge content",
        ),
        sa.Column(
            "promoted_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who promoted this from private memory to workspace",
        ),
        sa.Column(
            "promoted_from",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Source brain_user_memory.id if promoted from user layer",
        ),
        sa.Column(
            "provenance",
            sa.Text(),
            nullable=False,
            comment="How this knowledge was acquired at workspace level",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # FK: promoted_from → brain_user_memory
    op.create_foreign_key(
        "fk_brain_workspace_knowledge_promoted_from_brain_user_memory",
        "brain_workspace_knowledge",
        "brain_user_memory",
        ["promoted_from"],
        ["id"],
        ondelete="SET NULL",
    )

    # Index on org_id
    op.create_index(
        "ix_brain_workspace_knowledge_org_id",
        "brain_workspace_knowledge",
        ["org_id"],
    )

    # =========================================================================
    # 3. brain_conversations — Per-user conversation sessions
    # =========================================================================
    op.create_table(
        "brain_conversations",
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
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "trust_domain",
            sa.Text(),
            nullable=False,
            server_default="CUSTOMER_USER",
            comment="Trust domain: CUSTOMER_USER, WORKSPACE, FOUNDER_PRIVATE, PLATFORM, SERVICE, SYSTEM",
        ),
        sa.Column(
            "mode",
            sa.Text(),
            nullable=False,
            server_default="creative",
            comment="Brain mode: creative, prompt_engineer, story, production, research, analyzer",
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=True,
            comment="User-visible conversation title (auto-generated or manual)",
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of the most recent message",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Extensible metadata (tags, collections, context hints)",
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

    # Composite index for listing user's conversations sorted by recency
    op.create_index(
        "ix_brain_conversations_org_user_created",
        "brain_conversations",
        ["org_id", "user_id", sa.text("created_at DESC")],
    )

    # =========================================================================
    # 4. brain_messages — Messages within conversations
    # =========================================================================
    op.create_table(
        "brain_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "actor",
            sa.Text(),
            nullable=False,
            comment="Who sent this message: user, brain, hermes, system",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "tool_refs",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="References to tools/agents invoked for this message",
        ),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB,
            nullable=True,
            comment="Snapshot of context used to produce this message (for debugging)",
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=True,
            comment="Token count for cost tracking",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # CHECK constraint for actor values
    op.execute(sa.text("""
        ALTER TABLE brain_messages
        ADD CONSTRAINT ck_brain_messages_actor
        CHECK (actor IN ('user', 'brain', 'hermes', 'system'));
    """))

    # Composite index for fetching messages in conversation order
    op.create_index(
        "ix_brain_messages_conversation_created",
        "brain_messages",
        ["conversation_id", "created_at"],
    )

    # Index on org_id for tenant-scoped queries
    op.create_index(
        "ix_brain_messages_org_id",
        "brain_messages",
        ["org_id"],
    )

    # =========================================================================
    # 5. Enable RLS on all 4 tables with tenant isolation policies
    # =========================================================================

    # --- brain_user_memory ---
    op.execute(sa.text(
        "ALTER TABLE brain_user_memory ENABLE ROW LEVEL SECURITY;"
    ))
    op.execute(sa.text("""
        CREATE POLICY "brain_user_memory_tenant_isolation"
        ON brain_user_memory
        FOR ALL
        USING (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ))
        WITH CHECK (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ));
    """))

    # --- brain_workspace_knowledge ---
    op.execute(sa.text(
        "ALTER TABLE brain_workspace_knowledge ENABLE ROW LEVEL SECURITY;"
    ))
    op.execute(sa.text("""
        CREATE POLICY "brain_workspace_knowledge_tenant_isolation"
        ON brain_workspace_knowledge
        FOR ALL
        USING (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ))
        WITH CHECK (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ));
    """))

    # --- brain_conversations ---
    op.execute(sa.text(
        "ALTER TABLE brain_conversations ENABLE ROW LEVEL SECURITY;"
    ))
    op.execute(sa.text("""
        CREATE POLICY "brain_conversations_tenant_isolation"
        ON brain_conversations
        FOR ALL
        USING (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ))
        WITH CHECK (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ));
    """))

    # --- brain_messages ---
    op.execute(sa.text(
        "ALTER TABLE brain_messages ENABLE ROW LEVEL SECURITY;"
    ))
    op.execute(sa.text("""
        CREATE POLICY "brain_messages_tenant_isolation"
        ON brain_messages
        FOR ALL
        USING (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ))
        WITH CHECK (org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
        ));
    """))


def downgrade() -> None:
    """Drop brain memory 4-layer tables and RLS policies."""
    # Drop RLS policies
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "brain_messages_tenant_isolation" ON brain_messages;'
    ))
    op.execute(sa.text(
        "ALTER TABLE brain_messages DISABLE ROW LEVEL SECURITY;"
    ))

    op.execute(sa.text(
        'DROP POLICY IF EXISTS "brain_conversations_tenant_isolation"'
        " ON brain_conversations;"
    ))
    op.execute(sa.text(
        "ALTER TABLE brain_conversations DISABLE ROW LEVEL SECURITY;"
    ))

    op.execute(sa.text(
        'DROP POLICY IF EXISTS "brain_workspace_knowledge_tenant_isolation"'
        " ON brain_workspace_knowledge;"
    ))
    op.execute(sa.text(
        "ALTER TABLE brain_workspace_knowledge DISABLE ROW LEVEL SECURITY;"
    ))

    op.execute(sa.text(
        'DROP POLICY IF EXISTS "brain_user_memory_tenant_isolation"'
        " ON brain_user_memory;"
    ))
    op.execute(sa.text(
        "ALTER TABLE brain_user_memory DISABLE ROW LEVEL SECURITY;"
    ))

    # Drop brain_messages
    op.drop_index("ix_brain_messages_org_id", table_name="brain_messages")
    op.drop_index(
        "ix_brain_messages_conversation_created", table_name="brain_messages"
    )
    op.drop_table("brain_messages")

    # Drop brain_conversations
    op.drop_index(
        "ix_brain_conversations_org_user_created",
        table_name="brain_conversations",
    )
    op.drop_table("brain_conversations")

    # Drop brain_workspace_knowledge
    op.drop_index(
        "ix_brain_workspace_knowledge_org_id",
        table_name="brain_workspace_knowledge",
    )
    op.drop_table("brain_workspace_knowledge")

    # Drop brain_user_memory
    op.drop_index(
        "ix_brain_user_memory_org_id", table_name="brain_user_memory"
    )
    op.drop_index(
        "ix_brain_user_memory_org_user", table_name="brain_user_memory"
    )
    op.drop_table("brain_user_memory")
