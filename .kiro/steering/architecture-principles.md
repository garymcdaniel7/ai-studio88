---
inclusion: always
---

# Architecture Principles

These principles govern all design decisions. When in doubt, prefer the simpler, more explicit option.

## 1. Layered architecture — no layer skipping

```
Router → Service → Repository/DB
       → External Service (B2, Vast.ai, ComfyUI)
```

- Routers only: validate input, call service, return response
- Services only: business logic, orchestration, no direct DB access
- Repositories: all DB queries — never raw SQL in services
- Never import DB models directly into routers

## 2. Async all the way

- All FastAPI endpoints are `async def`
- All database queries use SQLAlchemy async
- All HTTP calls use `httpx.AsyncClient` or `aiohttp`
- Blocking operations (file I/O, model loading) run in `asyncio.run_in_executor`

## 3. Explicit over implicit

- No magic: no globals, no monkey-patching, no framework tricks
- Dependency injection via FastAPI `Depends()` — never module-level globals except `settings`
- All configuration via `Settings` class — never `os.environ` directly in application code

## 4. Fail fast, fail loud

- Validate at the boundary (Pydantic schemas on input)
- Never swallow exceptions silently
- Every exception gets logged with context (job_id, org_id, user_id)
- Return structured error responses: `{"detail": "...", "code": "ERROR_CODE"}`

## 5. Tenant isolation is a hard constraint

- Every database table has `org_id UUID NOT NULL`
- Supabase RLS policies enforce isolation at the DB level
- Service layer re-validates `org_id` on every mutation
- Never pass raw user-supplied UUIDs to DB queries without validation

## 6. GPU jobs are ephemeral

- GPU instances are created per-job and terminated on completion
- Never store state on GPU instances — everything goes to B2 or Supabase
- Jobs must be idempotent — retrying a failed job should be safe
- Always set a job timeout — no runaway GPU costs

## 7. API-first

- Every feature ships with an API endpoint before any UI
- All side effects are triggered via explicit API calls — no cron magic
- Webhooks for async results — never poll from the GPU worker

## 8. Schema evolution over big rewrites

- Additive changes only for backward compatibility
- Deprecate fields before removing them
- Version the API (v1, v2) — never break existing clients
