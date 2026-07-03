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
- **Phase:** 1 — Foundation (basic CRUD working, scaffold in place)

## Architecture (current)

```
backend/main.py         ← FastAPI app (entry point)
backend/api_v1.py       ← /api/v1/* router (Supabase direct)
backend/database.py     ← Supabase client + query functions
backend/app/            ← Future layered scaffold (not yet connected to live app)
```

The app currently uses the Supabase Python client directly (no ORM, no SQLAlchemy).
The `backend/app/` scaffold is prepared for when we add auth, ORM, and services.

## Working endpoints

- `GET /` — health
- `GET /projects` — Supabase projects table
- `GET /talent` — Supabase talent table
- `POST /talent` — create talent record
- `GET /api/v1/health` — v1 health
- `GET /api/v1/projects` — v1 projects
- `GET /api/v1/talent` — v1 talent list
- `POST /api/v1/talent` — v1 talent create

## Key constraints

- `.env` is gitignored — never commit it
- The server must run from the repo root (imports use `backend.` prefix)
- `backend/app/` scaffold imports use `app.` prefix (only usable when running from inside `backend/`)
- The two systems coexist but aren't fully integrated yet

## What's NOT done yet

- No authentication (all endpoints are public)
- No SQLAlchemy ORM (using Supabase client directly)
- No Celery/Redis (no async job processing)
- No B2 storage implementation
- No GPU provisioning
- No Docker Compose running (config exists but not tested)
- No frontend

## See also

- `.kiro/PROGRESS.md` — detailed progress log with git history
- `ROADMAP.md` — full 8-phase feature roadmap
- `ARCHITECTURE.md` — target architecture design
