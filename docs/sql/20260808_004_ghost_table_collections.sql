-- Ghost Table Migration: collections
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.
-- This is distinct from brain_collections (which has org_id).

CREATE TABLE IF NOT EXISTS public.collections (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID,
    name TEXT NOT NULL,
    collection_type TEXT,
    storage_path TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT collections_pkey PRIMARY KEY (id)
);
