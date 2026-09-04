# AIOS Studio Craft — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the in-app AIOS from a governance/chat control plane into a self-improving professional studio operator — with a persona ("soul"), a shared craft library that compounds across tenants, a recipe learning loop that moves generations toward near-perfect, and a local lip-sync execution layer (LatentSync) that nails voice-to-mouth alignment.

**Architecture:** Brain (app agent UI) → AIOS control plane (governance/policies + persona + memory) → Hermes planning → execution adapters (WAN2.2 + FLUX Klein 2 generation, LatentSync lip-sync, TTS voice profiles, mux). The AIOS already exists at `backend/aios/` (sessions, messages, decisions, approvals, policies; org-scoped tables). This plan ADDS persona/memory/craft/telemetry/sync — it does not rewrite the control plane.

**Tech Stack:** Python backend (existing), PostgreSQL (existing Supabase), LatentSync (ByteDance, open weights, self-hosted on existing Vast/RunPod GPU fleet), MuseTalk (optional fast-preview tier), Whisper-class alignment, existing TTS layer, existing ledger for cost tracking.

---

## Phase 1 — AIOS Soul (persona + memory)

**Objective:** Give the AIOS an identity and durable per-tenant memory so it behaves like a consistent line producer and remembers each studio's taste.

### Task 1: AIOS persona document
- Create: `backend/aios/persona.py` — loads `AIOS_SOUL.md` (new file, root `docs/` or `backend/aios/AIOS_SOUL.md`), injects into AIOS system prompt.
- Content: line-producer persona, voice, operating doctrine (matches house style: crisp, no fluff), bright-line guardrails already in governance policies.
- Test: unit test that persona injects and does not override tenant policy.
- Verify: `pytest tests/unit/test_core/test_aios_routes.py` passes.

### Task 2: Per-tenant memory tables
- Create migration: `aios_memory` (org_id, key, value JSONB, updated_at, RLS via org_id) — reuse existing tenant-isolation pattern from `docs/sql/20260804_006_aios_tenant_isolation.sql`.
- Test: tenant A cannot read tenant B memory (mirror `test_aios_isolation.py`).

### Task 3: Memory service
- Create: `backend/aios/memory.py` — CRUD + recall (top-k by recency), injected into AIOS context.
- Wire: AIOS prompt builder pulls persona + recent memory + policies.

## Phase 2 — Shared craft + recipe learning loop

**Objective:** Generations improve across users via a global craft library (knowledge, not user data) and a telemetry loop that mines winning recipes.

### Task 4: Generation telemetry tables
- Create migration: `generation_events` (org_id, model, prompt_hash, params JSONB, seed, duration_ms, cost_usd, status) + `recipe_ratings` (generation_event_id, rating 1-5, user note).
- Hook: generation adapter writes a row on every completion (ledger already exists — reuse cost values).

### Task 5: Craft library
- Create: `backend/aios/craft.py` + table `craft_recipes` (id, global BOOL, org_id NULLABLE, model, category, recipe JSONB, rating_avg, uses).
- Global recipes (global=TRUE) are shared across ALL tenants — "how", never "who". No talent LoRAs, no voice profiles, no user content. Per-tenant recipes stay org-scoped.

### Task 6: Mining job
- Create: `backend/aios/miner.py` — cron/manual job: top-rated recent generations → distill into craft_recipes (prompt template + params + seed pattern). P0: a simple "top recipe by rating" query + promote-to-global review queue (approvals table reuse).

## Phase 3 — Lip-sync execution layer

**Objective:** Voice and mouth move together, at frame accuracy, running local on the GPU fleet.

### Task 7: Sync engine selection
- Primary: **LatentSync** (ByteDance) — best open lip-sync quality, Whisper-aligned, any TTS, single-GPU.
- Fast tier: **MuseTalk** — real-time previews/dailies only.
- Worker: containerized on existing Vast/RunPod fleet (B2 artifact pattern already in place).

### Task 8: Sync adapter
- Create: `backend/aios/adapters/lipsync.py` — input video + audio → LatentSync (or MuseTalk per shot type) → aligned video; returns artifact URL + timing report.
- Shot-type policy: close-up = LatentSync; wide/behind = skip or light pass (learned craft move).
- Voice profiles: `voice_profiles` table (org_id, character, TTS embedding ref, sample ref) so the same talent sounds identical across takes.

### Task 9: Pipeline wiring
- AIOS decision flow: script → cast → TTS → WAN2.2/Klein gen → lipsync → mux → compliance (existing quarantine/C2PA) → deliver.
- Test: end-to-end happy path with a 5s fixture; assert mouth-sync timing report exists and artifact plays.

## Phase 4 — (Later) Curated fine-tunes

**Objective:** After the telemetry loop has data, train targeted LoRAs on top-rated output. Explicitly NOT in this build; needs founder-play session + data volume first.

---

## Files likely to change
- `backend/aios/` (persona.py, memory.py, craft.py, miner.py, adapters/lipsync.py)
- Alembic migrations (aios_memory, generation_events, recipe_ratings, craft_recipes, voice_profiles)
- Generation adapter (write telemetry rows)
- GPU worker fleet config (LatentSync/MuseTalk containers)

## Validation
- Backend unit tests green (existing suite + new coverage for isolation, telemetry, craft scoping).
- Frontend unaffected — this is backend/worker work.
- Lip-sync smoke test on one Vast/RunPod worker: 5s clip, timing report, artifact URL.

## Risks / tradeoffs
- LatentSync quality ceiling: teeth/side-profile artifacts on extreme angles → mitigated by shot-type policy (cut away = learned move).
- Telemetry loop needs rating volume to be useful → start with founder-play sessions + early users; mining job is the seed.
- Craft sharing must never leak tenant identity — global recipes are recipe-only, enforced by test.
- ox-alpha (stealth/ox-alpha via nous) is unreliable as a model choice — do not reference it in docs.

## Open questions
- Voice cloning stack: which TTS layer (OpenAI TTS vs open clone) for voice_profiles — defer to founder-play session.
- Global craft promotion: manual approval vs auto after N high ratings — default manual (approvals table).
