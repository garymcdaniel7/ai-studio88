-- Ghost Table Migration: performance_memory
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.

CREATE TABLE IF NOT EXISTS public.performance_memory (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    universe_id UUID,
    character_id UUID,
    episode_id UUID,
    scene_id UUID,
    shot_id UUID,
    emotion TEXT,
    energy_level TEXT,
    body_position TEXT,
    facing_direction TEXT,
    wardrobe TEXT,
    props_held JSONB DEFAULT '[]'::jsonb,
    location TEXT,
    time_of_day TEXT,
    weather TEXT,
    dialogue_state TEXT,
    voice_emotion TEXT,
    movement_direction TEXT,
    eyeline TEXT,
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT performance_memory_pkey PRIMARY KEY (id)
);

-- Indexes matching live DB
CREATE INDEX IF NOT EXISTS ix_perf_memory_character ON public.performance_memory USING btree (character_id);
CREATE INDEX IF NOT EXISTS ix_perf_memory_episode ON public.performance_memory USING btree (episode_id);
CREATE INDEX IF NOT EXISTS ix_perf_memory_scene ON public.performance_memory USING btree (scene_id);
