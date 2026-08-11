-- =============================================================================
-- Migration: Create _quarantine_log table
--
-- PURPOSE: Track quarantined rows with NULL or ambiguous org_id during
-- schema remediation. Implements R69 quarantine process.
--
-- REQUIREMENTS: R69.1, R69.2, R69.3, R69.4, R69.5, R69.6, R5.6
--
-- The _quarantine_log table provides Platform Operator tooling to review
-- quarantined records and either:
--   - Assign them to the correct org (with evidence)
--   - Classify them as system-owned
--   - Approve them for permanent deletion
--
-- SAFETY: Additive migration. No destructive changes.
-- ROLLBACK: DROP TABLE IF EXISTS _quarantine_log;
-- =============================================================================

BEGIN;

-- =============================================================================
-- Create the _quarantine_log table
-- =============================================================================

CREATE TABLE IF NOT EXISTS _quarantine_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    source_table TEXT NOT NULL,
    source_row_id UUID NOT NULL,

    -- Classification per R69.1
    classification TEXT NOT NULL DEFAULT 'QUARANTINED_FOR_REVIEW'
        CHECK (classification IN (
            'QUARANTINED_FOR_REVIEW',
            'ELIGIBLE_FOR_APPROVED_PURGE',
            'RESOLVED_ASSIGNED',
            'RESOLVED_SYSTEM_OWNED',
            'RESOLVED_PURGED'
        )),

    -- Quarantine metadata
    quarantine_reason TEXT NOT NULL,
    quarantine_date TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Resolution metadata (populated when resolved)
    resolved_at TIMESTAMPTZ,
    resolution TEXT CHECK (resolution IN ('assigned', 'system', 'purged')),
    resolved_by UUID,           -- actor who resolved (Platform Operator user_id)
    resolution_evidence TEXT,   -- evidence/justification for resolution decision
    assigned_org_id UUID,       -- if resolution = 'assigned', which org it was assigned to

    -- Audit trail
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS ix_quarantine_log_source_table
    ON _quarantine_log(source_table);

CREATE INDEX IF NOT EXISTS ix_quarantine_log_classification
    ON _quarantine_log(classification);

CREATE INDEX IF NOT EXISTS ix_quarantine_log_source_row
    ON _quarantine_log(source_table, source_row_id);

CREATE INDEX IF NOT EXISTS ix_quarantine_log_unresolved
    ON _quarantine_log(classification)
    WHERE resolved_at IS NULL;

-- =============================================================================
-- Comments for documentation
-- =============================================================================

COMMENT ON TABLE _quarantine_log IS
    'Tracks quarantined rows with NULL/ambiguous org_id during schema remediation (R69)';

COMMENT ON COLUMN _quarantine_log.classification IS
    'R69.1 classification: QUARANTINED_FOR_REVIEW, ELIGIBLE_FOR_APPROVED_PURGE, or RESOLVED_*';

COMMENT ON COLUMN _quarantine_log.quarantine_reason IS
    'Human-readable reason for quarantine (e.g., "NULL org_id", "references non-existent org")';

COMMENT ON COLUMN _quarantine_log.resolution IS
    'How the quarantined row was resolved: assigned to org, classified as system, or purged';

COMMIT;
