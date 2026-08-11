-- Ghost Table Migration: campaigns
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.
-- This is the canonical name; migration 017 defines "brand_campaigns" which was never deployed.

CREATE TABLE IF NOT EXISTS public.campaigns (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID,
    brand_id UUID,
    name TEXT NOT NULL,
    campaign_type TEXT,
    objective TEXT,
    target_platforms TEXT[],
    status TEXT DEFAULT 'planning'::text,
    start_date DATE,
    end_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT campaigns_pkey PRIMARY KEY (id)
);
