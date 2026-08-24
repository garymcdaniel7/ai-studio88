"""Reconcile the jobs table to the live Supabase schema.

The live ``public.jobs`` table is the source of truth and already carries the
correct columns (``type``, ``attempts``, ``progress``, ``error``, ``input``,
``output``, ``worker_*``, ``project_id``, ``workflow_id``, ...). This migration
makes any database produced by the older model's Alembic chain match that live
schema:

  * renames drifted columns (guarded) so the ORM model's column names line up
  * adds any live columns that are missing (idempotent ``ADD COLUMN IF NOT
    EXISTS``)
  * drops model-only columns that do not exist in the live table (guarded)

It is intentionally additive/idempotent and never drops a live column.
"""

from __future__ import annotations

from alembic import op

revision: str = "20260830001"
down_revision: str | None = "20260829001"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

_RENAME = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jobs' AND column_name = '{old}'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jobs' AND column_name = '{new}'
    ) THEN
        ALTER TABLE jobs RENAME COLUMN "{old}" TO "{new}";
    END IF;
END $$;
"""

_ADD = "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col};"


def upgrade() -> None:
    # --- Rename drifted columns (guard: only when the old name exists) ---
    op.execute(_RENAME.format(old="job_type", new="type"))
    op.execute(_RENAME.format(old="attempt_count", new="attempts"))
    op.execute(_RENAME.format(old="progress_percent", new="progress"))
    op.execute(_RENAME.format(old="error_message", new="error"))
    op.execute(_RENAME.format(old="parameters", new="input"))
    op.execute(_RENAME.format(old="output_asset_ids", new="output"))

    # --- Ensure every live column is present (additive / idempotent) ---
    for col in (
        "type TEXT",
        "attempts INTEGER NOT NULL DEFAULT 0",
        "progress INTEGER",
        "error TEXT",
        "input JSONB",
        "output JSONB",
        "progress_metadata JSONB",
        "worker_id UUID",
        "worker_name TEXT",
        "project_id UUID",
        "workflow_id UUID",
        "workload_class TEXT",
        "priority INTEGER NOT NULL DEFAULT 0",
        "idempotency_key TEXT",
        "max_attempts INTEGER NOT NULL DEFAULT 3",
        "talent_id UUID",
        "started_at TIMESTAMPTZ",
        "completed_at TIMESTAMPTZ",
    ):
        op.execute(_ADD.format(col=col))

    # --- Drop model-only columns not present in the live table ---
    for col in ("user_id", "context_package_id", "cost_usd",
                "max_duration_seconds", "progress_message", "metadata"):
        op.execute(f"ALTER TABLE jobs DROP COLUMN IF EXISTS {col};")


def downgrade() -> None:
    """Reverse renames back to the legacy names (best-effort, guarded)."""
    op.execute(_RENAME.format(old="type", new="job_type"))
    op.execute(_RENAME.format(old="attempts", new="attempt_count"))
    op.execute(_RENAME.format(old="progress", new="progress_percent"))
    op.execute(_RENAME.format(old="error", new="error_message"))
    op.execute(_RENAME.format(old="input", new="parameters"))
    op.execute(_RENAME.format(old="output", new="output_asset_ids"))
