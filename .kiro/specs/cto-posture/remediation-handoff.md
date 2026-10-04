# CTO Remediation — Handoff to Kiro

**Generated:** 2026-10-03 (updated — merged from posture review + scratch findings)
**Source audit:** `~/.hermes/audits/cto-posture-review-20261003.md`
**Specs directory:** `.kiro/specs/cto-posture/`

---

**Kiro: read this whole doc first, then open `tasks.md` in this directory for your task queue.**

Two workstreams:
- **Stream A — Auth Remediation** (sections 2-3): Remaining auth gaps from the original posture review. Phase order matters — follow the numbered phases in `tasks.md`.
- **Stream B — Competitive Capabilities** (section 5): Independent work items. Pick any order after Stream A. C2 has its own spec file.

---

## TL;DR

Three HIGH-severity auth gaps still open in production `backend/main.py`:
three native routes (`GET /projects`, `GET /talent`, `POST /talent`) are
completely unprotected by any auth middleware or dependency. A full-featured
`AuthMiddleware` class exists at `backend/app/core/middleware.py:128-190`
but is **never registered** via `app.add_middleware()`. The same file has
a second dead middleware (`OrgIdInjectionGuard`). Separately, the legacy v1
routes (`backend/api_v1.py`) make ~50+ tenant-scoped queries with zero
`org_id` filtering — entirely reliant on Supabase RLS as a backstop.

Additionally, six competitive capabilities (Section 5) can be wired on top
of existing infra for quick differentiation.

---

## 1. Remediation Status — Already Shipped ✅

| Finding | Severity | Fix | Commit | Status |
|---|---|---|---|---|
| F1 — Legacy `/api/v1` router has 155 routes with NO auth | 🔴 CRITICAL | Router-level `_legacy_v1_guard` deny-by-default; public allowlist `/api/v1/health` + `/api/v1/capabilities` | `b46e6b9` | ✅ Done — deployed |
| F2 — Publishing router no auth + cross-tenant collision | 🟠 HIGH | `_publishing_guard` + `_oauth_guard`; org-scoped queries; composite unique `(org_id, platform)` | `5e013bf` + `89efdcf` | ✅ Done — deployed |
| F3 — Dev fallback grants OWNER role on `dev-user-local` | 🟡 MEDIUM | Hard-blocked when `app_env` is production/staging | `cba6ef3` | ✅ Done — deployed |
| F4 — Trade-bot profile duplicates entire `.env` | 🔵 LOW | Sliced from 16 → 11 keys; backup saved | n/a (outside repo) | ✅ Done — applied |

**Test baseline:** 133 tests pass. Live probes confirm 6 unauthenticated endpoints return 401.

---

## 2. Remaining Auth Gaps — Still Open 🔴

These four findings are the **unfinished work** from the original CTO posture review. They were identified during the same audit as F1-F4 but were not included in that remediation pass.

### F5 — main.py Native Routes (HIGH)

| Route | Method | Risk |
|---|---|---|
| `GET /projects` | Read | Returns ALL projects to any caller |
| `GET /talent` | Read | Returns ALL talent records to any caller |
| `POST /talent` | **WRITE** | Creates talent records — data-mutating, no auth |

Currently **accidentally protected**: the direct Supabase client calls happen to
fail in production because the connection context isn't valid for these routes.
If/when the Supabase connection is fixed, these routes serve all rows to any caller.

**Fix approach:** Add `Depends(require_auth)` to each route. Use the existing
`require_auth` dependency from `backend/auth.py` — same one already used by
`_legacy_v1_guard`.

**Acceptance:**
- `GET /projects` (no creds) → 401
- `POST /talent` (no creds) → 401
- Both with valid JWT → 200 or proper structured error (if no data)

### F6 — AuthMiddleware Never Registered (HIGH — architecture-level)

`backend/app/core/middleware.py:128-190` defines a complete `AuthMiddleware`
class that:
- Validates Bearer JWTs via `decode_supabase_jwt()`
- Handles expired/invalid tokens with structured errors
- Supports `auth_dev_mode` (blocked in production/staging)
- Exempts public probe paths (`/health`, `/ready`, `/docs`, etc.)

It is **never wired** in `main.py`. The middleware registration block (lines 70-86)
only registers:
- `CORSMiddleware` — ✅
- `RequestContextMiddleware` — ✅
- `RequestIdMiddleware` — ✅

`app.add_middleware(AuthMiddleware)` is **absent**. The middleware is referenced
only in tests (`backend/tests/unit/test_core/test_middleware.py`).

**Note:** The module docstring on `middleware.py` (line 1-7) also doesn't
mention `AuthMiddleware` — update it while you're there.

**Fix:** In `backend/main.py`, after the existing middleware block (~line 86),
add:
```python
from backend.app.core.middleware import AuthMiddleware
app.add_middleware(AuthMiddleware)
```

