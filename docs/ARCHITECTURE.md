# AI Studio — Living Architecture Document

> **Last updated:** 2026-07-03 (Sprint 5)
> **Status:** Phase 1 — Foundation + Intelligence Layer designed
> **Maintainer:** Update after each sprint.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Clients                                   │
│   Streamlit Dashboard (8501) │ curl/Postman │ Frontend (future)  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (8000)                          │
│                                                                   │
│  /api/v1:  health │ projects │ talent │ assets │ jobs │ workflows│
└───────┬─────────────────┬────────────────────┬───────────────────┘
        │                 │                    │
        │ Supabase        │ Engines            │ S3 API
        ▼                 ▼                    ▼
┌────────────────┐ ┌──────────────────┐ ┌─────────────────┐
│   Supabase     │ │ Job Worker       │ │  Backblaze B2   │
│  (PostgreSQL)  │ │ Workflow Engine   │ │  ai-studio88    │
│                │ │ (future: AI      │ └─────────────────┘
│  6 tables:     │ │  Intelligence)   │
│  projects      │ └──────────────────┘
│  talent        │
│  assets        │       ┌─────────────────────────────────┐
│  jobs          │       │   AI Intelligence Layer          │
│  workflows     │       │   (Sprint 5 — designed)         │
│  workflow_runs │       │                                  │
│                │       │   Agents:                        │
│  (future:)     │       │   • Creative Director           │
│  generation_   │       │   • Prompt Engineer             │
│  feedback      │       │   • Workflow Optimizer           │
│  prompt_history│       │   • Model Expert                │
│  assistant_    │       │   • GPU Optimizer               │
│  memory        │       │   • Learning Engine             │
│  style_        │       │                                  │
│  preferences   │       │   + Recommendation Engine       │
│                │       │   + Feedback/Memory Store        │
└────────────────┘       └─────────────────────────────────┘
```

---

## Implemented Components

| File | Role | Sprint |
|---|---|---|
| `backend/main.py` | FastAPI app, root endpoints | 1 |
| `backend/api_v1.py` | All `/api/v1` endpoints | 1-3 |
| `backend/database.py` | Supabase queries | 1-3 |
| `backend/storage.py` | Backblaze B2 via boto3 | 1 |
| `backend/worker.py` | Job worker + handler registry | 2 |
| `backend/workflow_engine.py` | Workflow orchestrator | 3 |
| `dashboard/` | Streamlit UI (6 pages) | 4 |
| `docs/AI_INTELLIGENCE.md` | Intelligence layer architecture | 5 |

---

## API Endpoints (24 total)

| Method | Path | Sprint |
|---|---|---|
| GET | `/` | 1 |
| GET | `/projects` | 1 |
| GET | `/talent` | 1 |
| POST | `/talent` | 1 |
| GET | `/api/v1/health` | 1 |
| GET | `/api/v1/projects` | 1 |
| GET | `/api/v1/talent` | 1 |
| POST | `/api/v1/talent` | 1 |
| GET | `/api/v1/assets` | 1 |
| GET | `/api/v1/assets/{id}` | 1 |
| POST | `/api/v1/assets` | 1 |
| DELETE | `/api/v1/assets/{id}` | 1 |
| GET | `/api/v1/jobs` | 2 |
| GET | `/api/v1/jobs/{id}` | 2 |
| POST | `/api/v1/jobs` | 2 |
| DELETE | `/api/v1/jobs/{id}` | 2 |
| POST | `/api/v1/jobs/{id}/cancel` | 2 |
| POST | `/api/v1/jobs/{id}/retry` | 2 |
| GET | `/api/v1/workflows` | 3 |
| GET | `/api/v1/workflows/{id}` | 3 |
| POST | `/api/v1/workflows` | 3 |
| PUT | `/api/v1/workflows/{id}` | 3 |
| DELETE | `/api/v1/workflows/{id}` | 3 |
| POST | `/api/v1/workflows/{id}/run` | 3 |

---

## Database Schema (6 tables implemented, 5 designed)

**Implemented:** `projects`, `talent`, `assets`, `jobs`, `workflows`, `workflow_runs`

**Designed (Sprint 5, not yet created):**
- `generation_feedback` — star ratings + problem tags per output
- `workflow_feedback` — workflow execution quality ratings
- `prompt_history` — prompts + outcomes for learning
- `assistant_memory` — per-agent, per-tenant context memory
- `style_preferences` — learned style preferences per talent

See `docs/AI_INTELLIGENCE.md` for full schema proposals.

---

## AI Intelligence Layer (Designed — Sprint 5)

Six specialized agents + recommendation engine:

| Agent | Purpose |
|---|---|
| Creative Director | Refines concepts, suggests composition, maintains brand |
| Prompt Engineer | Model-specific prompt optimization (Flux, WAN, SDXL, etc.) |
| Workflow Optimizer | Recommends steps, templates, execution order |
| Model Expert | Checkpoint/LoRA/ControlNet selection and settings |
| GPU Optimizer | Routes jobs to cheapest/fastest provider |
| Learning Engine | Aggregates feedback, identifies patterns |

**Recommendation Engine** surfaces proactive suggestions based on feedback data.

**Multi-tenant isolation:** All intelligence data scoped by `org_id`. No cross-tenant learning.

Full architecture: `docs/AI_INTELLIGENCE.md`

---

## Technology Stack

| Layer | Technology | Status |
|---|---|---|
| API | FastAPI 0.139.0 | ✅ Running |
| Runtime | Python 3.12.13 (uv) | ✅ |
| Database | Supabase PostgreSQL | ✅ |
| Storage | Backblaze B2 | ✅ |
| Job Worker | backend/worker.py | ✅ |
| Workflow Engine | backend/workflow_engine.py | ✅ |
| Dashboard | Streamlit 1.58.0 | ✅ |
| AI Intelligence | Designed (docs only) | 📋 |
| VCS | Git + GitHub | ✅ |

---

## Documentation Index

| Document | Content |
|---|---|
| `docs/ARCHITECTURE.md` | This file — system overview |
| `docs/JOBS.md` | Job engine lifecycle and worker docs |
| `docs/WORKFLOWS.md` | Workflow engine and step dependencies |
| `docs/DASHBOARD.md` | Streamlit UI pages and startup |
| `docs/AI_INTELLIGENCE.md` | Intelligence layer architecture |
| `docs/sql/` | Migration SQL files |

---

## File Tree

```
ai-studio88/
├── backend/
│   ├── main.py
│   ├── api_v1.py
│   ├── database.py
│   ├── storage.py
│   ├── worker.py
│   ├── workflow_engine.py
│   └── app/                 ← Future scaffold
├── dashboard/
│   ├── app.py
│   ├── api_client.py
│   └── pages/ (6 pages)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── JOBS.md
│   ├── WORKFLOWS.md
│   ├── DASHBOARD.md
│   ├── AI_INTELLIGENCE.md
│   └── sql/
├── infrastructure/
├── .kiro/
├── .github/workflows/
└── docker-compose.yml
```

---

## Sprint History

| Sprint | Deliverable | Commit |
|---|---|---|
| 1 | Foundation: API, Supabase, B2, project structure | `69f7b53` → `4be07de` |
| 2 | Job Engine: async jobs, worker, handler registry | `4c8bbba` |
| 3 | Workflow Engine: multi-step orchestration | `9696202` |
| 4 | Dashboard: Streamlit UI with 6 pages | `4d1c353` |
| 5 | AI Intelligence Layer: architecture design | (this commit) |

---

*Living document. Updated after each sprint.*
