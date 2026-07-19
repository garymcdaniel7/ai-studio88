# AI Studio — Progress Log

> Updated: 2026-07-19 (after V2 transformation session)

---

## Current State

**Status:** V2 transformation ~95% complete. 42+ commits this session. Brain generates images. Self-learning system live.

### Platform stats

| Metric | Count |
|---|---|
| API endpoints | 160+ |
| Playwright tests | 85 (83 pass = 98%) |
| Navigation items | 8 (down from 14) |
| Creative Recipes | 10 system |
| Agent learning endpoints | 6 |
| Commits this session | 42+ |

### Test Results (latest)

| File | Pass | Total |
|------|------|-------|
| home | 5 | 5 |
| brain | 7 | 7 |
| create | 8 | 8 |
| talent | 5 | 5 |
| assets | 6 | 6 |
| models | 7 | 8 |
| training | 5 | 5 |
| settings | 4 | 4 |
| admin | 11 | 12 |
| publish | 4 | 4 |
| navigation | 23 | 23 |

---

## Next Session Priorities

### Sprint 2 (from Red Team Report)
1. Remove Music tab dead feature (or add Coming Soon badge)
2. Hide ControlNet until image upload implemented
3. Add "Save to Library" button on generation results
4. Auth gate (middleware + login redirect)
5. Change Railway fallback URL to localhost for safety

### Sprint 3 (Scale)
6. Add pagination to Assets and Talent
7. Persist Brain collections on mount
8. Training cancel button
9. Publish delivery mechanism (or honest "Draft" label)
10. Rate limiting (debounce Generate button)

### Enhanced Playwright Testing (target: 200+ tests)
- Cross-page flow tests (generate→save→find in library)
- Backend connection tests (GPU offline graceful errors)
- Hidden pages (/login, /projects/[id], /admin/fleet, etc.)
- Screenshot comparison for visual regression
- Navigation integrity (back button, deep links)

### Remaining V2 Items
- Talent page simplification (8 tabs → search + grid)
- Library AI semantic search
- Wire Supabase Auth SDK into login page
- Movie assembly timeline
- Smart AI suggestions (context-aware from learning)

---

## Build History

| Phase/Priority | Deliverable | Commit |
|---|---|---|
| Sprint 1 | Foundation: API, Supabase, B2 | `69f7b53`→`4be07de` |
| Sprint 2 | Job Engine: worker, handler registry | `4c8bbba` |
| Sprint 3 | Workflow Engine: multi-step orchestration | `9696202` |
| Sprint 4 | Dashboard: Streamlit UI | `4d1c353` |
| Sprint 5 | AI Intelligence Layer (design) | `802304b` |
| Sprint 6 | Creative Session | `fe45363` |
| Sprint 7 | Creative DNA + Feedback Loop | `46d4ed5` |
| Phase A | Generation Engine (full vertical slice) | `2e3d990`→`ee7e944` |
| Phase B | AI Intelligence Engine (10 agents) | `972a9be` |
| Phase C | Execution Platform (workers, routing) | `2302124` |
| Phase D | Creative DNA Engine (rules, continuity) | `37e1764` |
| Phase E | Story Engine (universes, characters, shots) | `40f5080` |
| Phase F | Production Studio (pipelines, voice, music) | `12773a7` |
| Phase G | Creator OS (campaigns, calendar, analytics) | `ac570d5` |
| Phase H | Autonomous Studio (19 departments) | `d633af4` |
| Priority 1 | Real ComfyUI + Vast.ai worker guide | `e11acbd` |
| Priority 2 | Model & Workflow Manager | `0293844` |
| Priority 3 | Worker Manager & GPU Routing | `668e51c` |
| Priority 4 | LoRA Training Manager | `e0e3212` |
| Priority 5 | Video Generation & Editing Pipeline | `1421148` |

---

## What's next

1. **Connect real ComfyUI worker** — Set `GENERATION_PROVIDER=comfyui` when Vast.ai instance is online
2. **Run pending SQL migrations** — Story, workers, training, video tables
3. **Connect LLM** — Set `AI_PROVIDER=openai` for real agent reasoning
4. **First real generation** — Luxury portrait through ComfyUI on Vast.ai
5. **First real LoRA training** — Melissa character on Kohya/FluxGym
6. **Real video generation** — WAN 2.1 on GPU worker

---

## SQL migrations to run (in order)

```
docs/sql/004_continuity_and_rules.sql    ← continuity_notes, creative_rules
docs/sql/005_story_engine.sql            ← universes, characters, episodes, scenes, shots, story_memory
docs/sql/006_models_and_templates.sql    ← models, workflow_templates (DONE)
docs/sql/006b_seed_models.sql            ← seed data (DONE)
docs/sql/007_workers.sql                 ← workers
docs/sql/008_lora_training.sql           ← training_datasets, images, jobs, lora_versions, evaluations
docs/sql/009_video_pipeline.sql          ← video_projects, shots, renders, timeline_tracks/clips/exports
```

---

## How to start

```bash
cd /Users/garymcdaniel/kiro/ai-studio88
/Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --reload
# API: http://localhost:8000
# Docs: http://localhost:8000/docs

uv run streamlit run dashboard/app.py
# Dashboard: http://localhost:8501
```
