---
inclusion: always
---

# Project Status (auto-loaded in every session)

## Quick Facts

- **Repo:** `garymcdaniel7/ai-studio88` on GitHub
- **Local path:** `/Users/garymcdaniel/kiro/ai-studio88`
- **Start command:** `./start.sh` (launches Ollama + Backend + Frontend)
- **Backend:** `uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend:** `cd frontend && npm run dev` (Next.js on port 3000)
- **Ollama:** `ollama serve` (port 11434, model: llama3.1:8b)
- **Python:** 3.12.13 in `.venv/` (managed by uv at `~/.local/bin/uv`)
- **Node:** v26.4.0 (Next.js 16 + Tailwind + shadcn/ui)
- **Database:** Supabase (PostgreSQL) at vipmjgglascthwoqqqji.supabase.co
- **Storage:** Backblaze B2 (bucket: ai-studio88, region: us-east-005)
- **GPU:** Vast.ai ($22.72 balance, SSH key: ~/.ssh/id_ed25519)
- **LLM:** Ollama llama3.1:8b (local), with OpenAI/Anthropic fallback
- **Generation:** ComfyUI on Vast.ai GPU workers (SDXL Turbo, Flux Dev proven)
- **Status:** Phase 13 complete. Frontend scaffolded. Defects being resolved.

## Architecture (current)

```
backend/                         ← FastAPI (port 8000)
  main.py                        ← Entry point (15 routers mounted)
  api_v1.py                      ← Core API (310+ endpoints)
  database.py                    ← Supabase query functions
  storage.py                     ← Backblaze B2 upload/delete
  providers/vast/                ← Vast.ai client + model cache + remote seeder
  infrastructure/                ← Phase 13: orchestrator, race, reputation, cost, fleet, dashboard, generate
  engine/                        ← Generation Engine (simulation + ComfyUI + workflow selector)
  brain/                         ← AI Brain (planner, memory, modules, LLM provider)
  training/                      ← LoRA (simulation + Vast.ai provider)
  video/                         ← Video (simulation + ComfyUI WAN 2.1 provider)
  audio/                         ← Voice (simulation + ElevenLabs) + Music (simulation + Suno)
  publishing/                    ← Social publishing (simulation + webhook provider)
  object_intelligence/           ← Object DNA, Product DNA, Digital Twins, Scene Composer
  asset_intelligence/            ← Visual DNA, wardrobes, collections, relationships
  ...12 more packages

frontend/                        ← Next.js 16 (port 3000)
  src/app/                       ← 10 pages: Home, Brain, Create, Talent, Assets, Story, Production, Publish, Analytics, Admin
  src/components/                ← Sidebar, Topbar, UI components (shadcn)
  src/lib/api.ts                 ← Centralized API client

workflows/comfyui/               ← ComfyUI workflow templates
  sdxl_turbo.json                ← SDXL Turbo (1 step, 512x512)
  sd15_standard.json             ← SD 1.5 (20 steps, 512x512)
  flux_dev.json                  ← Flux Dev (UNETLoader + DualCLIP + T5)
  wan21_t2v_simple.json          ← WAN 2.1 text-to-video
  wan21_t2v_native.json          ← WAN 2.1 native nodes
  wan21_i2v_simple.json          ← WAN 2.1 image-to-video
  wan21_i2v_native.json          ← WAN 2.1 I2V native

scripts/vast/                    ← Vast.ai automation
  check_vast_auth.py
  list_offers.py
  launch_comfy_worker.py
  check_comfy_health.py
  stop_vast_worker.py
  register_worker.py
  bootstrap_comfyui.sh
  upload_model.py
  download_model.py
  seed_cache_remote.py
```

## Routers Mounted in main.py (15 total)

1. `api_v1` — Core endpoints (jobs, assets, talent, models, workers, generation, workflows)
2. `creator_os` — Campaigns, calendar, brands, teams
3. `autonomous_studio` — 19 AI departments, briefing
4. `training` — LoRA training lifecycle
5. `video` — Video production pipeline
6. `audio` — Voice (ElevenLabs) + Music (Suno)
7. `performance` — Performance engine
8. `publishing` — Social publishing + webhooks
9. `brain` — AI Brain (chat, planning, memory, LLM)
10. `production_intelligence` — Production analytics
11. `asset_intelligence` — Visual DNA, collections
12. `cinematic` — Cinematic studio
13. `company` — Company OS, multi-brand
14. `object_intelligence` — Object DNA, Product DNA, Digital Twins
15. `infrastructure` — Worker orchestration, connection race, fleet, cost, reputation, generate
16. `generate` — Direct ComfyUI generation endpoint

## Key Infrastructure (Phase 13)

| System | Module | Status |
|--------|--------|--------|
| Worker Orchestrator | `backend/infrastructure/worker_orchestrator.py` | ✅ Connection Race Mode |
| Provider Reputation | `backend/infrastructure/provider_reputation.py` | ✅ Learning engine |
| Cost Intelligence | `backend/infrastructure/cost_intelligence.py` | ✅ Budget tracking |
| Render Fleet | `backend/infrastructure/render_fleet.py` | ✅ Multi-worker |
| Status Dashboard | `backend/infrastructure/status_dashboard.py` | ✅ Aggregated status |
| Admin Settings | `backend/infrastructure/admin_settings.py` | ✅ Service connections |
| Direct Generate | `backend/infrastructure/generate.py` | ✅ ComfyUI workflow submit |

## Service Connections (verified)

| Service | Status | Notes |
|---------|--------|-------|
| Vast.ai | ✅ Connected | $22.72 balance |
| Backblaze B2 | ✅ Connected | 2 models cached (11.2GB) |
| Supabase | ✅ Connected | Tables accessible |
| HuggingFace | ✅ Authenticated | chachi88 |
| Ollama | ✅ Connected | llama3.1:8b local |
| ComfyUI | ❌ Offline | Needs GPU worker launched |
| ElevenLabs | ⏳ Pending | Key permissions issue |

## Model Cache (B2)

- `sd_xl_turbo_1.0_fp16.safetensors` (6.94 GB) ✅
- `v1-5-pruned-emaonly.safetensors` (4.27 GB) ✅
- Flux Dev — downloaded to worker but B2 cap hit (user needs to increase)

## Active Defect List

See `docs/DEFECTS.md` for full list (30 items).
Critical: Brain UI not wired, Create doesn't generate, Backend connection warning.

## Shell Quirks

- `&&` chaining works in this environment
- Python multiline via SSH fails — use SCP + run approach
- Vast.ai onstart scripts unreliable — SSH-based setup after boot is better
- RTX 50 series (Blackwell) GPUs unsupported by PyTorch — auto-exclude
