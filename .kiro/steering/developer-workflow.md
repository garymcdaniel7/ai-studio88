---
inclusion: always
---

# Developer Workflow

## Starting the server (current working method)

```bash
cd /Users/garymcdaniel/kiro/ai-studio88
/Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --reload
```

Or activate venv first:
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

API docs: http://localhost:8000/docs

## Current endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/projects` | List projects (Supabase) |
| GET | `/talent` | List AI talent (Supabase) |
| POST | `/talent` | Create talent (Supabase) |
| GET | `/api/v1/health` | V1 health check |
| GET | `/api/v1/projects` | V1 projects list |
| GET | `/api/v1/talent` | V1 talent list |
| POST | `/api/v1/talent` | V1 talent create |

## Key files

- `backend/main.py` — entry point, mounts root + v1 endpoints
- `backend/api_v1.py` — v1 router (same Supabase functions, versioned prefix)
- `backend/database.py` — Supabase client, all DB functions live here currently
- `.env` — real credentials (never commit)
- `.env.example` — template (safe to commit)

## Before committing

```bash
git status                     # Check what's changed
git diff                       # Review changes
# Ensure .env is NOT in the list
git add <specific files>       # Stage only intended files
git commit -m "type(scope): description"
git push origin main
```

## Commit format

```
feat(talent): add LoRA model association endpoint
fix(auth): handle expired JWT gracefully
chore(deps): upgrade fastapi to 0.115.6
```

## Adding a new Supabase-backed endpoint

1. Add the query function to `backend/database.py`
2. Add the route to `backend/main.py` (root level) AND `backend/api_v1.py` (v1 prefix)
3. Test with curl
4. Commit

## Future: migrating to the full scaffold

When ready to add auth/ORM/services:
1. Implement the feature in `backend/app/services/`
2. Wire it to `backend/app/api/v1/endpoints/`
3. Remove the corresponding route from `backend/api_v1.py`
4. The root-level routes in `main.py` can stay as backward-compatible aliases

## Environment

- `uv` at `~/.local/bin/uv`
- Python 3.12.13 in `.venv/`
- All deps from `requirements.txt` installed in `.venv/`
- Supabase project: `vipmjgglascthwoqqqji.supabase.co`
