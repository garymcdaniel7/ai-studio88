# GPU Asset Intelligence — Founder Brief (Assessment v1)

**Date:** 2026-08-30 · **Author:** Hermes · **Status:** ASSESSMENT (no implementation started)
**Scope:** Does AI Studio need, and can it support, an asset-placement/cache/prefetch
intelligence layer? Ground truth from repo inspection + live Supabase schema + live GPU workers.

---

## 1. CURRENT WORK (what was completed before this assessment)

### QA Evaluator course (completed this session)
- Built a QA harness that runs generation cases across all categories on the Thunder A6000,
  grades each output, tunes prompts/params until they pass, and records recipes.
- **Local uncensored VLM grader** (Ollama qwen2.5vl:3b) because the hosted vision model
  refuses NSFW frames (error 451, provider policy). Verified working.
- **Lessons learned (recorded in `ai-studio-qa-evaluator` skill):**
  - Anatomy is strong everywhere (8.5-9.8). Lighting is the weak point — "golden hour"
    causes yellow cast + glossy painterly skin. Fix: neutral balanced lighting + natural
    skin texture + film grain in prompt, plus negative "oversaturated/yellow tint/glossy".
  - Style LoRAs (anime/cartoon) need their **trigger words** at strength 1.0 or they output
    photorealistic content. Verified: anime adherence 0.5 → 8.2, cartoon 3.2 → 9.0.
  - CFG 3.5 is Wan 2.2 community consensus (committed to `comfyui_provider.py`).
- **Thunder Compute** = new persistent GPU home (A6000, $0.49/hr), full Remix NSFW 14B
  stack + 41 LoRAs + nsfw CLIP + VAE downloaded.
- **Snapshot `v1-baseline-remix-nsfw` READY** — the 43GB stack is now a bootable golden image
  for any number of future instances. This IS the persistence layer working as designed.

### Remaining / open
- BBW LoRA repo is gated (401) — blocked on user-provided access.
- Gay/male-male LoRAs not on HF (Civitai is red) — model itself may suffice with prompts.
- `backend/gpu.py` is an empty placeholder.
- `worker_registry`/`worker_state`/`worker_orchestrator`/`render_fleet` exist as code but
  the polling worker (`backend/worker.py`) does NOT call them — two parallel worker paths.

### Verification status
- Real end-to-end video generation proven on Thunder (Remix 14B, 49 frames, real content).
- QA grade card above is from actual frame-level VLM grading.
- Snapshot verified READY via `tnr snapshot list`.

### Safe transition point: **REACHED** ✅
Current work is stabilized (snapshot + committed config + recorded skill). The GPU Asset
Intelligence assessment below is the next phase.

---

## 2. INFRASTRUCTURE ASSESSMENT (repository reality)

### What already exists (significant — more than the proposal assumed)

| Capability | Where | State |
|---|---|---|
| **Models registry** | Supabase `models` table: id, name, type, family, version, provider, storage_path, local_path, required_vram_gb, status, supported_tasks, supported_resolutions, metadata, org_id | EXISTS (live) |
| **Assets registry** | Supabase `assets`: checksum, storage_key, storage_provider, public_url, size_bytes, mime_type, talent_id, project_id, tags | EXISTS (live) |
| **Job queue w/ priority + optimistic claim** | `jobs` table + `claim_next_job` (status queued→running CAS, priority desc, FIFO, org-scoped) | EXISTS (live, multi-worker safe) |
| **Job leases** | `job_leases` table (worker_identity, lease) | EXISTS |
| **Cost tracking** | `cost_reservations`, `cost_entries`, `cost_intelligence.py` | EXISTS |
| **Provider reputation / routing governance** | `provider_reputation.py`, `routing_governance.py` (reputation, suppression, evidence) | EXISTS (code) |
| **Worker orchestration** | `worker_orchestrator.py` (provision/terminate/health/idle-timeout/assign/release/blacklist), `render_fleet.py`, `auto_provisioner.py` (FLEET_* settings), `capacity_telemetry.py` | EXISTS (code) |
| **Worker state machine** | `worker_state.py` — DurableWorkerRecord with lifecycle, leases, heartbeats, `models_loaded` field | EXISTS (code, **models_loaded not wired to real worker**) |
| **Model cache (B2 + HF)** | `providers/vast/model_cache.py` — B2 two-tier cache, `MODEL_CACHE_*` env, KNOWN_MODELS dict, list_cached_models/list_known_models | EXISTS (code, wired to status dashboard/admin) |
| **B2 storage** | `storage.py` — upload/download/delete/signed URL, checksum | EXISTS (live, private bucket) |
| **LoRA lifecycle** | `lora_lifecycle.py` — trained→evaluating→review→approved→deployable→active (governance gate) | EXISTS |
| **Workflow registry** | `workflows/comfyui/*.json` + `video/registry.py`, `capability_selector.py` | EXISTS |

