# Design Review — Corrections from @ai-studio + @cto

**Team:** @ai-studio (production pipeline), @cto (infrastructure), @hermes (product)
**Date:** 2026-10-04
**Target:** `design.md` and `bugfix.md` in this directory

---

## 🔴 Must-Fix Before Implementation

### 1. Worker Path Undercovered (HIGH)
**design.md** lines 298-327 (Repository-Wide Query Audit Method) must explicitly name `backend/worker.py`.

The worker (`backend/worker.py`) uses service-role Supabase credentials and polls the `jobs` table DIRECTLY — it bypasses the HTTP middleware (`AuthMiddleware`) entirely. After the fix, application-layer org predicates are the ONLY isolation for the worker. The current sweep scope names `api_v1.py`, `training/router.py`, and `production_intelligence/router.py` explicitly but only implies "workers, scripts" in the generic language.

**Fix:** Add `backend/worker.py` to the named scope alongside `api_v1.py`, `training/router.py`, and `production_intelligence/router.py`. The worker's `supabase.table('jobs')` calls (claim, complete, fail) must each have `.eq("org_id", ...)`. Missing even one exposes all jobs cross-tenant.

### 2. CORS/OPTIONS Preflight Exemption (MEDIUM)
**design.md** lines 249-261 (AuthMiddleware behavior) — OPTIONS preflight requests carry no `Authorization` header. `AuthMiddleware` must not reject OPTIONS before CORS handles it.

**Fix:** Add OPTIONS to the `PUBLIC_PROBE_ALLOWLIST` or exempt it explicitly in middleware logic. The middleware ordering diagram shows "CORS/transport handling" first — confirm this in code.

### 3. `optional_auth` Null-Org 500s (MEDIUM)
**bugfix.md** clause 2.5 and **design.md** lines 284-294 (Application-Layer Tenant Scoping) — Endpoints with `Depends(optional_auth)` can 500 when `org_id=None` is passed to downstream validation.

**Fix:** The tenant sweep must verify every `optional_auth`-guarded path handles the null-org case without raising. The design's decision tree (direct/inherited/system/ambiguous) should include null-org as an explicit rejection case, not a pass-through.

### 4. Rollback Doctrine — Forward-Only (HIGH — ops risk)
**design.md** lines 402-407 (Rollout and Rollback) — The design correctly says you cannot flip enforcement off in production. But it doesn't say what happens when a deploy engineer at 3AM tries to roll back to a pre-enforcement release.

**Fix:** Make the rollout section explicit:
> *Rollback to a release without auth enforcement is NOT a rollback — it re-exposes the defect. The only safe rollback is to the immediately prior release that ALSO has enforcement. If no such release exists, fix forward, restrict traffic, or shed load. Do not flip `AUTH_ENFORCEMENT_FLIP` from true to false in staging or production.*

### 5. Allowlist Derivation (MEDIUM)
**design.md** line 205 — `PUBLIC_PROBE_ALLOWLIST` as a frozen set of exact paths is correct, but it must include EVERY unauthenticated bootstrap route. The design lists `/auth/google`, `/auth/login`, `/auth/callback`, `/auth/logout` — if one is missed, frontend auth breaks at the first redirect.

**Fix:** Add an integration test that asserts every unauthenticated route in production matches the allowlist. Or derive the list from the router table rather than maintaining by hand.

---

## ⚠️ Should-Fix

### 6. Load Testing (MEDIUM)
**design.md** — No load test or benchmark is mentioned. `AuthMiddleware` now runs on every request (JWT decode + policy resolution + structured event emission).

**Fix:** Add a before/after latency comparison under representative load. Under light load this is nothing; under sustained load it adds per-request latency that should be measured before production deployment.

### 7. Coverage Target Precision (LOW)
**design.md** line 557 — "80% coverage target for new code" should be branch-coverage on critical paths (enforcement/fallback/allowlist/error), not line coverage.

**Fix:** Change to "80% branch coverage on enforcement, fallback, allowlist, and error paths; 80% line coverage on all new code."

---

## 📋 For Reference — What the Team Approved

| Item | Verdict |
|---|---|
| Middleware order (AuthMiddleware → OrgIdInjectionGuard) | ✅ Correct |
| AuthPolicy single module | ✅ Sound |
| Tenant sweep methodology | ✅ Exhaustive — but add worker.py (see above) |
| Dark launch approach | ✅ Sound |
| Staging gates / CTO ownership | ✅ Well-defined |
| Bugfix EARS format | ✅ Standards-compliant |

The design is high quality. Fix the 5 items above and proceed to implementation.