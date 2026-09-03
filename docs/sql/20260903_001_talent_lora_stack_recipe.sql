-- Migration: Add character LoRA stack recipe to talent
-- Run in: Supabase Dashboard > SQL Editor
-- Date: 2026-09-03
-- Purpose: store the dialed-in "character stack recipe" per talent so the
-- talent page can save/reuse it (character LoRA @ weight + NSFW LoRA @ weight
-- + locked appearance tags). See wan-video-prompting skill →
-- references/lora-stacking-hygiene.md for the six-move stacking playbook.

ALTER TABLE talent ADD COLUMN IF NOT EXISTS lora_stack_recipe JSONB DEFAULT NULL;

-- Example shape (what the talent page writes):
-- {
--   "character_lora": {
--     "file": "melissa_char_v2.safetensors",
--     "weight": 0.9,
--     "trigger": "melissachar"
--   },
--   "nsfw_loras": [
--     { "file": "krea2_uncut_penis_coachbate_v1.safetensors", "weight": 0.6, "trigger": "krea2uncut" }
--   ],
--   "locked_appearance_tags": [
--     "deep brown skin", "black hair", "dark brown eyes", "athletic build"
--   ],
--   "notes": "Delete 1girl. Appearance tags from HER, action tags from NSFW LoRA."
-- }
