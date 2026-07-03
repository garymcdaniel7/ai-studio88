# AI Studio — Setup Guide

This guide walks you through setting up a complete local development environment from scratch.

---

## Prerequisites

- macOS 13+ or Ubuntu 22.04+ (Windows via WSL2)
- A GitHub account with repository access
- Supabase account (free tier works for development)
- Backblaze B2 account
- Vast.ai account (for GPU testing)

---

## Option A: One-Command Setup (Recommended)

```bash
git clone https://github.com/your-org/ai-studio.git
cd ai-studio
chmod +x bootstrap.sh
./bootstrap.sh
```

The bootstrap script installs all required tools and creates your virtual environment. After it completes, configure your `.env` file and you're ready to code.

---

## Option B: Manual Setup

### 1. Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install core tools

```bash
brew install git gh git-lfs node python@3.12 ffmpeg imagemagick
brew install --cask docker
brew install supabase/tap/supabase
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Install Python quality tools

```bash
pip install ruff black pytest pre-commit
```

### 4. Clone and configure

```bash
git clone https://github.com/your-org/ai-studio.git
cd ai-studio
cp .env.example .env
# Edit .env with your credentials
```

### 5. Python environment

```bash
cd backend
uv venv .venv --python python3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 6. Pre-commit hooks

```bash
pre-commit install
```

### 7. Start Supabase locally

```bash
supabase start
# This downloads and starts a local Supabase stack (takes a few minutes first run)
supabase db push   # Apply migrations
```

### 8. Start the API

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Verifying your setup

```bash
./verify_environment.sh
```

This checks every required tool, your Git state, .env variables, and optionally the running API.

---

## Environment Variables

All configuration lives in `.env`. The key groups are:

| Group | Purpose |
|---|---|
| `SUPABASE_*` | Database and auth connection |
| `DATABASE_URL` | Direct PostgreSQL connection string |
| `B2_*` | Backblaze B2 storage credentials |
| `VASTAI_API_KEY` | GPU provisioning |
| `REDIS_URL` | Job queue and caching |
| `SECRET_KEY` | JWT signing (generate with `openssl rand -hex 32`) |

See `.env.example` for all available variables with descriptions.

---

## Supabase local development

```bash
supabase start          # Start local Supabase stack
supabase status         # Show URLs and API keys
supabase db reset       # Reset database to latest migration state
supabase db push        # Apply pending migrations
supabase db diff        # Show pending schema changes
supabase stop           # Stop local stack
```

The local Supabase dashboard is available at `http://localhost:54323`.

---

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest                          # Run all tests
pytest tests/unit               # Unit tests only
pytest -v --cov=app             # With coverage
pytest -k "test_talent"         # Filter by name
```

---

## Docker Compose (full stack)

```bash
docker compose up -d            # Start all services
docker compose logs -f api      # Stream API logs
docker compose down             # Stop services
docker compose down -v          # Stop and remove volumes
```

---

## Common issues

**`supabase start` fails:**
- Ensure Docker Desktop is running
- Run `docker system prune` if disk is full

**`uv: command not found` after install:**
- Add `~/.local/bin` to your PATH: `export PATH="$HOME/.local/bin:$PATH"`

**Import errors in tests:**
- Ensure you're using the venv: `source backend/.venv/bin/activate`

**`SECRET_KEY` warning:**
- Generate one: `openssl rand -hex 32`

---

## Useful commands

```bash
# Generate a SECRET_KEY
openssl rand -hex 32

# Lint and format code
ruff check backend/
black backend/

# Run type checking
mypy backend/app

# Create a new DB migration
cd backend && alembic revision --autogenerate -m "add_talent_table"

# Apply migrations
cd backend && alembic upgrade head
```
