# AI Studio — Living Architecture Document

> **Last updated:** 2026-07-03 (Sprint 3)
> **Status:** Phase 1 — Foundation (Workflow Engine added)
> **Maintainer:** Update after each sprint.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Clients                                   │
│   curl / Postman / Frontend (future)                             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (localhost:8000)
┌────────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Application                            │
│                    backend/main.py                                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              /api/v1 Router (backend/api_v1.py)              │ │
│  │                                                             │ │
│  │  /health  /projects  /talent  /assets  /jobs  /workflows    │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────┬─────────────────┬────────────────────┬───────────────────┘
        │                 │                    │
        │ Supabase        │ Workflow Engine    │ S3 API
        │ (database.py)   │ (workflow_engine)  │ (storage.py)
        ▼                 ▼                    ▼
┌────────────────┐ ┌──────────────┐  ┌─────────────────┐
│   Supabase     │ │  Job Worker  │  │  Backblaze B2   │
│  (PostgreSQL)  │ │  (worker.py) │  │  ai-studio88    │
│                │ │              │  │                 │
│  Tables:       │ │  Handlers:   │  └─────────────────┘
│  • projects    │ │  • Simulation│
│  • talent      │ │  • (Flux)    │
│  • assets      │ │  • (WAN)     │
│  • jobs        │ │  • (LoRA)    │
│  • workflows   │ │  • ...       │
│  • workflow_runs│ └──────────────┘
└────────────────┘
```

---

## Implemented Components

| File | Role |
|---|---|
| `backend/main.py` | FastAPI app, root endpoints, mounts v1 router |
| `backend/api_v1.py` | All `/api/v1` endpoints (talent, assets, jobs, workflows) |
| `backend/database.py` | Supabase client, all query functions |
| `backend/storage.py` | Backblaze B2 upload/delete via boto3 |
| `backend/worker.py` | Job worker with BaseHandler + SimulationHandler |
| `backend/workflow_engine.py` | Workflow orchestrator with dependency resolution |

---

## API Endpoints (18 total)

| Method | Path | Sprint | Description |
|---|---|---|---|
| GET | `/` | 1 | Health check |
| GET | `/projects` | 1 | List projects |
| GET | `/talent` | 1 | List talent |
| POST | `/talent` | 1 | Create talent |
| GET | `/api/v1/health` | 1 | V1 health |
| GET | `/api/v1/projects` | 1 | V1 projects |
| GET | `/api/v1/talent` | 1 | V1 talent list |
| POST | `/api/v1/talent` | 1 | V1 create talent |
| GET | `/api/v1/assets` | 1 | List assets |
| GET | `/api/v1/assets/{id}` | 1 | Get asset |
| POST | `/api/v1/assets` | 1 | Upload → B2 + Supabase |
| DELETE | `/api/v1/assets/{id}` | 1 | Delete asset |
| GET | `/api/v1/jobs` | 2 | List jobs |
| GET | `/api/v1/jobs/{id}` | 2 | Get job |
| POST | `/api/v1/jobs` | 2 | Create job |
| DELETE | `/api/v1/jobs/{id}` | 2 | Delete job |
| POST | `/api/v1/jobs/{id}/cancel` | 2 | Cancel job |
| POST | `/api/v1/jobs/{id}/retry` | 2 | Retry job |
| GET | `/api/v1/workflows` | 3 | List workflows |
| GET | `/api/v1/workflows/{id}` | 3 | Get workflow |
| POST | `/api/v1/workflows` | 3 | Create workflow |
| PUT | `/api/v1/workflows/{id}` | 3 | Update workflow |
| DELETE | `/api/v1/workflows/{id}` | 3 | Delete workflow |
| POST | `/api/v1/workflows/{id}/run` | 3 | Execute workflow |

---

## Database Schema (6 tables)

### `projects` / `talent` / `assets` / `jobs`

See previous sprint docs for these schemas.

### `workflows`

| Column | Type |
|---|---|
| id | UUID PK |
| project_id | UUID FK |
| name | TEXT |
| description | TEXT |
| version | INTEGER |
| status | TEXT (draft/active/archived) |
| trigger_type | TEXT (manual/schedule/event/api) |
| steps | JSONB |
| definition | JSONB |
| created_at / updated_at | TIMESTAMPTZ |

### `workflow_runs`

| Column | Type |
|---|---|
| id | UUID PK |
| workflow_id | UUID FK |
| status | TEXT (running/completed/failed/cancelled) |
| input / output | JSONB |
| current_step / total_steps | INTEGER |
| error | TEXT |
| created_at / completed_at / updated_at | TIMESTAMPTZ |

---

## Data Flow: Workflow Execution

```
Client                API           Engine          Supabase         Worker/Handler
  │                    │              │                │                 │
  │ POST /run          │              │                │                 │
  │───────────────────►│              │                │                 │
  │                    │ execute()    │                │                 │
  │                    │─────────────►│                │                 │
  │                    │              │ create run     │                 │
  │                    │              │───────────────►│                 │
  │                    │              │                │                 │
  │                    │              │ step 0: create job               │
  │                    │              │───────────────►│                 │
  │                    │              │ execute handler│                 │
  │                    │              │────────────────────────────────►│
  │                    │              │ progress 33%   │                 │
  │                    │              │◄────────────────────────────────│
  │                    │              │ progress 100%  │                 │
  │                    │              │◄────────────────────────────────│
  │                    │              │ complete job   │                 │
  │                    │              │───────────────►│                 │
  │                    │              │                │                 │
  │                    │              │ step 1: (deps met, run)         │
  │                    │              │    ... same pattern ...          │
  │                    │              │                │                 │
  │                    │              │ all steps done │                 │
  │                    │              │ complete run   │                 │
  │                    │              │───────────────►│                 │
  │                    │◄─────────────│                │                 │
  │  200 { run result }│              │                │                 │
  │◄───────────────────│              │                │                 │
