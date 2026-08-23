# AI Studio — UAT & Production-Readiness Report
**Date:** 2026-08-23 · **Method:** anonymous route sweep (Playwright) + authenticated sweep (real Supabase user) + backend `/ready` audit + live prod verification

---

## Executive Summary

| Area | Status |
|---|---|
| **Landing page** | ✅ Rebuilt ("whoa" front door), images fixed, deployed |
| **Auth boundary (anonymous)** | ✅ All 26 protected routes redirect to login, zero console errors |
| **Fresh-user experience** | ✅ **FIXED** — was 500 on every core page; org provisioning now wired |
| **Core authenticated pages** | ✅ `/talent`, `/`, `/models`, `/admin/*` load clean |
| **Story / Workflows pages** | ⚠️ 500 — DB schema drift (tables missing org_id / missing entirely) |
| **Production backend** | ⚠️ AUTH_DEV_MODE on, 2 routers failing, old code deployed |
| **Production frontend** | ✅ **FIXED** — NEXT_PUBLIC_API_URL was unset (all data calls failed); now points at Railway |
| **CI pipeline** | ⚠️ Frontend lint+build pass; unit/lint/audit blocked by pre-existing debt |

**Critical fixes shipped today (4 commits pushed to `main`):**
1. **Fresh signups now work** — org provisioning was built + tested but *never wired in*. First API call now auto-creates the workspace. This was THE critical bug: every new user got 500s on `/talent`, `/assets`, `/jobs`.
2. **Production frontend API URL** — was unset on Vercel, so prod data calls hit the app's own domain (404). Now points at the live Railway backend.
3. **CI dependency resolution** — `supabase==2.10.0` + `gotrue==2.9.0` + `httpx==0.28.1` were mutually incompatible; fresh CI installs failed. Aligned to the working venv (supabase 2.31, httpx 0.27, pydantic 2.13).
4. **CI tooling flags** — `next lint` (removed in Next 16), `pip-audit --severity`, `bandit -ll --severity-level` all had invalid flags; ruff now pinned to 0.8.6 for a deterministic gate.

---

## Findings by Severity

### 🔴 CRITICAL (fixed today)

**C1. Fresh signup → 500 on every core endpoint (org provisioning never wired)**
- Every new user with no org membership got 500 on `/api/v1/talent`, `/api/v1/jobs`, `/api/v1/assets`.
- Root cause: `ProvisioningService` was fully built + unit-tested, but **no endpoint, hook, or edge function ever called it**. The frontend comment promised "backend will provision the real org on first API call" — nothing did.
- **Fix:** wired `provision_workspace_sync` into `auth.py` on `MembershipError`. Verified: fresh user now gets 200s, org auto-created.
- **Bonus bug found during fix:** `_create_organization` used `owner_user_id`/`is_active` (schema drift — real table has `owner_id`, no `is_active`); `onboarding_state` table doesn't exist. Both fixed.

**C2. Production frontend had no API URL — every prod data call failed**
- `NEXT_PUBLIC_API_URL` was unset in Vercel env. In prod, `getBaseUrl()` returns `""` → data calls hit the Vercel domain itself → 404. The site rendered a shell with no data.
- **Fix:** set `NEXT_PUBLIC_API_URL=https://web-production-1f511.up.railway.app` on both `ai-studio88` + `ai-studio99`, verified baked into deployed chunks.

### 🟠 HIGH (partially fixed / needs action)

**H1. Deployed Railway backend is not prod-ready (needs redeploy from clean env)**
Live `/ready` shows:
- `AUTH_DEV_MODE enabled — auth bypassed` (security issue in prod)
- 2 routers failed to load (`notifications`, `social_analytics`) — import fine locally, env gap on Railway
- `Ollama not reachable`, `REDIS_URL not configured`, generation in simulation
- Running pre-fix code (no provisioning fix)
- **Action:** redeploy Railway from current `main` with proper env vars (`AUTH_DEV_MODE=false`, `REDIS_URL`, Ollama, CORS including `ai-studio88.vercel.app` which is currently 400-blocked).

**H2. Story + Workflows pages 500 (DB schema drift)**
- `/story` queries `universes` table — **doesn't exist** (never migrated)
- `/workflows` queries `training_jobs` with `org_id` filter — **column doesn't exist**
- **22 tenant tables** are missing `org_id` or missing entirely vs. the code's `TENANT_TABLES` list (migrations written but never applied — they even have unresolved `%%FOUNDER_ORG_ID%%` placeholders).
- **Action:** apply the pending migrations (`docs/sql/20260810_042..046`) after resolving the placeholder, and create `universes` + `onboarding_state`.

### 🟡 MEDIUM

**M1. Queue degraded** — `redis` package not installed in venv though pinned. **FIXED** (installed `redis==5.2.1`; `/ready` now shows `queue: ready`).

**M2. AI Brain has no model** — `OLLAMA_MODEL=dolphin-llama3:8b` configured but 0 models pulled. Pull in progress (~4.7GB).

**M3. "Skip login (dev mode)" button is a no-op** — just `router.push(redirect)`, never establishes a session. Dev-mode convenience, not prod-impacting.

### 🟢 LOW / Debt

**L1. 9 stale unit-test modules** — reference removed code (`AuthMiddleware`, `app.models.support_session`, `app.repositories.job_repository`, `app.models.feature_rollout`) or changed APIs (sqlalchemy `DBAPIError`). CI unit tests can't collect.

**L2. ~1121 Ruff lint errors** — pre-existing debt across the whole backend (269 in app/, 231 in tests/). Pinned ruff 0.8.6 for determinism; 899 are auto-fixable but need a dedicated cleanup pass, not a pre-prod blind sweep.

**L3. Bandit flags 2237 "high confidence" issues** — same version-drift pattern; needs baseline/triage, not a real vuln count.

**L4. Ollama model pull** — in progress, verify after.

---

## Verified Working Well
- ✅ Auth gate: every protected route cleanly redirects to `/login?redirect=...` (26/26), zero console errors
- ✅ Landing page + full talent cast + vibe switcher render, images serve 200
- ✅ `/talent`, `/models`, `/admin/*`, `/assets`, `/brain`, `/publish`, `/training` all load with 0 console errors post-fix
- ✅ Real Supabase login via UI works end-to-end
- ✅ Frontend prod build + lint pass in CI
- ✅ Railway backend `/health` live

---

## Next Actions (recommended order)
1. **Redeploy Railway** from `main` with corrected env (kill AUTH_DEV_MODE, set REDIS_URL, Ollama, CORS for both Vercel apps) — unblocks real prod.
2. **Apply DB migrations** (`042-046` + create `universes`/`onboarding_state`) — unblocks Story/Workflows and hardens tenant isolation.
3. **Clear test debt** (fix/remove 9 stale test modules) so unit tests pass.
4. **Lint debt cleanup pass** (separate session; auto-fix 899 with review).
5. **Verify Ollama model** landed; confirm AI Brain works.
