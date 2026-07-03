---
inclusion: always
---

# Developer Workflow

## Daily workflow

```bash
# Start the day
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/AI-<ticket>-<description>

# Start services
supabase start
docker compose up -d redis

# Start API in watch mode
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Verify everything
./verify_environment.sh
```

## Before committing

```bash
ruff check backend/
black backend/
pytest backend/tests/unit/ -v
pre-commit run --all-files
```

## Commit format

```
feat(talent): add LoRA model association endpoint
fix(auth): handle expired JWT gracefully
chore(deps): upgrade fastapi to 0.115.6
docs(api): update talent endpoint examples
test(jobs): add unit tests for job cancellation
```

## PR checklist

- [ ] Tests written and passing
- [ ] Linting passes (`ruff check` + `black --check`)
- [ ] No secrets in code
- [ ] Migration includes downgrade function
- [ ] CHANGELOG.md updated for notable changes

## Common commands

```bash
# Create migration
cd backend && alembic revision --autogenerate -m "describe_change"

# Apply migrations
cd backend && alembic upgrade head

# Check types
mypy backend/app

# Format and lint
black backend/ && ruff check --fix backend/

# Supabase local DB UI
supabase studio   # http://localhost:54323

# Celery: inspect queue
celery -A app.workers.celery_app inspect active
```

## GPU job testing locally

1. Run ComfyUI locally or via Docker image
2. Set `COMFYUI_BASE_URL=http://localhost:8188` in `.env`
3. `APP_ENV=development` skips Vast.ai provisioning and uses local ComfyUI
