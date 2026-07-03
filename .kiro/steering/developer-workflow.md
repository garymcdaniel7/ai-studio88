---
inclusion: always
---

# Developer Workflow

## Starting the server

```bash
cd /Users/garymcdaniel/kiro/ai-studio88
/Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --reload
```

Dashboard (16 pages):
```bash
uv run streamlit run dashboard/app.py
```

API docs: http://localhost:8000/docs

## Architecture overview

The backend has 5 mounted routers:
- `api_v1.py` — core platform (generation, models, workers, etc.)
- `creator_os/router.py` — campaigns, calendar, analytics, brands
- `autonomous_studio/router.py` — AI departments, briefing, recommendations
- `training/router.py` — LoRA training lifecycle
- `video/router.py` — video production pipeline

Plus 7 engine packages: `engine/`, `intelligence_engine/`, `execution/`,
`story_engine/`, `production/`, `creator_os/`, `autonomous_studio/`

## Adding a new feature

1. Add database functions to `backend/database.py` (or create a new router)
2. Add API endpoints (in `api_v1.py` or a dedicated router file)
3. If new router: mount in `backend/main.py`
4. Add dashboard page in `dashboard/pages/`
5. Create SQL migration in `docs/sql/`
6. Update documentation in `docs/`

## Adding a new provider

1. Create provider class implementing the appropriate interface
2. Register in the provider registry dict
3. Set env var to activate
4. No core code changes needed

## Before committing

```bash
# Verify server starts
curl http://localhost:8000/
curl http://localhost:8000/api/v1/health

# Check no secrets staged
git status
git diff --cached --name-only | grep -i env

# Commit
git add <specific files>
git commit -m "type(scope): description"
git push origin main
```

## Never commit

- `.env` (real credentials)
- API keys, secrets, tokens
- Generated media, model files, LoRA binaries
- Temporary test scripts
- `__pycache__/`, `.venv/`

## Key environment variables

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Database connection |
| `SUPABASE_SERVICE_ROLE_KEY` | Full DB access |
| `B2_KEY_ID` / `B2_APPLICATION_KEY` | Backblaze storage |
| `GENERATION_PROVIDER` | simulation or comfyui |
| `COMFYUI_BASE_URL` | Remote ComfyUI instance |
| `AI_PROVIDER` | LLM provider (simulation/openai) |
| `API_BASE_URL` | For dashboard → API calls |
