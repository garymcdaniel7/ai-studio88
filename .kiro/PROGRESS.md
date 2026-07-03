# AI Studio — Progress Log

> This file tracks what has been completed, what's working, and what comes next.
> Updated after each significant milestone to help new sessions pick up context fast.

---

## Current State (2026-07-03)

**Status:** Phase 1 — Foundation (in progress)

### What's working

| Component | Status | Notes |
|---|---|---|
| FastAPI server | ✅ Running | `uv run uvicorn backend.main:app --reload` from repo root |
| Supabase connection | ✅ Connected | Live data flowing (projects, talent) |
| `GET /` | ✅ | Health check → `{"status":"ok"}` |
| `GET /projects` | ✅ | Returns projects from Supabase |
| `GET /talent` | ✅ | Returns AI talent records |
| `POST /talent` | ✅ | Creates talent in Supabase |
| `GET /api/v1/health` | ✅ | V1 prefix health check |
| `GET /api/v1/projects` | ✅ | V1 prefix projects list |
| `GET /api/v1/talent` | ✅ | V1 prefix talent list |
| `POST /api/v1/talent` | ✅ | V1 prefix talent creation |
| Python 3.12 venv | ✅ | `.venv/` managed by uv |
| GitHub push | ✅ | Remote: `garymcdaniel7/ai-studio88` |
| Docs | ✅ | ARCHITECTURE, SETUP, CONTRIBUTING, ROADMAP, etc. |
| CI pipeline | ✅ | `.github/workflows/ci.yml` (lint, test, security, docker) |
| Steering files | ✅ | 12 files in `.kiro/steering/` |
| Skill files | ✅ | 9 files in `.kiro/skills/` |

### Repository layout

```
ai-studio88/
├── backend/
│   ├── main.py              ← Entry point (uvicorn target)
│   ├── api_v1.py            ← V1 router wrapping Supabase functions
│   ├── database.py          ← Supabase client (working)
│   ├── config.py            ← (empty, future use)
│   ├── gpu.py               ← (stub)
│   ├── jobs.py              ← (stub)
│   ├── storage.py           ← (stub)
│   ├── pyproject.toml       ← Full deps + dev tools config
│   └── app/                 ← Layered scaffold (future)
│       ├── core/            ← config, security, dependencies, logging
│       ├── api/v1/endpoints/← typed endpoints (auth-gated, not connected yet)
│       ├── db/              ← SQLAlchemy async session + base models
│       ├── schemas/         ← Pydantic DTOs
│       ├── models/          ← (empty, future ORM models)
│       ├── services/        ← (empty, future business logic)
│       └── workers/         ← (empty, future Celery tasks)
├── worker/worker.py         ← (stub)
├── infrastructure/          ← Dockerfile, nginx config
├── .github/workflows/       ← CI pipeline
├── .kiro/                   ← Steering + skills for AI dev
├── .env.example             ← Template (safe to commit)
├── .env                     ← Real secrets (gitignored)
├── docker-compose.yml       ← Full local stack definition
├── bootstrap.sh             ← One-command dev setup
└── verify_environment.sh    ← Health check script
```

### How to start the server

```bash
cd /Users/garymcdaniel/kiro/ai-studio88
/Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --reload
```

Or with the venv activated:
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

### Git history

```
4be07de Connect v1 API scaffold to working backend
69f7b53 Bootstrap AI Studio platform foundation
0e6ab4f Add AI Studio backend foundation
c9c8a0d Initial commit
```

---

## What's next (immediate priorities)

1. **Implement Supabase JWT auth middleware** — validate tokens on protected endpoints
2. **Wire up the full v1 scaffold** — replace stub endpoints with real Supabase queries
3. **Add Backblaze B2 upload** — implement `backend/storage.py` using `StorageService`
4. **Add Vast.ai GPU provisioning** — implement `backend/gpu.py`
5. **Celery + Redis** — job queue for async generation tasks
6. **Docker Compose up** — get full stack running in containers
7. **First ComfyUI workflow** — end-to-end image generation job

---

## Environment requirements

| Tool | Version | How installed |
|---|---|---|
| uv | 0.11.26 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.12.13 | Downloaded by uv automatically |
| Git | 2.39.5 | Apple built-in |
| macOS | 15.6.1 | — |

Missing (install via `./bootstrap.sh` when ready):
- Homebrew, Docker, Node.js, Supabase CLI, ffmpeg, ImageMagick, gh CLI

---

## Decisions made

1. **Keep flat `backend/main.py` as entry point** — existing Supabase queries work, no need to force migration yet
2. **v1 scaffold is opt-in** — lives in `backend/app/` but only connected via `backend/api_v1.py` currently
3. **Apache 2.0 license** — open source, kept from original repo
4. **uv for package management** — faster than pip, manages Python versions too
5. **`.env` never committed** — `.env.example` is the template
