"""Add progress_metadata JSONB column to jobs table.

Supports optional structured progress reporting from workers per R21.13.
Workers may include arbitrary metadata (step counts, timing info, etc.)
alongside percent and message progress fields.

Revision ID: 20260810_002
Revises: 20260810_001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# Revision identifiers
revision = "20260810_002"
down_revision = "20260810_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add progress_metadata JSONB column to jobs table."""
    op.add_column(
        "jobs",
        sa.Column("progress_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove progress_metadata column from jobs table."""
    op.drop_column("jobs", "progress_metadata")
