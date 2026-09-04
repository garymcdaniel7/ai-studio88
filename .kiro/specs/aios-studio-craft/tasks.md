# AIOS Studio Craft — Tasks

Work in small commits. Read `.kiro/specs/aios-studio-craft/requirements.md` first. Backend-only; never touch `frontend/`; route any `backend/api_v1.py` changes through the orchestrator.

## P0 — Persona + memory foundation
- [ ] R1: Write `backend/aios/AIOS_SOUL.md` (line-producer persona, studio-operator voice, operating doctrine) + `backend/aios/persona.py` loader/injector.
- [ ] R1: Unit test — persona injects into prompt builder; policy still wins on conflict.
- [ ] R2: Alembic migration — `aios_memory` table with org_id + RLS (reuse tenant-isolation pattern).
- [ ] R2: `backend/aios/memory.py` — CRUD + top-k recall; wire into AIOS prompt builder.
- [ ] R2: Isolation test — tenant A cannot read/write tenant B memory.

## P1 — Telemetry + craft library
- [ ] R3: Alembic migration — `generation_events` + `recipe_ratings` tables.
- [ ] R3: Generation adapter writes telemetry row on completion (reuse ledger cost values).
- [ ] R4: Alembic migration — `craft_recipes` (global flag, org_id nullable, recipe JSONB).
- [ ] R4: `backend/aios/craft.py` — CRUD + validation: global recipes must NOT contain talent/voice/tenant identity fields.
- [ ] R4: Craft scoping test — global visible to all tenants; per-tenant org-scoped; validation rejects identity-bearing global recipe.
- [ ] R5: `backend/aios/miner.py` — top-rated generations → recipe drafts → approvals queue (manual promote).
- [ ] R5: Miner test — distill picks highest-rated, drops unrated/low-rated.

## P2 — Lip-sync layer + voice profiles
- [ ] R6: `backend/aios/adapters/lipsync.py` — LatentSync primary path (input artifacts → output artifact + timing report).
- [ ] R6: MuseTalk fast-tier path + shot-type policy (close-up vs wide/behind).
- [ ] R6: Worker container for the GPU fleet; B2 artifact upload.
- [ ] R7: Alembic migration — `voice_profiles` table; adapter reads profile when present.
- [ ] R8: Pipeline wiring — decision flow includes lipsync stage; dry-run mode returns planned stages without executing.
- [ ] R9: Lip-sync smoke test — 5s fixture + audio → timing report + artifact URL.
- [ ] R9: Full backend suite green.

## Verification
- [ ] `pytest` (backend) — full suite green, including new isolation/scoping tests.
- [ ] Alembic `upgrade head` against hosted Supabase (use pooler URL; stamp existing revisions, run only missing DDL).
- [ ] Report: files changed, exact test command + results, smoke-test artifact URL, deliberate non-goals.
