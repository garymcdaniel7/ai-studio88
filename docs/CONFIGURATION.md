# Configuration & Environment Profiles

## Overview

AI Studio uses typed, validated configuration with environment profiles. The system rejects unsafe settings before accepting traffic — production will not start with placeholder secrets, localhost dependencies, or simulation modes.

## Profiles

| Profile | `APP_ENV` value | Purpose |
|---------|----------------|---------|
| Local | `local` (or `development`) | Developer workstation. All defaults are safe. Warnings only. |
| Test | `test` | CI/testing. Allows placeholders. No production constraints. |
| Staging | `staging` | Pre-production. Same constraints as production. |
| Production | `production` | Live deployment. Fails fast on any unsafe config. |

## Startup Behavior

```
APP_ENV=local       → Validate, warn on issues, start anyway
APP_ENV=test        → Validate, minimal constraints, start
APP_ENV=staging     → Validate, reject unsafe config, refuse to start
APP_ENV=production  → Validate, reject unsafe config, refuse to start
```

## Required Variables by Profile

### All Profiles (minimum)

| Variable | Description |
|----------|-------------|
| `APP_ENV` | Profile selector (default: `local`) |

### Production / Staging (required)

| Variable | Constraint |
|----------|-----------|
| `SECRET_KEY` | Real value, min 32 chars, not a placeholder |
| `SUPABASE_URL` | Real URL, not localhost |
| `SUPABASE_SERVICE_ROLE_KEY` | Not empty, not a placeholder |
| `SUPABASE_JWT_SECRET` | Not empty, not a placeholder |
| `SUPABASE_ANON_KEY` | Not empty, not a placeholder |
| `DATABASE_URL` | Real URL, not localhost |
| `REDIS_URL` | Real URL, not localhost |
| `API_BASE_URL` | Real URL, not localhost |
| `B2_KEY_ID` | Not empty, not a placeholder |
| `B2_APPLICATION_KEY` | Not empty, not a placeholder |
| `AUTH_REQUIRED` | Must be `true` |
| `DEBUG` | Must be `false` |
| `GENERATION_PROVIDER` | Cannot be `simulation` |
| `ALLOWED_ORIGINS` | Cannot contain `*` |

### Optional Capabilities

These are not required but enhance functionality:

| Variable | Enables |
|----------|---------|
| `VAST_API_KEY` or `RUNPOD_API_KEY` | GPU workers (required if GENERATION_PROVIDER != simulation) |
| `HF_TOKEN` | Faster HuggingFace downloads + gated models |
| `ELEVENLABS_API_KEY` + `ELEVENLABS_LIVE=true` | Real voice generation |
| `OPENAI_API_KEY` | Cloud LLM fallback |
| `VERCEL_TOKEN` | Deployment automation |
| `STRIPE_SECRET_KEY` | Billing |

## Unsafe Defaults Rejected in Production

| Check | Error |
|-------|-------|
| Placeholder values (e.g., `your-xxx`, `change_me`) | "contains a placeholder value" |
| Localhost URLs | "points to localhost — not allowed" |
| `DEBUG=true` | "DEBUG must be false in production" |
| `AUTH_REQUIRED=false` | "AUTH_REQUIRED must be true" |
| `GENERATION_PROVIDER=simulation` | "cannot be 'simulation' in production" |
| `ALLOWED_ORIGINS=*` | "cannot contain '*' in production" |
| Missing GPU provider with real generation | "GPU provider required" |
| Short SECRET_KEY (< 32 chars) | "must be at least 32 characters" |

## Endpoints

### `GET /health` — Liveness

Always returns 200 if the process is accepting connections.

```json
{"status": "ok"}
```

### `GET /ready` — Readiness

Returns 200 if critical capabilities are configured, 503 otherwise.

```json
{
  "ready": true,
  "profile": "local",
  "version": "0.1.0",
  "capabilities": [
    {"name": "database", "status": "configured", "message": "Supabase URL set"},
    {"name": "storage", "status": "configured", "message": "B2 credentials set"},
    {"name": "gpu", "status": "configured", "message": "Vast.ai API key set"},
    {"name": "generation", "status": "degraded", "message": "Running in simulation mode"},
    {"name": "llm", "status": "configured", "message": "Ollama (dolphin-llama3:8b)"},
    {"name": "voice", "status": "configured", "message": "ElevenLabs live"},
    {"name": "training", "status": "degraded", "message": "Training in simulation mode"},
    {"name": "auth", "status": "configured", "message": "JWT validation configured"},
    {"name": "queue", "status": "configured", "message": "Redis URL set"}
  ]
}
```

### `GET /ready/capabilities` — Detailed Breakdown

```json
{
  "profile": "local",
  "capabilities": {
    "database": {"status": "configured", "message": "..."},
    "storage": {"status": "configured", "message": "..."}
  },
  "summary": {
    "total": 9,
    "ready": 0,
    "configured": 6,
    "degraded": 2,
    "unavailable": 1
  }
}
```

## Capability Statuses

| Status | Meaning |
|--------|---------|
| `ready` | Configured AND verified working (live check passed) |
| `configured` | Credentials/settings present, not yet verified |
| `degraded` | Running in a limited mode (e.g., simulation) |
| `unavailable` | Not configured — feature disabled |

## Error Messages

Error messages identify the variable name and required action without exposing secret values:

```
FATAL: Configuration validation failed:
  - SECRET_KEY contains a placeholder value — set a real credential
  - REDIS_URL points to localhost — not allowed in production
  - GENERATION_PROVIDER cannot be 'simulation' in production
```

## Adding New Variables

1. Add the field to `backend/app/core/config.py` in the `Settings` class
2. Add appropriate default (empty string for optional secrets)
3. If required in production, add a check in `_validate_production()`
4. If it enables a capability, add a status check in `get_capability_status()`
5. Add to `.env.example` with a descriptive placeholder
6. Update this document

## File Locations

| File | Purpose |
|------|---------|
| `backend/app/core/config.py` | Settings class, profiles, validation |
| `backend/app/core/readiness.py` | `/health` and `/ready` endpoints |
| `backend/main.py` | Startup validation (crashes early if invalid) |
| `tests/unit/test_core/test_config.py` | 39 unit tests |
| `.env.example` | Template with all variables |
| `.env` | Local overrides (gitignored) |
