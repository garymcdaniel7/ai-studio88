# AIOS Studio Craft — Requirements

Turn the AIOS control plane into a self-improving professional studio operator. The AIOS already exists at `backend/aios/` with sessions, messages, decisions, approvals, policies (org-scoped tables). This spec ADDS four layers. Do NOT rewrite the control plane, do NOT touch `frontend/`, do NOT touch `backend/api_v1.py` without routing through the orchestrator.

## R1 — AIOS Persona ("soul")
- New file `backend/aios/persona.py` loads `AIOS_SOUL.md` (author: line-producer persona, studio operator voice, operating doctrine, no fluff) and injects it into the AIOS system prompt alongside governance policies.
- Persona must never override tenant policy; bright-line guardrails stay in governance.
- Unit test: persona injects; policy still wins on conflict.

## R2 — Per-tenant AIOS memory
- New migration: `aios_memory` (org_id, key, value JSONB, updated_at) with RLS scoping identical to the existing tenant-isolation pattern (`docs/sql/20260804_006_aios_tenant_isolation.sql`).
- New service `backend/aios/memory.py`: CRUD + recall (top-k by recency), injected into the AIOS prompt builder.
- Isolation test: tenant A cannot read/write tenant B memory (mirror `tests/unit/test_core/test_aios_isolation.py`).

## R3 — Generation telemetry
- New migration: `generation_events` (org_id, model, prompt_hash, params JSONB, seed, duration_ms, cost_usd, status, created_at) and `recipe_ratings` (generation_event_id FK, rating 1-5, note, created_at).
- The generation adapter writes a row per completed generation; reuse existing ledger cost values. No new auth surface.

## R4 — Shared craft library
- New migration: `craft_recipes` (id, global BOOL, org_id NULLABLE, model, category, recipe JSONB, rating_avg, uses, created_at).
- Global recipes (global=TRUE, org_id NULL) are visible to ALL tenants; per-tenant recipes org-scoped.
- Rule: global recipes contain ONLY craft ("how") — prompt templates, params, seed patterns, camera moves. NEVER talent LoRAs, voice profiles, or any tenant identity/IP. Enforce with a validation test.

## R5 — Recipe mining
- New job `backend/aios/miner.py`: query top-rated recent generations → distill into `craft_recipes` drafts → promote-to-global via existing approvals queue (manual review default).
- Manual script + cron entry; no auto-promotion in v1.

## R6 — Lip-sync execution layer
- New worker adapter `backend/aios/adapters/lipsync.py`: input (video artifact URL + audio artifact URL) → LatentSync (primary) or MuseTalk (fast tier) → aligned video artifact + timing report JSON (frame offsets, confidence).
- Runs on the existing GPU fleet (Vast/RunPod, B2 artifact pattern). No third-party sync API — local-first.
- Shot-type policy: close-up = LatentSync; wide/behind = light pass or skip (configurable).

## R7 — Voice profiles
- New migration: `voice_profiles` (org_id, character, tts_ref JSONB, sample_ref, created_at) so a talent sounds identical across takes.
- Adapter reads profile when provided.

## R8 — Pipeline wiring (decision flow)
- AIOS decision flow: script → cast → TTS → WAN2.2/Klein generation → lipsync → mux → compliance (existing quarantine/C2PA) → deliver.
- Add a dry-run mode that returns the planned stages without executing (for founder-play testing).

## R9 — Tests
- Full backend unit suite green (existing + new coverage: isolation, telemetry write, craft scoping, persona/policy precedence, miner distillation).
- One lip-sync smoke test: 5s fixture clip + audio → timing report + artifact URL.

## R10 — Non-goals
- No frontend changes. No rewrite of `backend/aios/` core. No fine-tunes yet. No auto-promotion of global recipes. No voice cloning training in this phase (profile table only).