```

---

## Technology Stack

| Layer | Technology | Status |
|---|---|---|
| API | FastAPI 0.139.0 | ✅ |
| Runtime | Python 3.12.13 (uv) | ✅ |
| Database | Supabase PostgreSQL | ✅ |
| Storage | Backblaze B2 | ✅ |
| Job Worker | backend/worker.py | ✅ |
| Workflow Engine | backend/workflow_engine.py | ✅ |
| Package Manager | uv 0.11.26 | ✅ |
| VCS | Git + GitHub | ✅ |

---

## Not Yet Implemented

| Component | Phase |
|---|---|
| JWT Auth | 1 |
| Real GPU handlers (Flux, WAN, LoRA) | 2 |
| Celery + Redis queue | 2 |
| Vast.ai GPU provisioning | 2 |
| ComfyUI integration | 2 |
| Multi-tenant RBAC | 5 |
| Stripe billing | 5 |
| Frontend dashboard | 8 |

---

## File Tree

```
ai-studio88/
├── backend/
│   ├── main.py              ← Entry point
│   ├── api_v1.py            ← /api/v1 router (24 endpoints)
│   ├── database.py          ← Supabase queries
│   ├── storage.py           ← B2 storage
│   ├── worker.py            ← Job worker + handler registry
│   ├── workflow_engine.py   ← Workflow orchestrator
│   └── app/                 ← Future layered scaffold
├── docs/
│   ├── ARCHITECTURE.md      ← THIS FILE
│   ├── JOBS.md              ← Job engine docs
│   ├── WORKFLOWS.md         ← Workflow engine docs
│   └── sql/                 ← Migration SQL
├── infrastructure/
├── .kiro/
├── .github/workflows/
└── docker-compose.yml
```

---

## How to Update

After each sprint:
1. Update endpoint count and table
2. Add new tables to schema section
3. Update system diagram
4. Commit: `docs(arch): update for sprint N`

---

*Living document. Reflects what is deployed and working.*
