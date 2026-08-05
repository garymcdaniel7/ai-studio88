# Story 015 — Asset & Job Authorization Hardening

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## Summary

Hardened all asset and generation-job endpoints with mandatory authentication, workspace-scoped access via AuthorizedClient, cross-tenant isolation, and audit trails for destructive/spend-affecting operations. **8 endpoints migrated from zero-auth to full tenant isolation.**

---

## Endpoint Inventory & Authorization Status

### Asset Endpoints (6 total)

| Route | Before | After | Auth | Org-Scoped | Audited |
|-------|--------|-------|:---:|:---:|:---:|
| GET /assets | optional_auth | optional_auth | ✅ | Partial | — |
| GET /assets/{id} | **NONE** | require_auth | ✅ | ✅ | — |
| GET /assets/{id}/file | **NONE** | require_auth | ✅ | ✅ | — |
| POST /assets (upload) | NONE | NONE | ❌ UNVERIFIED | — | — |
| POST /assets/save-generation | require_auth | require_auth | ✅ | — | — |
| DELETE /assets/{id} | **NONE** | require_auth | ✅ | ✅ | ✅ |

### Job Endpoints (6 total)

| Route | Before | After | Auth | Org-Scoped | Audited |
|-------|--------|-------|:---:|:---:|:---:|
| GET /jobs | **NONE** | require_auth | ✅ | ✅ | — |
| GET /jobs/{id} | **NONE** | require_auth | ✅ | ✅ | — |
| POST /jobs | NONE | NONE | ❌ UNVERIFIED | — | — |
| DELETE /jobs/{id} | **NONE** | require_auth | ✅ | ✅ | ✅ |
| POST /jobs/{id}/cancel | **NONE** | require_auth | ✅ | ✅ | ✅ |
| POST /jobs/{id}/retry | **NONE** | require_auth | ✅ | ✅ | ✅ |

### Generation Endpoints (UNVERIFIED — not migrated in this story)

| Route | Auth | Note |
|-------|:---:|------|
| POST /generation/run | ❌ | Triggers GPU spend — HIGH priority for next story |
| GET /generation/history | ❌ | Returns all generations globally |
| POST /generation/{id}/cancel | ❌ | Duplicates /jobs/{id}/cancel |
| POST /generation/{id}/retry | ❌ | Duplicates /jobs/{id}/retry |
| GET /generation/{id}/status | ❌ | Bare ID lookup |

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/asset_job_auth.py` | **NEW** | Centralized auth helpers + destructive action audit |
| `backend/api_v1.py` | Updated | 8 endpoints hardened with require_auth + AuthorizedClient |
| `tests/unit/test_asset_job_auth.py` | **NEW** | 17 two-tenant isolation tests |

---

## Authorization Rules

| Operation | Rule |
|-----------|------|
| Read asset/job | Must be authenticated + asset/job org_id matches user's org |
| Delete asset | Requires auth + org match + audit entry recorded |
| Cancel job | Requires auth + org match + job in cancellable state + audit |
| Retry job | Requires auth + org match + job in retryable state + audit |
| Delete job | Requires auth + org match + job NOT running + audit |
| File serving | Requires auth + org match BEFORE any bytes are served |

**Cross-tenant behavior:** If a record belongs to another org, the org_id filter returns empty → response is always 404 "not found" (never reveals existence).

---

## Audit Events

| Action | Resource | Fields Recorded |
|--------|----------|----------------|
| `delete_asset` | asset | actor_user_id, email, org_id, resource_id, filename |
| `cancel_job` | job | actor_user_id, email, org_id, resource_id, job_type, prev_status |
| `retry_job` | job | actor_user_id, email, org_id, resource_id, job_type, prev_status |
| `delete_job` | job | actor_user_id, email, org_id, resource_id, job_type |

Audit entries stored in memory (ring buffer, 500 entries). Production flush to DB table planned.

---

## Tests & Results

```
pytest tests/unit/test_asset_job_auth.py -v
======================= 17 passed in 0.18s ========================
```

| Test Class | Tests | Proves |
|-----------|-------|--------|
| TestAssetReadIsolation | 2 | Own-org read OK; cross-tenant → 404 |
| TestAssetDeleteAuth | 3 | Own delete OK; cross-tenant → 404; audit produced |
| TestJobReadIsolation | 2 | Own-org read OK; cross-tenant → 404 |
| TestJobCancelAuth | 3 | Cancel queued OK; completed blocked; cross-tenant → 404 |
| TestJobRetryAuth | 4 | Retry failed OK; running blocked; cross-tenant → 404; audit |
| TestJobDeleteAuth | 3 | Delete queued OK; running blocked; cross-tenant → 404 |

---

## Unresolved UNVERIFIED Routes

| Route | Risk | Reason |
|-------|------|--------|
| POST /assets (upload) | Medium | File upload without auth — could be intentional for anonymous drops or a gap |
| POST /jobs (create) | Medium | Job creation without auth — triggers resource allocation |
| POST /generation/run | **HIGH** | Triggers GPU compute spend without any auth |
| GET /generation/history | Medium | Returns all generation history globally |
| POST /generation/{id}/cancel | Low | Duplicates /jobs/{id}/cancel which IS now protected |
| POST /generation/{id}/retry | Low | Duplicates /jobs/{id}/retry which IS now protected |
| GET /generation/{id}/status | Low | Bare ID status lookup |

---

## Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| GET /assets/{id} now requires auth | Frontend must send token | Frontend api.ts already sends auth headers |
| GET /assets/{id}/file now requires auth | Image/video display needs token | Frontend fetches via authenticated client |
| DELETE /assets/{id} now requires auth | Unauthenticated delete blocked | Correct — was a security bug |
| GET /jobs, GET /jobs/{id} now require auth | Unauthenticated job listing blocked | Correct — was a security bug |
| DELETE/cancel/retry jobs now require auth | Unauthenticated lifecycle ops blocked | Correct — was a security bug |

**Dev mode note:** With `AUTH_DEV_MODE=true`, the `require_auth` dependency returns a dev user with `org_id=None`. When `org_id` is None, the `get_authorized_client()` helper returns None and falls back to unscoped access. This preserves local development without requiring org_members setup.

---

## Rollback Steps

Revert the api_v1.py changes (git revert or manual restoration of old function signatures without `user: AuthUser = Depends(require_auth)` parameter).

The `backend/asset_job_auth.py` module can be deleted — it's only imported lazily within routes.

---

## Risks & Follow-ups

| Risk | Severity | Follow-up |
|------|----------|-----------|
| POST /generation/run has no auth (GPU spend risk) | HIGH | Next hardening story |
| POST /assets upload has no auth | Medium | Evaluate if anonymous upload is intentional |
| POST /jobs create has no auth | Medium | Should require auth — next story |
| Generation endpoints duplicate job lifecycle | Low | Consolidate cancel/retry to single path |
| Audit is in-memory only | Medium | Flush to DB table in production story |
| Worker callbacks need separate auth path | Medium | WorkerContext from Story 009 available |