**Acceptance:**
- Credential-less request to `/projects` → 401 (via middleware before route)
- Valid JWT → continues to handler
- Expired/invalid token → 401 with structured error (`TOKEN_EXPIRED` code)

### F7 — OrgIdInjectionGuard Not Wired (MEDIUM)

`backend/app/core/middleware.py:28-75` defines `OrgIdInjectionGuard` — a
defense-in-depth middleware that rejects any request supplying `org_id` as a
query parameter (prevents client-side org_id injection/spoofing).

Also never registered. Same pattern as `AuthMiddleware`.

**Fix:** In `backend/main.py` after the existing middleware block, add:
```python
from backend.app.core.middleware import OrgIdInjectionGuard
app.add_middleware(OrgIdInjectionGuard)
```

**Acceptance:**
- `GET /projects?org_id=foreign-org` → 422 `ORG_ID_INJECTION_REJECTED`
- `GET /projects` (no `org_id` param) → proceeds normally

### F8 — Tenant Isolation on v1 Queries (MEDIUM)

The legacy v1 router (`backend/api_v1.py`) has ~50+ `supabase.table(...)`
queries that lack `org_id` filtering. Known patterns:

| Pattern | Example | Risk |
|---|---|---|
| `.table("talent").delete().eq("id", talent_id)` | Deletes without org_id | Any user can delete any org's talent |
| `.table("talent").update(...).eq("id", talent_id)` | Updates without org_id | Cross-tenant talent mutation |
| `.table("assets").select("*").contains("tags", ...)` | No org_id | Returns all orgs' assets |
| `.table("storyboards").select("*")` | No org_id | Returns ALL storyboards |
| `.table("scenes").select("*").eq("id", scene_id)` | No org_id | Cross-tenant scene access |
| `.table("shots").select("*").eq("id", shot_id)` | No org_id | Cross-tenant shot access |
| `.table("lora_versions").select("*").eq("talent_id", talent_id)` | No org_id | Cross-tenant LoRA access |

All rely **entirely** on Supabase RLS for tenant isolation. Per the engineering
doctrine: app-layer enforcement is primary, RLS is a backstop. A system relying
on the backstop is already broken.

