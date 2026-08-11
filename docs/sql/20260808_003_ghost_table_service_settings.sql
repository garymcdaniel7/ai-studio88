-- Ghost Table Migration: service_settings
-- Documents existing live schema (table created ad-hoc, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: This is a platform-wide config table (2 rows in live DB).
-- No org_id needed — classified as REUSE in SCHEMA_RECONCILIATION.md.

CREATE TABLE IF NOT EXISTS public.service_settings (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    service_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    source TEXT DEFAULT 'unknown'::text,
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT service_settings_pkey PRIMARY KEY (id),
    CONSTRAINT service_settings_service_name_key UNIQUE (service_name)
);
