---
inclusion: always
---

# Project Status (auto-loaded in every session)

## Quick facts

- **Repo:** `garymcdaniel7/ai-studio88` on GitHub
- **Local path:** `/Users/garymcdaniel/kiro/ai-studio88`
- **Entry point:** `uv run uvicorn backend.main:app --reload` (from repo root)
- **Python:** 3.12.13 in `.venv/` (managed by uv at `~/.local/bin/uv`)
- **Database:** Supabase (PostgreSQL) — credentials in `.env`
- **Storage:** Backblaze B2 (bucket: ai-studio88)
- **Status:** Priorities 1-5 complete. Full platform operational.

## Architecture (current)

```
backend/
  main.py                  ← FastAPI entry point (mounts 5 routers)
  api_v1.py                ← Core API (150+ endpoints)
  database.py              ← All Supabase query functions
  storage.py               ← Backblaze B2 upload/delete
  worker.py                ← Job worker + handler registry
  workflow_engine.py       ← Multi-step workflow orchestrator
  intelligence.py          ← Legacy recommendation providers
  engine/                  ← Generation Engine (provider interface, simulation, ComfyUI)
  intelligence_engine/     ← 10 AI agents + orchestrator + LLM provider interface
  execution/               ← Worker manager, job router, 9 execution providers
  story_engine/            ← Universes, characters, episodes, scenes, shots
  production/              ← Pipelines, timeline, voice, music, camera system
  creator_os/              ← Campaigns, calendar, analytics, brands, teams
  autonomous_studio/       ← 19 AI departments, daily briefing, recommendations
  training/                ← LoRA training: datasets, captions, jobs, versions
  video/                   ← Video projects, shots, renders, timeline, exports
```

## Routers mounted in main.py

1. `api_v1` at `/api/v1` (core endpoints)
2. `creator_os` at `/api/v1` (campaigns, calendar, analytics)
3. `autonomous_studio` at `/api/v1/studio` (departments, briefing)
4. `training` at `/api/v1` (LoRA training lifecycle)
5. `video` at `/api/v1` (video production pipeline)

## Key systems

| System | Package | Status |
|---|---|---|
| Generation Engine | `backend/engine/` | ✅ SimulationProvider + ComfyUIProvider |
| Intelligence Engine | `backend/intelligence_engine/` | ✅ 10 agents + orchestrator |
| Execution Platform | `backend/execution/` | ✅ 9 providers, worker manager |
| Story Engine | `backend/story_engine/` | ✅ Universes → shots |
| Production Studio | `backend/production/` | ✅ 21 types, 8 pipelines |
| Creator OS | `backend/creator_os/` | ✅ Calendar, campaigns, analytics |
| Autonomous Studio | `backend/autonomous_studio/` | ✅ 19 departments |
| LoRA Training | `backend/training/` | ✅ Full lifecycle |
| Video Pipeline | `backend/video/` | ✅ Projects → export |

## Database (Supabase)

Tables created: projects, talent, assets, jobs, workflows, workflow_runs,
creative_dna, generation_feedback, prompt_history, style_preferences,
continuity_notes, creative_rules, models, workflow_templates, workers

Tables needing creation (run SQL in order):
- `005_story_engine.sql` — universes, characters, episodes, scenes, shots, story_memory
- `007_workers.sql` — workers
- `008_lora_training.sql` — training_datasets/images/jobs, lora_versions/evaluations
- `009_video_pipeline.sql` — video_projects/shots/renders, timeline_tracks/clips/exports

## Starting the server

```bash
cd /Users/garymcdaniel/kiro/ai-studio88
/Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --reload
```

Dashboard: `uv run streamlit run dashboard/app.py` (16 pages)

## Provider configuration

```env
GENERATION_PROVIDER=simulation   # simulation | comfyui
COMFYUI_BASE_URL=http://...      # Set when Vast.ai worker is online
AI_PROVIDER=simulation           # simulation | openai | anthropic
```