### Gaps (the honest gap analysis — VERIFIED by 3-agent codebase audit)

1. **Jobs don't carry dependency manifests.** `generate_video` enqueues `input` with a
   bare `model: "wan-2.1"` string — no LoRA list, no VAE, no checkpoint filenames, no
   workflow resolution. `jobs.workflow_id` column exists but nothing populates it.
   → Queue-lookahead prefetching is **impossible today** because the system cannot know
   what a queued job will need.
2. **No worker inventory reconciliation in the live path.** `worker_state.models_loaded`
   exists in schema but the real `worker.py` never calls it. The app-layer `workers`
   table tracks only `available_vram_gb`, `current_job_id`, `last_heartbeat_at` — no
   model/cached-asset inventory.
3. **TWO divergent claim implementations coexist.** Legacy `claim_next_job` (optimistic
   UPDATE guard, no leases) vs app-layer `job_repository.claim_next_job` (FOR UPDATE
   SKIP LOCKED + job_leases, heartbeat). The legacy worker uses the weaker one; no
   lease expiry/requeue in the legacy path.
4. **`generate_image` bypasses the queue entirely** — synchronous client call to a
   reachable worker, never a job row. Only video/lora go through jobs.
5. **Silent simulation fallback masks missing models.** `comfyui_provider` falls back to
   fake output when ComfyUI is unreachable — a missing checkpoint looks like a "successful"
   generation. Real reliability hazard.
6. **Three parallel worker models, no single source of truth** — orchestrator
   WorkerInstance (Supabase), registry WorkerInstance (in-memory), state
   DurableWorkerRecord (in-memory). They never synchronize; auto-provisioner launches
   are fire-and-forget (never registered back).
7. **No live B2↔Supabase reconciliation.** Bytes → B2 and rows → Supabase are written
   independently; the ORPHANED/UPLOAD_PENDING/UPLOAD_FAILED reconciliation logic exists
   only in archived `_archive/asset_registration.py`.
8. **Latent bug:** `aios/orchestration/model_lifecycle.py:141` imports `get_public_url`
   from `backend.storage`, which doesn't define it — import error at call time.
9. **`gpu.py` is empty** — the intended GPU abstraction was never written.

### IMPORTANT CORRECTION vs v1 draft
- A **cache-value/eviction model already exists** for models: `aios/orchestration/
  model_lifecycle.py` implements ModelState B2_ONLY/CACHED/LOADED/ARCHIVED,
  ensure/unload/archive/restore, and `recommend_eviction()` (LRU weighted by
  recency/size/use-count) — already wired into aios/gateway.py and autoscaler.py.
  It is VRAM-model placement only, but it is the **direct precedent to extend**,
  not rebuild.
- **`app/providers/storage.py` is the canonical storage abstraction** (StorageResult/
  ObjectInfo carry key + checksum_sha256; MediaAccessDescriptor) — prefer it over
  raw `backend/storage.py` for new cache work.
- **`app/models/asset.py` + `asset_service.py`** is an existing asset registry
  (storage_key + checksum_sha256 + storage_provider) — extend with canonical_uri/
  version/cache-tier, don't create a new table.
- **`app/models/dataset_manifest.py`** (immutable versioned manifest + sha256 +
  verify-before-run) is the download-integrity pattern to reuse.

