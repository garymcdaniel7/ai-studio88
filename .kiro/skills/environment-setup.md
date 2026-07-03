# Skill: Environment Setup from Scratch

## Purpose

Set up a complete local development environment for AI Studio on a fresh macOS machine.

## Prerequisites

- macOS 13+ (Apple Silicon or Intel)
- Git (comes with macOS)
- Internet access
- Supabase project with `projects` and `talent` tables

## Steps

### 1. Clone the repo

```bash
git clone https://github.com/garymcdaniel7/ai-studio88.git
cd ai-studio88
```

### 2. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Add to PATH (restart shell or run):
source ~/.local/bin/env
```

### 3. Create virtual environment with Python 3.12

```bash
uv venv .venv --python 3.12
```

uv downloads Python 3.12 automatically if not present on the system.

### 4. Install dependencies

```bash
uv pip install -r requirements.txt --python .venv/bin/python
```

### 5. Create .env from template

```bash
cp .env.example .env
# Edit .env — fill in at minimum:
#   SUPABASE_URL=https://your-project.supabase.co
#   SUPABASE_SERVICE_ROLE_KEY=eyJ...  (from Supabase Dashboard → Settings → API)
```

### 6. Start the server

```bash
uv run uvicorn backend.main:app --reload
```

### 7. Verify

```bash
curl http://localhost:8000/         # → {"status":"ok"}
curl http://localhost:8000/talent   # → talent records from Supabase
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `uv: command not found` | Add `~/.local/bin` to PATH: `export PATH="$HOME/.local/bin:$PATH"` |
| `RuntimeError: Missing SUPABASE_URL` | Create `.env` with real credentials (see step 5) |
| `ModuleNotFoundError` | Ensure you're running from the repo root, not inside `backend/` |
| Python 3.7 being used | uv manages its own Python — use `uv run` or activate `.venv` |

## What's installed

The `requirements.txt` provides:
- `fastapi` — web framework
- `uvicorn[standard]` — ASGI server with hot reload
- `python-dotenv` — .env file loading
- `supabase` — Supabase Python client
- `boto3` — AWS/B2 S3-compatible storage
- `requests` — HTTP client
- `streamlit` — (future dashboard prototyping)