**Fix approach:** Each query needs `.eq("org_id", org_id)` where `org_id` comes
from validated credentials (the JWT's `app_metadata.org_id`). The v1 router already
has `_legacy_v1_guard` which calls `require_auth(request)` returning an `AuthUser`
with an `org_id` field.

Pattern:
```python
# Current:
result = supabase.table("assets").select("*").contains("tags", tags).execute()

# Fixed:
user = _legacy_v1_guard(request)  # already authenticated by router dep
result = supabase.table("assets").select("*")\
    .eq("org_id", user.org_id)\
    .contains("tags", tags)\
    .execute()
```

**Acceptance:** Using staging Supabase with RLS disabled:
- Create assets under org_A JWT → request assets with org_B JWT → zero org_A assets visible
- DELETE talent with org_B JWT → cannot delete org_A's talent record
- SELECT storyboards with no filter → only own org's storyboards returned

---

## 3. Specs in This Directory

| File | Covers |
|---|---|
| `c2-speed-verbs-injection.md` | Speed verbs into H3 prompt builder |
| `staging-environment.md` | Staging Supabase + local Docker Compose for safe testing |
| `tasks.md` | Kiro's task queue — sliced and phased |

---

## 4. Staging Environment

**Two tiers of test sandbox:**

| Environment | What it covers | How to use |
|---|---|---|
| **Local Docker Compose** | All non-RLS tests, auth guard verification, unit/integration | `docker compose up -d redis nginx api` → `cd backend && pytest` |
| **Supabase Staging** | RLS-disabled tests, tenant isolation (F8), destructive migration tests | Source `.env.staging` → `supabase db push` → run targeted tests |

**Staging project:** `xvafacjfhosvoowotztz.supabase.co` (created 2026-10-03)
**`.env.staging`:** `~/kiro/ai-studio88/.env.staging` — contains URL, pooler URL, JWT secret.
**Missing:** anon + service_role JWT keys (must be retrieved from Supabase dashboard → Settings → API)

See `staging-environment.md` for full matrix and step-by-step.

---

## 5. Competitive Capabilities — Unified Ship Menu

Six capabilities we can ship at sprint speed because the infra already exists.
Each is self-contained — pick any subset.

| # | Capability | Lane | Effort | Existing Infra | Wiring Work | Depends On |
|---|---|---|---|---|---|---|
| C1 | **Anti-Plastic Toggle** | @ai-studio | **0.5 day** | Mandatory prompt clauses already defined (`realistic skin texture with visible pores, no plastic/waxy/CGI skin, no beauty filter`); Krea body → Klein face dual-pass pipeline exists on box. | Project-level boolean that (a) auto-injects anti-plastic block into every gen prompt and (b) routes through dual-pass render chain. Frontend toggle + backend prompt template injection. | None |
| C2 | **Speed Verbs Injection** | @ai-studio | **< 2 hrs** | Gary's production rule: every H3/Wan video prompt must include `"fast powerful motion, whip-fast acceleration"` — or motion feels "weird." | Two-line injection into the I2V prompt template. No UI needed. | None — see `c2-speed-verbs-injection.md` |
| C3 | **Character Consistency Toggle** | @kiro (spec by @cto) | **1 day** | Identity-locking pipeline (identity anchor → Krea 2 Edit → H3 img2img), identity sheet concept exists. | Expose per-project toggle: "Enforce character consistency" → backend locks all gen prompts to use identity anchor block. Frontend toggle + backend wiring. | None |
| C4 | **Frame Grid Validation** | @ai-studio | **0.5 day** | Known valid H3 frame grid (`17k+5`: 226/243/260/277 for 15s @ 24fps). Know that 216/280 produce temporal glitches. | Snap duration slider in UI to valid grid values. Backend validates frame count before enqueue. Frontend form constraint. | None |
| C5 | **Series Bible / Show Memory** | @kiro (spec by @cto) | **1-2 days** | `brain_user_memory` table, `BrainConversationService`, summary compaction. | Surface "session memory" in generation UI as editable series bible — write key facts to memory pool, inject into every gen prompt. UI + API wiring. | None |
| C6 | **Brand Identity Template** | @kiro (spec by @cto) | **1-2 days** | Memory pool, project settings store. | Store visual style guide, tone, format rules per project; inject into prompt templates. Data model + settings UI. | None |

### Lane Ownership

| Lane | Focus | Capabilities |
|---|---|---|
| **@ai-studio** | Production pipeline, prompt templates, workflow logic | C1, C2, C4 |
| **@kiro** | Infrastructure, data model, API wiring (spec'd by @cto) | C3, C5, C6 |
| **@hermes** | Direct execution of template-speed changes | C2 (executing) |

### Recommended Ship Order

```
Stream A first (auth remediation) — F5+F6+F7+F8 in Phase 1+2+3 order
Then:
  Batch 1: C2 (today), C1 (0.5d), C4 (0.5d), C3 (1d)
            → Four "Episode 11" differentiators in ~2 days
  Batch 2: C5 (1-2d), C6 (1-2d)
            → Deepens moat with series memory + brand locks
```

### Avoid for Fast Ship

These require new infra, not wiring:

- Multi-episode narrative planner — new orchestration engine
- Automated episode sequencing — non-trivial planning logic
- YouTube upload scheduling — new platform surface + OAuth
- BYOLLM — tenant LLM key support (product question, not ready)
- Real Hermes Agent per tenant — profile isolation + MCP tool bindings

---

## 6. Handoff Envelope

When these gates clear, the remediation handoff is done:

- [ ] **F5** — main.py native routes auth'd (GET /projects, GET /talent, POST /talent)
- [ ] **F6** — AuthMiddleware wired in main.py
- [ ] **F7** — OrgIdInjectionGuard wired in main.py
- [ ] **F8** — Tenant isolation scoped on v1 queries (app-layer, not RLS-dependent)
- [ ] **C2** — Speed verbs injection committed (see `c2-speed-verbs-injection.md`)
- [ ] **Staging env** — anon/service_role keys retrieved from dashboard, `.env.staging` complete
- [ ] **Remaining capabilities (C1, C3, C4, C5, C6)** — Ownership confirmed, specced, and scheduled
- [ ] **Final verification** — Re-run probe calls against staging → all 401 on guarded surfaces

---

## 7. Verification Checklist

```bash
# 1. Auth guard (F1) — already shipped, verify still holding
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/generation/run
# Expected: 401

# 2. Publishing guard (F2) — already shipped
curl -s -o /dev/null -w "%{http_code}" -X GET http://localhost:8000/api/v1/publishing/analytics/summary
# Expected: 401

# 3. OAuth guard (F2) — already shipped
curl -s -o /dev/null -w "%{http_code}" -X GET http://localhost:8000/api/v1/publishing/oauth/connections
# Expected: 401

# 4. Public allowlist intact (F1)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health
# Expected: 200

# 5. F5 — main.py native routes (open — verify after fix)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/projects
# Expected: 401

# 6. F7 — OrgIdInjectionGuard (open — verify after fix)
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/projects?org_id=foreign-123"
# Expected: 422 (ORG_ID_INJECTION_REJECTED)

# 7. Tenant isolation (F8 — run against staging with RLS disabled)
cd backend && APP_ENV=staging python -m pytest tests/unit/test_rls_isolation.py -v --tb=long
# Expected: all pass

# 8. Unit test suite
cd backend && python -m pytest tests/unit/ -v --tb=short
# Expected: all pass (133 baseline)
```