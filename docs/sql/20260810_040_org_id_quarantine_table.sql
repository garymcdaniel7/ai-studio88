-- =============================================================================
-- Migration 040: Create _org_id_quarantine table
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: Track NULL org_id rows before backfill per R69 quarantine process.
-- Provides a structured audit trail of how ownership was resolved for every
-- ambiguous row during the NULL → NOT NULL transition.
--
-- REQUIREMENTS: R69.1, R69.2, R69.5, R5.6, R2.1
--
-- CATEGORY: Platform-operational (Category C) — no org_id on this table.
--
-- SAFETY: Additive migration. No destructive changes.
-- ROLLBACK: DROP TABLE IF EXISTS _org_id_quarantine;
-- =============================================================================

BEGIN;

-- =============================================================================
-- Create the quarantine tracking table
-- =============================================================================

CREATE TABLE IF NOT EXISTS _org_id_quarantine (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    table_name TEXT NOT NULL,
    row_id UUID NOT NULL,

    -- Quarantine reason and timing
    reason TEXT NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Resolution tracking
    resolved_at TIMESTAMPTZ,
    resolution TEXT CHECK (resolution IN ('assigned', 'purged', 'system_owned')),
    resolved_by UUID,                  -- Platform Operator user_id who resolved
    assigned_org_id UUID,              -- If resolution = 'assigned', which org

    -- Metadata
    row_snapshot JSONB,                -- Optional snapshot of the row at quarantine time
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes for efficient querying
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_org_id_quarantine_table_name
    ON _org_id_quarantine(table_name);

CREATE INDEX IF NOT EXISTS ix_org_id_quarantine_unresolved
    ON _org_id_quarantine(table_name, quarantined_at)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_org_id_quarantine_row
    ON _org_id_quarantine(table_name, row_id);

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE _org_id_quarantine IS
    'Tracks rows with NULL org_id during schema remediation (R69 quarantine process). '
    'Platform-operational table — no tenant dimension.';

COMMENT ON COLUMN _org_id_quarantine.reason IS
    'Why this row was quarantined (e.g., "NULL org_id — single-founder table", '
    '"NULL org_id — ambiguous ownership")';

COMMENT ON COLUMN _org_id_quarantine.resolution IS
    'How the row was resolved: assigned (to an org), purged (deleted), '
    'or system_owned (platform data, not tenant-scoped)';

COMMIT;