### Thunder Compute considerations
- Persistence = **snapshots** (golden images). Unlike Vast, instances don't die randomly,
  but they're still per-instance; the snapshot IS the shared warm-cache primitive.
- A6000 48GB is the sweet spot for the 14B fp8 stack. Worker heartbeat/inventory reporting
  is on us to add (the box exposes ComfyUI `/object_info` — a free model inventory source).
- Prefetch overlap is genuinely valuable here: a 14GB model download (~5 min) should run
  while the previous job renders, not block the next job.

### B2 considerations
- B2 is private; signed URLs work with **path-style addressing** only (verified earlier).
- B2 as canonical model store is viable: it's cheap ($0.005/GB/mo), durable, and the model
  cache already keys by `models/<type>/<filename>`. But it is NOT currently the enforced
  source of truth — KNOWN_MODELS is a hardcoded dict, not DB-driven.

---

## 3. RECOMMENDATION

### BUILD NOW — unify claims + wire inventory + queue-lookahead core
The single highest-value, lowest-risk increments, in dependency order:
1. **Fix the two divergent claim paths** — make the legacy worker use the app-layer
   FOR UPDATE SKIP LOCKED + job_leases claim (or add lease expiry/requeue to the legacy
   path). Without this, any multi-worker logic is built on sand.
2. **Dependency manifests** — make every job declare its exact asset dependencies at
   enqueue time (`asset_dependencies = {models, loras, vae, controlnets, workflow_id}`),
   populated from the `models` table resolution.
3. **Worker inventory reporting** — wire the real worker to report `models_loaded` from
   ComfyUI `/object_info` into the `workers` table / DurableWorkerRecord.
4. **Queue-lookahead prefetcher** — while a worker renders, inspect upcoming queued jobs,
   diff required assets against that worker's inventory, download missing ones in the
   background (throttled, checksum-verified).

This is the "GPU compute and asset preparation overlap" goal, reuses `model_cache.py`,
`model_lifecycle.py` (extend its ModelState/recommend_eviction to disk assets), and the
existing `models`/`assets` registries. It needs no scheduler rewrite.

### BUILD LATER — readiness-aware scheduling + cache policy
- Weight `claim` by cache coverage + worker readiness + cost + provider reputation once
  inventory is trustworthy. Extend `model_lifecycle.recommend_eviction` (already LRU +
  recency/size/use-count) from VRAM to general worker-disk assets; add warm/cold flags.
- Prefer `app/providers/storage.py` + `app/models/asset.py` over raw `backend/storage.py`;
  add canonical_uri/version/cache-tier to the existing asset registry (do NOT create a new
  table). Reuse `app/models/dataset_manifest.py` for download integrity.

### DO NOT BUILD (yet) — full distributed cache + demand forecasting + provider failover matrix
The "think bigger" list is real infrastructure AI Studio doesn't yet have the job volume to
justify, and it duplicates what B2 + Thunder snapshots already provide cheaply. Revisit when
the fleet is multi-provider with real concurrent demand.

### Do NOT duplicate
- Do not build a new asset registry — extend existing `models`/`assets`/`asset_service`.
- Do not build a new scheduler — unify on the app-layer `job_repository` claim path.
- Do not build a new downloader — reuse `model_cache.py`.
- Do not rebuild model placement/eviction — extend `aios/orchestration/model_lifecycle.py`.

### The boundary that matters
- **Workflow Intelligence** (future): decides WHAT should run (model + LoRA + controlnet + VAE).
- **Infrastructure Intelligence** (this): decides WHERE/WHEN/HOW it runs reliably.
Keep them separate. The dependency manifest is the contract between them: Workflow
Intelligence emits `{model, loras[], vae, controlnets[], workflow_id}`, Infrastructure
Intelligence consumes it.

---

## 4. IMPLEMENTATION PLAN (phases, dependency order)

### Phase 1 — Dependency manifests (foundation, ~1-2 days)
- Extend `jobs.input` schema contract: `asset_dependencies = {models:[], loras:[], vae:[],
  controlnets:[], workflow_id, versions[]}`.
