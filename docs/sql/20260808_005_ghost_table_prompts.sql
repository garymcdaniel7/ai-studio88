-- Ghost Table Migration: prompts
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.
-- This is distinct from prompt_history (separate table).

CREATE TABLE IF NOT EXISTS public.prompts (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    character_id UUID,
    name TEXT,
    prompt TEXT,
    negative_prompt TEXT,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT prompts_pkey PRIMARY KEY (id)
);
