-- Ghost Table Migration: content_calendar
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.

CREATE TABLE IF NOT EXISTS public.content_calendar (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID,
    campaign_id UUID,
    talent_id UUID,
    platform TEXT,
    content_type TEXT,
    title TEXT,
    caption TEXT,
    scheduled_for TIMESTAMPTZ,
    status TEXT DEFAULT 'draft'::text,
    asset_ids JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT content_calendar_pkey PRIMARY KEY (id)
);
