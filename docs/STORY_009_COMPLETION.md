# Story 009 — Service-Role Authorization Boundary

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## All Service-Role Creation/Usage Points

### Single client creation point

| Location | Mechanism | Purpose |
|----------|-----------|---------|
| `backend/database.py` | `get_supabase_client()` + `_LazySupabaseProxy` | Creates Supabase client with `SUPABASE_SERVICE_ROLE_KEY` |

### Legitimate privileged usage (NOT requiring boundary)

| File | Justification |
|------|---------------|
| `backend/app/core/auth_middleware.py` | Uses SERVICE_ROLE_KEY to validate tokens via Supabase auth endpoint — auth verification, not data access |
| `backend/membership.py` | Queries `org_members` scoped by `user_id` — the membership resolver itself |
| `backend/infrastructure/admin_settings.py` | Connectivity health probe — no tenant data accessed |

### Raw usage inventory (44 files grandfathered)

**19 files with `_db()` pattern:**
aios/decisions.py, aios/governance/queue.py, aios/knowledge/graph.py, aios/knowledge/memory.py, aios/knowledge/workflow_dna.py, aios/sessions.py, aios/workflow/intelligence.py, asset_intelligence/router.py, audio/router.py, brain/router.py, cinematic/router.py, company/router.py, object_intelligence/router.py, performance/router.py, publishing/oauth.py, publishing/router.py, training/router.py, video/router.py

**Direct inline imports (13 additional files):**
api_v1.py, infrastructure/router.py, infrastructure/cost_intelligence.py, infrastructure/fleet_settings.py, infrastructure/sse_progress.py, intelligence_engine/context.py, brain/rag.py, production_intelligence/router.py, autonomous_studio/orchestrator.py, engine/lora_injector.py, aios/gateway.py, aios/obaluaye/monitor.py, aios/obaluaye/recovery.py, aios/mcp/server.py, aios/execution/tools.py, aios/orchestration/model_lifecycle.py, aios/orchestration/session_planner.py, aios/orchestration/interceptor.py

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/data_access.py` | **NEW** | AuthorizedClient boundary — the mandatory gateway for all privileged DB ops |
| `backend/data_access_helpers.py` | **NEW** | Migration bridge (AuthUser → AuthorizedClient) for gradual adoption |
| `backend/api_v1.py` | Updated | DELETE /talent migrated to AuthorizedClient; PUT /talent now requires auth |
| `tests/unit/test_data_access.py` | **NEW** | 23 cross-tenant, role, capability, and audit tests |
| `tests/unit/test_data_access_enforcement.py` | **NEW** | 3 enforcement tests (scan for new raw usage, stale allow-list, module API) |

---

## Boundary and Context Contract

### AuthorizedClient

```python
from backend.data_access import AuthorizedClient, authorized_client

