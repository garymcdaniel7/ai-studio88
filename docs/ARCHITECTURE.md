# AI Studio — Living Architecture Document

> **Last updated:** 2026-07-03 (Sprint 1)
> **Status:** Phase 1 — Foundation
> **Maintainer:** Update this document after each sprint or major subsystem change.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Clients                                   │
│                                                                   │
│   curl / Postman / Frontend (future)                             │
│                                                                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (localhost:8000)
┌────────────────────────────▼─────────────────────────────────────┐
│                                                                   │
│                    FastAPI Application                            │
│                    backend/main.py                                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   Root Endpoints                             │ │
│  │  GET /          GET /projects    GET /talent    POST /talent │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              /api/v1 Router (backend/api_v1.py)              │ │
│  │                                                             │ │
│  │  GET  /api/v1/health                                        │ │
│  │  GET  /api/v1/projects                                      │ │
│  │  GET  /api/v1/talent       POST /api/v1/talent              │ │
│  │  GET  /api/v1/assets       POST /api/v1/assets              │ │
│  │  GET  /api/v1/assets/{id}  DELETE /api/v1/assets/{id}       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└───────┬──────────────────────────────────┬───────────────────────┘
        │                                  │
        │ Supabase Client                  │ S3-Compatible API
        │ (backend/database.py)            │ (backend/storage.py)
        ▼                                  ▼
┌───────────────────┐            ┌─────────────────────────┐
│                   │            │                         │
│     Supabase      │            │     Backblaze B2        │
│   (PostgreSQL)    │            │                         │
│                   │            │  Bucket: ai-studio88    │
│  Tables:          │            │                         │
│  • projects       │            │  Keys:                  │
│  • talent         │            │  {type}/{uuid}_{name}   │
│  • assets         │            │                         │
│                   │            │                         │
└───────────────────┘            └─────────────────────────┘
```

---

## Implemented Components (Sprint 1)

### Backend Entry Point

| File | Role |
|---|---|
| `backend/main.py` | FastAPI app factory, root endpoints, mounts v1 router |
| `backend/api_v1.py` | `/api/v1` prefix router — all versioned endpoints |
| `backend/database.py` | Supabase Python client, query functions |
| `backend/storage.py` | Backblaze B2 upload/delete via boto3 S3 API |

### Data Flow: Asset Upload

```
Client                    API                     B2              Supabase
  │                        │                      │                 │
  │  POST /api/v1/assets   │                      │                 │
  │  (multipart file)      │                      │                 │
  │───────────────────────►│                      │                 │
  │                        │                      │                 │
  │                        │  put_object()        │                 │
  │                        │─────────────────────►│                 │
  │                        │                      │                 │
  │                        │  200 OK              │                 │
  │                        │◄─────────────────────│                 │
  │                        │                      │                 │
  │                        │  INSERT INTO assets  │                 │
  │                        │──────────────────────────────────────►│
  │                        │                      │                 │
  │                        │  asset record        │                 │
  │                        │◄──────────────────────────────────────│
  │                        │                      │                 │
  │  201 { asset }         │                      │                 │
  │◄───────────────────────│                      │                 │
```

### Data Flow: Asset Delete

```
Client                    API                     B2              Supabase
  │                        │                      │                 │
  │  DELETE /assets/{id}   │                      │                 │
  │───────────────────────►│                      │                 │
  │                        │  SELECT asset        │                 │
  │                        │──────────────────────────────────────►│
  │                        │◄──────────────────────────────────────│
  │                        │                      │                 │
  │                        │  delete_object()     │                 │
  │                        │─────────────────────►│                 │
  │                        │                      │                 │
  │                        │  DELETE FROM assets  │                 │
  │                        │──────────────────────────────────────►│
  │                        │                      │                 │
  │  200 { deleted }       │                      │                 │
  │◄───────────────────────│                      │                 │
```

---

## Database Schema (Supabase)

### `projects`

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, auto-generated |
| name | TEXT | |
| description | TEXT | |
| status | TEXT | active / archived |
| created_at | TIMESTAMPTZ | |

### `talent`

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, auto-generated |
| project_id | UUID | FK → projects(id) |
| name | TEXT | |
| bio | TEXT | |
| gender | TEXT | |
| age | INT | |
| ethnicity | TEXT | |
| status | TEXT | active / archived |
| is_active | BOOLEAN | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| *(+ social handles, profile_image, etc.)* | | |

### `assets`

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, auto-generated |
| project_id | UUID | FK → projects(id), nullable |
| talent_id | UUID | FK → talent(id), nullable |
| type | TEXT | general / image / video / audio / model / document |
| filename | TEXT | Generated unique filename in B2 |
| original_filename | TEXT | User's original filename |
| mime_type | TEXT | e.g. image/png, video/mp4 |
| size_bytes | BIGINT | |
| storage_provider | TEXT | backblaze_b2 |
| storage_key | TEXT | Full B2 object key |
| public_url | TEXT | Direct B2 URL |
| thumbnail_url | TEXT | Optional |
| checksum | TEXT | SHA-256 of file content |
| metadata | JSONB | Extensible metadata |
| tags | TEXT[] | Array of string tags |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

## API Endpoints (Current)

| Method | Path | Status | Description |
|---|---|---|---|
| GET | `/` | ✅ | Health check |
| GET | `/projects` | ✅ | List projects |
| GET | `/talent` | ✅ | List talent |
| POST | `/talent` | ✅ | Create talent |
| GET | `/api/v1/health` | ✅ | V1 health |
| GET | `/api/v1/projects` | ✅ | V1 list projects |
| GET | `/api/v1/talent` | ✅ | V1 list talent |
| POST | `/api/v1/talent` | ✅ | V1 create talent |
| GET | `/api/v1/assets` | ✅ | List all assets |
| GET | `/api/v1/assets/{id}` | ✅ | Get asset by ID |
| POST | `/api/v1/assets` | ✅ | Upload file → B2 + Supabase |
| DELETE | `/api/v1/assets/{id}` | ✅ | Delete from B2 + Supabase |

---

## Storage Architecture (Backblaze B2)

```
Bucket: ai-studio88
Region: us-east-005

