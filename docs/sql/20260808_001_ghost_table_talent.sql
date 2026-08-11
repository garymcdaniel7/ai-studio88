-- Ghost Table Migration: talent
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.

CREATE TABLE IF NOT EXISTS public.talent (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID,
    name TEXT NOT NULL,
    bio TEXT,
    default_style TEXT,
    trigger_words TEXT,
    main_lora_asset_id UUID,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'active'::text,
    gender TEXT,
    age INTEGER,
    ethnicity TEXT,
    instagram_handle TEXT,
    tiktok_handle TEXT,
    youtube_handle TEXT,
    x_handle TEXT,
    profile_image TEXT,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT now(),
    avatar_url TEXT,
    height TEXT,
    hair_color TEXT,
    eye_color TEXT,
    body_type TEXT,
    negative_prompt TEXT,
    visual_style TEXT,
    best_for TEXT,
    persona TEXT,
    creative_dna JSONB,

    CONSTRAINT characters_pkey PRIMARY KEY (id)
);

-- Note: The PK constraint is named "characters_pkey" in the live DB
-- (table was likely renamed from "characters" to "talent" at some point)