# For user requests:
client = AuthorizedClient(tenant_context)  # or authorized_client(ctx)
result = client.select("talent")
result = client.select_by_id("talent", record_id)
result = client.insert("talent", {"name": "Nova"})
result = client.update("talent", {"bio": "..."}, record_id="abc")
result = client.delete("talent", "abc")
query  = client.raw_query("assets", purpose="filter_by_tags")
```

### Rules enforced

1. **Tenant tables** (28 listed): org_id ALWAYS added to WHERE clause
2. **Record IDs alone never authorize** — org_id must match
3. **Mutations require editor+ role** for TenantContext
4. **System/Worker contexts** checked against declared capabilities
5. **raw_query()** requires explicit purpose string (audit trail)
6. **UPDATE without record_id or filters** is rejected (prevents mass mutations)
7. **Authorization failures** return "not found" — never reveal record exists in other org

### Execution Contexts

| Context | Used By | org_id Source | Role Check |
|---------|---------|--------------|------------|
| `TenantContext` | Interactive users | From org_members membership | Yes (editor+ for mutations) |
| `SystemContext` | Cron, seeds, CLI, migrations | Explicit `target_org_id` (default: SYSTEM_ORG_ID) | No (system has no role) |
| `WorkerContext` | GPU jobs, training, publishing | From job record's `org_id` | No (scoped by job ownership) |

---

## Callers Migrated

| Endpoint | Before | After |
|----------|--------|-------|
| `DELETE /api/v1/talent/{id}` | Raw `supabase.table("talent").delete().eq("id", ...)` — no auth, no org check | `AuthorizedClient.delete("talent", id)` — requires auth + org_id match |
| `PUT /api/v1/talent/{id}` | No auth dependency at all | Now requires `require_auth` (auth enforced, boundary migration TODO) |

---

## System/Worker Context Rules

### SystemContext

```python
ctx = SystemContext(
    purpose="seed_default_models",     # REQUIRED — audit trail
    actor="cli:seed",                  # REQUIRED — who/what is acting
    target_org_id=str(SYSTEM_ORG_ID),  # Default: system org
    capabilities=frozenset(),          # Empty = unrestricted
)
```

- Never uses zero-UUID — uses explicit SYSTEM_ORG_ID (`00000000-0000-0000-0000-000000000001`)
- Actor is logged for attribution (e.g., "cron:publish_scheduled", "cli:seed", "migration:029")
- Can target any org explicitly (for admin operations on customer data)

### WorkerContext

```python
ctx = WorkerContext(
    job_id="job-123",                  # REQUIRED — the executing job
    org_id="org-abc",                  # REQUIRED — job owner's org
    user_id="user-456",               # REQUIRED — who submitted the job
    purpose="image_generation:flux",   # REQUIRED — what's happening
    capabilities=frozenset({"read:assets", "write:assets"}),  # Narrow scope
)
```

- Scoped to the job's org — cannot access other tenants
- Capabilities restrict which tables/operations are allowed
- Auto-generates `request_id` (wrk-{uuid}) for audit correlation

---

## Enforcement Added

### Test: `test_no_new_raw_supabase_usage`

Scans all `*.py` files under `backend/` for patterns:
- `supabase.table(`
- `_db().table(`
- `from backend.database import supabase`

Any file NOT in `ALLOWED_RAW_USAGE` fails the test. This prevents regression — new code MUST use AuthorizedClient.

### Test: `test_allowed_files_still_exist`

Detects stale entries in the allow-list (files deleted but not removed from the list).

### Test: `test_data_access_module_exports`

Verifies the boundary module exports the complete public API.

---

## Authorization and Cross-Tenant Tests

**26 tests, all passing:**

| Category | Tests | Proves |
|----------|-------|--------|
| TenantAuthorizedAccess | 4 | select/insert/update/delete all scope by org_id |
| CrossTenantIsolation | 2 | Record in another org returns "not found" (no leak) |
| RoleEnforcement | 4 | Viewer blocked from mutations; editor allowed |
| SystemContext | 4 | Requires purpose/actor; factory works; no role check |
| WorkerContext | 3 | Requires job_id/org_id; scoped to job's org |
| CapabilityEnforcement | 2 | Restricted caps block; allowed caps pass |
| AuditTrail | 1 | Operations produce audit entries |
| EdgeCases | 3 | Bulk update rejected; raw_query requires purpose; system tables exempt |
| Enforcement | 3 | No new raw usage; stale entries detected; module API complete |

---

## Audit Behavior

- Every operation through AuthorizedClient records an `AuditEntry`
- Fields: timestamp, request_id, actor, org_id, context_kind, table, operation, purpose, authorized, denial_reason
- Current: in-memory ring buffer (1000 entries) with `get_recent_audit_entries()` API
- Future: flush to `audit_log` DB table for production observability

---

## Remaining Raw Usages (Grandfathered)

44 files still use raw `supabase.table()` or `_db().table()`. Each is tracked in `ALLOWED_RAW_USAGE` in the enforcement test. Migration priority:

| Priority | Files | Reason |
|----------|-------|--------|
| High | api_v1.py (remaining 4 locations) | Core user endpoints |
| High | training/router.py | Handles user-submitted training jobs |
| Medium | infrastructure/router.py | Service settings + worker sessions |
| Medium | company/router.py | Organization CRUD |
| Low | aios/* (12 files) | Internal AI operations, less external attack surface |
| Low | audio/video/cinematic routers | Feature-specific, lower risk |

---

## Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| `DELETE /talent/{id}` now requires auth | Previously accessible without token | Correct behavior — was a security bug |
| `PUT /talent/{id}` now requires auth | Previously accessible without token | Correct behavior — was a security bug |
| AuthorizedClient.delete raises AuthorizationError on cross-tenant | Code depending on delete returning empty for wrong-org records needs try/catch | Consistent with desired behavior |

---

## Rollout Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Dev mode (AUTH_DEV_MODE=true) loses ability to delete/update talent without token | Low | Dev mode users need to either use the dev bypass login or set up org_members |
| Enforcement test may break if someone adds a new file with raw access | Low | Intentional — forces awareness and review |
| allow-list in enforcement test needs maintenance as files are renamed/deleted | Low | `test_allowed_files_still_exist` catches stale entries |
| Audit ring buffer is in-memory only | Medium | Acceptable for now; production story should flush to DB |

---

## Follow-up Stories

| Story | Description |
|-------|-------------|
| Migrate api_v1.py remaining endpoints | Move search, list-generations, get-scene behind boundary |
| Migrate training/router.py | Training endpoints handle user-submitted jobs — high priority |
| Migrate infrastructure/router.py | Service settings and worker session persistence |
| Migrate company/router.py | Organization/team CRUD (Story 005 made org_members canonical) |
| Migrate AIOS subsystem | 12 files in aios/ — lower priority but broad surface |
| Audit persistence | Flush AuditEntry records to a `data_access_audit` table |
| Pre-commit hook | Add a pre-commit check (faster than pytest) for raw usage patterns |
| Deprecate `_db()` pattern | Replace all 19 `_db()` helpers with AuthorizedClient imports |
