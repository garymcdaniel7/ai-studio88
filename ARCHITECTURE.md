# AI Studio — Architecture

> Last updated: 2026-07-03
> Status: Active development — Phase 1

---

## 1. Vision

AI Studio is a multi-tenant SaaS platform that industrialises AI content production. It abstracts the complexity of GPU provisioning, model training, and content pipeline orchestration behind a clean API and (future) web dashboard.

The system is designed to handle **thousands of concurrent generation jobs** across multiple GPU cloud providers while maintaining strict per-tenant data isolation.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Clients                              │
│        Web Dashboard (Next.js)  │  API Consumers            │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼────────────────────────────────────────┐
│                   API Gateway / CDN                          │
│              (Nginx / Cloudflare)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              FastAPI Application Server                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               Service Layer                          │  │
│  │  TalentService │ CampaignService │ GenerationService │  │
│  │  TrainingService │ AssetService  │ AnalyticsService  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
┌─────────▼──────┐   ┌──────────▼──────────────────────────┐
│   Supabase     │   │       Task Queue (Celery + Redis)     │
│  (PostgreSQL)  │   │  GPU Jobs │  Media Processing         │
│  - Auth / RLS  │   └──────────┬──────────────────────────┘
│  - Realtime    │              │
└────────────────┘   ┌──────────▼────────────────────────┐
                     │       GPU Worker Fleet              │
                     │  Vast.ai GPU Nodes (ComfyUI)        │
                     │  RunPod GPU Nodes (roadmap)         │
                     └──────────┬────────────────────────┘
                                │
                     ┌──────────▼────────────────────────┐
                     │     Backblaze B2 Storage           │
                     │  images, videos, models, assets    │
                     └────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 FastAPI Backend (`backend/`)

Layered architecture:

| Layer | Path | Responsibility |
|---|---|---|
| API Layer | `app/api/v1/endpoints/` | HTTP route handlers, request validation |
| Service Layer | `app/services/` | Business logic, orchestration |
| Data Layer | `app/models/` | SQLAlchemy ORM models |
| Schema Layer | `app/schemas/` | Pydantic request/response DTOs |
| Core | `app/core/` | Config, security, dependencies |
| Workers | `app/workers/` | Celery tasks |

Existing flat files (`backend/main.py`, `backend/database.py`) represent the initial prototype. New features follow the layered `app/` structure.

### 3.2 Database (Supabase / PostgreSQL)

- **Auth:** Supabase Auth (email/password, OAuth)
- **RLS:** Row-Level Security enforces per-tenant isolation at DB level
- **Migrations:** Alembic for schema versioning

Key tables:
```
organisations → users (org_members) → ai_talent → campaigns → content_jobs
                                    → lora_models → assets → workflows
```

### 3.3 GPU Worker Architecture

Workers run on ephemeral Vast.ai instances:

1. API creates a `content_job` record in Supabase (status=queued)
2. Celery picks up job, provisions GPU on Vast.ai
3. GPU instance pulls ComfyUI + workflow, runs generation
4. Output uploaded to Backblaze B2
5. Worker updates job status via Supabase
6. GPU instance terminated to minimise cost

### 3.4 Storage (Backblaze B2)

Path structure: `/{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}`

- Signed URLs for time-limited access
- Optional CDN (Cloudflare) in front of B2

### 3.5 Celery Task Queue

- `generation.image` — ComfyUI image generation
- `generation.video` — WAN / LTX video generation
- `generation.voice` — Voice synthesis
- `training.lora` — LoRA fine-tuning
- `assets.upload` — B2 upload tasks

---

## 4. Multi-Tenancy

| Resource | Isolation Method |
|---|---|
| User data | Supabase Auth + RLS |
| AI Talent | `org_id` FK + RLS |
| Assets | `org_id` in B2 path + RLS |
| GPU Jobs | `org_id` FK + Celery queue isolation |
| LoRA Models | `org_id` FK + B2 path |

---

## 5. Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| API framework | FastAPI | Async-native, OpenAPI auto-docs, Pydantic validation |
| Database | Supabase/PostgreSQL | Auth + RLS + Realtime built-in |
| Storage | Backblaze B2 | ~75% cheaper than S3, S3-compatible API |
| Package manager | uv | 10-100x faster than pip, lockfile support |
| GPU provider | Vast.ai | Spot pricing, large GPU inventory |
| Task queue | Celery + Redis | Mature, priority queues, retries |
| Generation | ComfyUI | Workflow-based, extensible, large model ecosystem |

---

## 6. Future Considerations

- Event streaming via Supabase Realtime or Kafka for job status updates
- Multi-region API deployment for latency reduction
- RunPod as secondary GPU provider for redundancy
- PgBouncer connection pooling at scale
- OpenTelemetry distributed tracing
