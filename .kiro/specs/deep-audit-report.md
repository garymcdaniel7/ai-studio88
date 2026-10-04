# Deep Codebase Audit Report — 2026-10-04

**Author:** @cto + @ai-studio teams + subagents
**Scope:** All 7 workspace variants (main, brain, creation, growth, platform, post, talent)
**Total findings:** 17 security + 6 pipeline + 33 route audit

---

## 🔴 CRITICAL FINDINGS (Ship-Blocking)

### F13 — api_v1.py: 19+ Unscoped Supabase Queries
**File:** `backend/api_v1.py` (lines 230, 287, 1983, 2010, 2052, 2853, 3524, 3702, 3728, 3741, 3755, 3769, 3797, 3972, 3978, 4019, 4390, 4429, 4441)
**Impact:** Any authenticated user can READ/WRITE any tenant's data through **19+ queries** that lack `.eq("org_id", org_id)`. Tables affected: talent, scenes, shots, lora_versions, assets, storyboards, talent_relationships.
**Fix:** Append `.eq("org_id", user_org_id)` to every query or route through `database.py` org-scoped helpers.

### F14 — main.py Native Routes: Crash + No Auth
**File:** `backend/main.py` (lines 130-149)
**Impact:** GET /projects, GET /talent, POST /talent have NO auth guard AND crash with TypeError at runtime because `database.py` functions require `org_id` but none is passed.
**Fix:** Add `Depends(require_auth)`, extract `org_id` from `AuthUser`, pass to functions.

### F3 — execution/tools.py: Zero org_id Filters
**File:** `backend/aios/execution/tools.py` (lines 133, 194, 213, 229) — ALL 7 variants
**Impact:** Brain's tool executors bypass MCP middleware. Cross-tenant data leak + write access to talent, assets, publishing_posts.

### F1 — dashboard/api_client.py: No Auth Headers
**File:** `dashboard/api_client.py` (lines 29-123) — ALL 7 variants
**Impact:** Streamlit dashboard uses `requests.get/post/delete()` with ZERO auth headers. After backend auth is enforced, every dashboard page gets 401.

### F4 — worker.py: Hardcoded org_id
**File:** `backend/worker.py` (lines 142, 221)
**Impact:** Hardcoded UUID `c7dc65c0-...` means ALL workers claim jobs under dev tenant if WORKER_ORG_ID not set.

---

## 🟡 HIGH FINDINGS

| # | Finding | File | Detail |
|---|---|---|---|
| F15 | Auth router removed | `backend/main.py` (all 6 agent branches) | OAuth login/callback/logout endpoints missing |
| F17 | No AuthMiddleware | `backend/main.py` (main branch) | Root app has no AuthMiddleware registered |
| F2 | authFetch not enforced | `frontend/src/lib/api.ts` | Pages can still use raw fetch() |
| F5 | No org_id validation | `backend/worker.py:142` | No startup validation for org_id format |
| F6 | _find_active no expiry check | `backend/credentials.py:441-456` | Returns expired credentials as valid |

---

## 🟢 MEDIUM FINDINGS

| # | Finding | Detail |
|---|---|---|
| F7 | No expires_at field | `credentials.py:124-140` |
| F9 | ProviderType missing social platforms | `credentials.py:95-106` — Instagram→ElevenLabs hack |
| SF1 | Story engine: 0 of 22 endpoints exist | Models/logic exist but NO FastAPI router |
| SF2 | 11 frontend pages don't import from @/lib/api | Various files, see full report |
| SF3 | 33 routes vs 17 in design doc | Design doc undercounts routes significantly |
| SF4 | Frame grid: 11 valid values, not 4 | 124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600 |

---

## ✅ PASS

| # | Finding | Detail |
|---|---|---|
| F16 | MCP auth.py | All endpoints authenticated — strongest auth in codebase |

---

## Key Insight: MCP server.py is CLEAN, The Leak is in execution/tools.py

The MCP server (`server.py`) was fixed in the auth-tenant-isolation pass — every endpoint uses `MCPClientDep` and executors receive `org_id`. The CRITICAL leak is in the **Brain's executor bridge** (`execution/tools.py`), which bypasses MCP middleware entirely. This is the file Kiro (or the backend lane) must fix first.

---

## 7 Workspace Variants Status

| Branch | Critical | High | Medium |
|---|---|---|---|
| main | 5 | 5 | 3 |
| brain | 4 | 5 | 3 |
| creation | 4 | 5 | 3 |
| growth | 4 | 5 | 3 |
| platform | 4 | 5 | 3 |
| post | 4 | 5 | 3 |
| talent | 4 | 5 | 3 |