Key pattern:
  {asset_type}/{uuid_prefix}_{original_filename}

Examples:
  image/a1b2c3d4e5f6_portrait_melissa.png
  document/f7e8d9c0b1a2_training_notes.pdf
  model/1a2b3c4d5e6f_lora_v3.safetensors
```

**Access:** Public URLs via `https://s3.us-east-005.backblazeb2.com/ai-studio88/{key}`

---

## Technology Stack (Implemented)

| Layer | Technology | Status |
|---|---|---|
| API Framework | FastAPI 0.139.0 | ✅ Running |
| Python Runtime | 3.12.13 (managed by uv) | ✅ |
| Database | Supabase (hosted PostgreSQL) | ✅ Connected |
| Storage | Backblaze B2 (S3-compatible) | ✅ Connected |
| Package Manager | uv 0.11.26 | ✅ |
| Version Control | Git + GitHub | ✅ |

---

## Not Yet Implemented (Roadmap)

| Component | Target Phase | Notes |
|---|---|---|
| JWT Auth Middleware | Phase 1 | Validate Supabase tokens |
| SQLAlchemy ORM | Phase 1 | Replace direct Supabase client for complex queries |
| Celery + Redis | Phase 1 | Async job queue |
| GPU Provisioning (Vast.ai) | Phase 1 | Ephemeral ComfyUI instances |
| ComfyUI Workflow Execution | Phase 1 | Image generation pipeline |
| LoRA Training Pipeline | Phase 3 | Fine-tuning on GPU instances |
| Video Generation (WAN/LTX) | Phase 4 | |
| Multi-tenant RBAC | Phase 5 | org_id isolation |
| Stripe Billing | Phase 5 | Usage-based pricing |
| Frontend Dashboard | Phase 8 | Next.js |

---

## Infrastructure (Defined, Not Running)

| Component | Config File | Status |
|---|---|---|
| Docker (API) | `infrastructure/docker/Dockerfile.api` | Defined |
| Docker Compose | `docker-compose.yml` | Defined (API, worker, Redis, Nginx, Flower) |
| Nginx reverse proxy | `infrastructure/nginx/nginx.dev.conf` | Defined |
| GitHub Actions CI | `.github/workflows/ci.yml` | Defined (lint, test, security, build) |

---

## File Tree (Key Files)

```
ai-studio88/
├── backend/
│   ├── main.py              ← App entry point
│   ├── api_v1.py            ← /api/v1 router
│   ├── database.py          ← Supabase client + queries
│   ├── storage.py           ← B2 upload/delete
│   ├── app/                 ← Future layered scaffold
│   │   ├── core/            ← config, security, logging
│   │   ├── api/v1/endpoints/← typed endpoints (future)
│   │   ├── db/              ← SQLAlchemy session (future)
│   │   ├── schemas/         ← Pydantic DTOs
│   │   ├── models/          ← ORM models (future)
│   │   ├── services/        ← Business logic (future)
│   │   └── workers/         ← Celery tasks (future)
│   └── pyproject.toml
├── infrastructure/
│   ├── docker/Dockerfile.api
│   └── nginx/nginx.dev.conf
├── .kiro/
│   ├── steering/            ← 13 engineering standards
│   ├── skills/              ← 10 workflow recipes
│   └── PROGRESS.md          ← Sprint progress log
├── docs/
│   └── ARCHITECTURE.md      ← THIS FILE
├── docker-compose.yml
├── bootstrap.sh
├── verify_environment.sh
├── .env.example
└── .github/workflows/ci.yml
```

---

## How to Update This Document

After each sprint or significant subsystem addition:

1. Update the **System Overview** diagram if new services/connections are added
2. Add new tables to the **Database Schema** section
3. Add new endpoints to the **API Endpoints** table
4. Move items from **Not Yet Implemented** to **Implemented** as completed
5. Update the **Data Flow** diagrams for new patterns
6. Commit with message: `docs(arch): update architecture for sprint N`

---

*This is a living document. It reflects what is actually deployed and working, not aspirational architecture. See `ARCHITECTURE.md` in the repo root for the target vision.*
