# AI Studio — Living Architecture Document

> **Last updated:** 2026-07-03 (Phase A Part 2)
> **Status:** Phase A — Generation Engine complete
> **Maintainer:** Update after each phase/sprint.

---

## Design Principles

AI Studio is a **Creative Intelligence Platform**, not a GPU rendering application.

- The backend **orchestrates, coordinates, schedules, recommends, queues, monitors, and learns**
- Heavy compute executes in **external workers** (ComfyUI, Vast.ai, Shadow PC, RunPod)
- The API process stays responsive regardless of generation workload
- Everything communicates through **interfaces** — no provider-specific code leaks outside the provider layer
- AI Studio is an **operating system** for AI content production, not a model runner

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Clients                                   │
│   Streamlit (8501) │ curl/Postman │ Future Frontend               │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (8000)                          │
│          Lightweight orchestration layer — no heavy compute       │
│                                                                   │
│  /api/v1:                                                         │
│    health │ projects │ talent │ assets │ jobs │ workflows         │
│    creative-dna │ feedback │ generation/*                         │
└───────┬────────────────┬────────────────────┬────────────────────┘
        │                │                    │
        │ DB             │ Engine             │ Storage
        ▼                ▼                    ▼
┌────────────────┐ ┌───────────────────┐ ┌─────────────────┐
│   Supabase     │ │ Generation Engine │ │  Backblaze B2   │
│  (PostgreSQL)  │ │                   │ │  ai-studio88    │
│                │ │  Provider Interface│ └─────────────────┘
│  10 tables:    │ │    │              │
│  projects      │ │    ├─ Simulation  │
│  talent        │ │    ├─ ComfyUI     │
│  assets        │ │    ├─ (Forge)     │
│  jobs          │ │    ├─ (InvokeAI)  │
│  workflows     │ │    └─ (Cloud GPU) │
│  workflow_runs │ │                   │
│  creative_dna  │ │  Model Registry   │
│  generation_   │ │  GPU Manager      │
│    feedback    │ │  Queue Manager    │
│  prompt_history│ └───────────────────┘
│  style_prefs   │
└────────────────┘        ┌────────────────────────────────┐
                          │  External Compute (future)      │
                          │  • ComfyUI on local GPU         │
                          │  • ComfyUI on Shadow PC         │
                          │  • Vast.ai spot instances       │
                          │  • RunPod serverless            │
                          │  • Internal GPU cluster         │
                          └────────────────────────────────┘
```

---

## API Endpoints (32 total)

| Method | Path | Phase |
|---|---|---|
| GET | `/` | S1 |
| GET | `/projects` | S1 |
| GET | `/talent` | S1 |
| POST | `/talent` | S1 |
| GET | `/api/v1/health` | S1 |
| GET | `/api/v1/projects` | S1 |
| GET | `/api/v1/talent` | S1 |
| POST | `/api/v1/talent` | S1 |
| GET | `/api/v1/assets` | S1 |
| GET | `/api/v1/assets/{id}` | S1 |
| POST | `/api/v1/assets` | S1 |
| DELETE | `/api/v1/assets/{id}` | S1 |
| GET | `/api/v1/jobs` | S2 |
| GET | `/api/v1/jobs/{id}` | S2 |
| POST | `/api/v1/jobs` | S2 |
| DELETE | `/api/v1/jobs/{id}` | S2 |
| POST | `/api/v1/jobs/{id}/cancel` | S2 |
| POST | `/api/v1/jobs/{id}/retry` | S2 |
| GET | `/api/v1/workflows` | S3 |
| GET | `/api/v1/workflows/{id}` | S3 |
| POST | `/api/v1/workflows` | S3 |
| PUT | `/api/v1/workflows/{id}` | S3 |
| DELETE | `/api/v1/workflows/{id}` | S3 |
| POST | `/api/v1/workflows/{id}/run` | S3 |
| GET | `/api/v1/creative-dna` | S7 |
| GET | `/api/v1/creative-dna/{talent_id}` | S7 |
| POST | `/api/v1/creative-dna` | S7 |
| PUT | `/api/v1/creative-dna/{id}` | S7 |
| GET | `/api/v1/feedback` | S7 |
| POST | `/api/v1/feedback` | S7 |
| GET | `/api/v1/generation/health` | A |
| GET | `/api/v1/generation/providers` | A |
| GET | `/api/v1/generation/models` | A |
| POST | `/api/v1/generation/run` | A |
| GET | `/api/v1/generation/history` | A |
| GET | `/api/v1/generation/{id}/status` | A |
| POST | `/api/v1/generation/{id}/cancel` | A |
| POST | `/api/v1/generation/{id}/retry` | A |

---

## Generation Engine

The engine is a **lightweight orchestrator** — it dispatches to providers but never runs GPU workloads itself.

```
POST /generation/run
  → Build GenerationRequest
  → Create job (status=running)
  → Dispatch to provider.submit()
  → Provider executes externally (simulation or real GPU)
  → Progress callbacks → job.progress updated
  → Output bytes returned
  → Upload to B2
  → Create asset record (with full metadata)
  → Mark job completed
  → Return { job_id, asset, provider }
```

### Output metadata captured on every generation:

- Prompt + negative prompt
- Seed used
- Model + version
- LoRA stack + strengths
- Sampler + scheduler
- CFG scale
- Resolution
- Steps
- Generation time (seconds)
- Provider used
- GPU used
- Creative Session ID
- Workflow ID
- Job ID
- Talent ID + Project ID

---

## Technology Stack

| Layer | Technology | Status |
|---|---|---|
| API | FastAPI 0.139.0 | ✅ |
| Runtime | Python 3.12.13 (uv) | ✅ |
| Database | Supabase PostgreSQL (10 tables) | ✅ |
| Storage | Backblaze B2 | ✅ |
| Generation Engine | backend/engine/ | ✅ |
| Job Worker | backend/worker.py | ✅ |
| Workflow Engine | backend/workflow_engine.py | ✅ |
| Intelligence Layer | backend/intelligence.py | ✅ |
| Dashboard | Streamlit (9 pages) | ✅ |
| VCS | Git + GitHub | ✅ |

---

## File Tree

```
ai-studio88/
├── backend/
│   ├── main.py                  ← Entry point
│   ├── api_v1.py                ← All /api/v1 endpoints (38)
│   ├── database.py              ← Supabase queries
│   ├── storage.py               ← B2 storage
│   ├── worker.py                ← Job worker + handler registry
│   ├── workflow_engine.py       ← Workflow orchestrator
│   ├── intelligence.py          ← AI recommendation providers
│   └── engine/
│       ├── generation_engine.py ← Engine + model registry + GPU manager
│       ├── models.py            ← Internal data models
│       ├── provider.py          ← Provider interface (ABC)
│       └── providers/
│           ├── simulation.py    ← Dev/test provider
│           └── comfyui.py       ← Production provider
├── dashboard/
│   ├── app.py, api_client.py
│   └── pages/ (9 pages)
├── docs/
│   ├── ARCHITECTURE.md, GENERATION_ENGINE.md
│   ├── JOBS.md, WORKFLOWS.md, DASHBOARD.md
│   ├── AI_INTELLIGENCE.md, CREATIVE_SESSION.md
│   ├── CREATIVE_DNA.md
│   └── sql/ (3 migration files)
├── infrastructure/, .kiro/, .github/
└── docker-compose.yml
```

---

## Phase History

| Phase | Deliverable | Commit |
|---|---|---|
| S1 | Foundation: API, Supabase, B2 | `69f7b53`→`4be07de` |
| S2 | Job Engine: worker, handler registry | `4c8bbba` |
| S3 | Workflow Engine: multi-step orchestration | `9696202` |
| S4 | Dashboard: Streamlit UI | `4d1c353` |
| S5 | AI Intelligence Layer (design) | `802304b` |
| S6 | Creative Session | `fe45363` |
| S7 | Creative DNA + Feedback Loop | `46d4ed5` |
| A | Generation Engine (full vertical slice) | `2e3d990`→current |

---

*Living document. Updated after each phase.*