- Populate from `generate_video`/`generate_image` enqueue paths (resolve model name → models
  table → filenames via `get_known_model` / `models` table).
- Add a lightweight `job_assets` table or JSONB `asset_deps` column (reuse `jobs.input` first,
  avoid schema churn).

### Phase 2 — Worker inventory reporting (foundation, ~1-2 days)
- Add `worker_heartbeat(..., models_loaded=...)` call in `backend/worker.py` loop.
- Inventory source: scan ComfyUI `/object_info` loader lists on the box (free, accurate).
- Persist to `worker_state` DurableWorkerRecord; expose via infra status endpoint.

### Phase 3 — Queue-lookahead prefetcher (core value, ~2-3 days)
- New `backend/infrastructure/asset_prefetcher.py`: on each poll, read next N queued jobs
  (adaptive N by queue depth), resolve dependency manifests, diff against worker inventory,
  download missing to the worker via `model_cache.download_from_cache` / HF fallback.
- Concurrency guard: pause/throttle when a job is actively rendering (GPU/network/disk
  contention); primary generation wins.
- Integrity: checksum verify after download (`assets.checksum` / sha256); on mismatch
  re-download once then fail-safe (report, don't silently substitute).

### Phase 4 — Readiness-aware claiming (leverage, ~1-2 days)
- Extend `claim_next_job` (or add `claim_best_job`) to weight: cache coverage of the job's
  manifest, worker idle/ready state, cost, reliability (provider reputation).
- Keep fallback to current naive path when signals are absent (never break the worker).

### Phase 5 — Cache-value policy + warm/cold flags (~2-3 days)
- Add `last_used_at`, `usage_count`, `warm` to `models` registry (columns exist-ish; extend).
- Document eviction policy; implement explicit KEEP/PREFETCH/EVICT decisions as a Hermes
  planning step (not automatic deletion — the hard rule: never delete canonical B2 copy).

### Phase 6 — Reliability & recovery pass (~1-2 days)
- Partial/corrupt downloads, interrupted transfers, provider outage, full disk, version
  mismatch, duplicate concurrent downloads (dedupe by asset_id+worker), B2 outage fallback.
- All the failure cases from the brief, each with detect + recover + report.

### Verification gates per phase
- Phase 1: enqueue a job with a manifest, assert the DB row carries resolved filenames.
- Phase 2: worker heartbeat shows real `/object_info` inventory.
- Phase 3: enqueue 2 jobs where #2 needs a model #1 doesn't; assert the download starts
  DURING #1's render (the "overlap" test), throttled, and #2 starts warm.
- Phase 4: two workers with different caches; assert #2's job lands on the warm worker.
- Phase 5/6: policy doc + failure-injection table.

---

## 5. RISKS & DEPENDENCIES

- **No worker-inventory trust today** — Phase 2 must precede any cache-based scheduling.
- **Asset manifests require API/MCP changes** (enqueue paths) — needs the app side to emit them.
- **Thunder snapshots vs B2** — snapshot is the instance-boot primitive; B2 remains canonical.
  Keep them complementary, not competing.
- **Cost** — prefetch adds download traffic but saves GPU-idle time; net positive at $0.49/hr.
- **Security/tenancy** — org_id scoping already in models/assets/jobs; keep it. No talent or
  identity-specific behavior in any logic (per directive — generic, tenant-safe only).
- **The two-worker-path problem** (`worker.py` vs `WorkerOrchestrator`) must be resolved or
  explicitly bridged; do not maintain two divergent schedulers.

---

## 6. DECISION REQUESTED

Recommendation: **proceed with Phases 1-3 as BUILD NOW** (dependency manifests → inventory
reporting → queue-lookahead prefetcher), then reassess Phases 4-6 against real queue demand.

Confirm:
1. Proceed with Phase 1+2 (manifests + inventory) first?
2. Is `jobs.input` JSONB extension acceptable, or do you want a dedicated `job_assets` table?
3. Budget guardrail for prefetch bandwidth (e.g., cap concurrent downloads at 1-2 while rendering)?
