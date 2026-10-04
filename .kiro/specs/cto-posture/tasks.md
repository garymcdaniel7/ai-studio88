# Kiro Task Queue — CTO Remediation

**Source:** `.kiro/specs/cto-posture/remediation-handoff.md`
**Tag legend:** `[AUTH]` = Stream A (auth remediation), `[CAP]` = Stream B (competitive capabilities)
**Lane tags:** `[ai-studio]`, `[kiro]`

---

## Phase 1 — main.py Native Routes [AUTH] [kiro]

### Task P1-1: Add auth dependency to `GET /projects`

**File:** `backend/main.py` (line 130)

**What:**
1. Import `require_auth` from `backend.auth` (already exists — used by `_legacy_v1_guard`)
2. Change `@app.get("/projects", tags=["projects"])` → add `dependencies=[Depends(require_auth)]` and `user: AuthUser = Depends(require_auth)` parameter
3. Optionally scope the `get_projects()` call to the authenticated user's org

**Acceptance:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/projects
# → 401
```

---

### Task P1-2: Add auth dependency to `GET /talent`

**File:** `backend/main.py` (line 136)

**What:** Same pattern as P1-1 — add `Depends(require_auth)` to the `/talent` GET route.

**Acceptance:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/talent
# → 401
```

---

### Task P1-3: Add auth dependency to `POST /talent`

**File:** `backend/main.py` (line 142)

**What:** Same pattern — add `Depends(require_auth)`. This is the highest-risk route of the three since it's a **WRITE** endpoint. Also validate that `talent_data` is accepted from an authenticated context only.

**Acceptance:**
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d '{"name":"test"}' \
  http://localhost:8000/talent
# → 401
```

---

## Phase 2 — Middleware Wiring [AUTH] [kiro]

### Task P2-1: Wire AuthMiddleware in main.py

**Files:** `backend/main.py` (~line 86 addition), `backend/app/core/middleware.py` (docstring update)

**What:**
1. In `backend/main.py`, after the existing middleware block (after line 86 `app.add_middleware(RequestIdMiddleware)`):
   ```python
   from backend.app.core.middleware import AuthMiddleware
   app.add_middleware(AuthMiddleware)
   ```
2. Update `middleware.py` module docstring (line 1-7) to mention `AuthMiddleware`:
   ```python
   """Application middleware for security and tenant isolation enforcement.
   
   Contains:
       - OrgIdInjectionGuard: Rejects requests that supply org_id in query/body params
       - RequestContextMiddleware: Adds X-Request-ID to all responses
       - AuthMiddleware: Validates bearer JWTs on every request
   """
   ```

**Dependency:** P1-1, P1-2, P1-3 should be done first (AuthMiddleware may conflict with or override route-level auth — better to have route deps in place as defense-in-depth).

**Acceptance:**
```bash
# No creds → 401 with structured error
curl -s http://localhost:8000/projects | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('code')=='UNAUTHORIZED'"

# Expired token → TOKEN_EXPIRED
# (test via unit test or with an expired JWT)

# Valid JWT → passes through to handler
```

---

### Task P2-2: Wire OrgIdInjectionGuard in main.py

**File:** `backend/main.py` (after AuthMiddleware registration)

**What:** Add import and registration:
```python
from backend.app.core.middleware import OrgIdInjectionGuard
app.add_middleware(OrgIdInjectionGuard)
```

**Acceptance:**
```bash
# org_id in query → 422
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/projects?org_id=foreign-123"
# → 422

# No org_id param → passes through
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <valid-jwt>" \
  http://localhost:8000/projects
# → 200 (or whatever the auth'd response is)
```

---

## Phase 3 — Tenant Isolation on v1 Queries [AUTH] [kiro]

### Task P3-1: Scope talent queries with org_id

**File:** `backend/api_v1.py`

**What:** Find all `supabase.table("talent").*` queries that lack `.eq("org_id", org_id)` and add the filter. At minimum:
- `talent.delete().eq("id", talent_id)` → add `.eq("org_id", user.org_id)`
- `talent.update(...).eq("id", talent_id)` → add `.eq("org_id", user.org_id)`
- Any talent SELECT without org_id filter

**Context:** `org_id` is available from `user = _legacy_v1_guard(request)` — the router already authenticates via this guard.

**Acceptance:** Run against staging with RLS disabled — create talent under org_A, attempt delete/update with org_B JWT → rejected.

---

### Task P3-2: Scope assets queries with org_id

**File:** `backend/api_v1.py` (around line 1408)

**What:** Add `.eq("org_id", user.org_id)` to all `supabase.table("assets")` queries. Known unfiltered pattern:
```python
# Current:
supabase.table("assets").select("*").contains("tags", tags).execute()
# Fixed:
supabase.table("assets").select("*").eq("org_id", user.org_id).contains("tags", tags).execute()
```

**Acceptance:** Create assets under org_A → request with org_B JWT → zero org_A assets visible. Staging with RLS disabled.

---

### Task P3-3: Scope storyboards/scenes/shots queries with org_id

**File:** `backend/api_v1.py` (around lines 1983, 2010, 3702)

**What:** Add `.eq("org_id", user.org_id)` to all `supabase.table("storyboards")`, `supabase.table("scenes")`, and `supabase.table("shots")` queries.

**Acceptance:** SELECT storyboards with no filter → only own org's storyboards returned. Same for scenes and shots. Staging with RLS disabled.

---

### Task P3-4: Scope remaining v1 queries (lora_versions + catch-all)

**File:** `backend/api_v1.py`

**What:** Audit and fix all remaining `supabase.table(...)` queries not covered by P3-1 through P3-3. Known pattern:
- `supabase.table("lora_versions").select("*").eq("talent_id", talent_id)` — add org_id filter

**Approach:** Grep for `supabase.table(` in `api_v1.py` and verify each occurrence has an `org_id` filter or an explicit justification for not needing one (e.g. public reference data).

**Acceptance:** Complete audit log showing every `supabase.table()` call reviewed, with org_id verified or documented as exempt.

---

## Phase 4 — Staging Environment Setup [AUTH] [kiro]

### Task P4-1: Complete staging env credentials

**Files:** `~/kiro/ai-studio88/.env.staging`

**What:** The `.env.staging` file has URL, pooler URL, and JWT secret but is **missing** two API keys that must be retrieved from the Supabase dashboard:
- `anon` key (starts with `eyJhbG...`)
- `service_role` key (starts with `eyJhbG...`)

**Action:** Open https://supabase.com/dashboard/project/xvafacjfhosvoowotztz → Settings → API → Project API keys → copy both keys into `.env.staging` as:
```
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service_role key>
```

**Acceptance:** `cd backend && APP_ENV=staging python -m pytest tests/unit/test_rls_isolation.py -v --tb=long` → all pass.

---

## Capability Tasks — Stream B [CAP]

### Task C2-1: Speed Verbs Injection (if not already shipped)

**Spec:** `c2-speed-verbs-injection.md` in this directory.
**Lane:** @ai-studio
**Estimate:** < 2 hrs

See the standalone spec file. This is the fastest ship in the menu.

---

### Task C1-1: Anti-Plastic Toggle

**Lane:** @ai-studio
**Estimate:** 0.5 day

**What:** Project-level boolean toggle that:
1. Auto-injects anti-plastic block into every generation prompt (`realistic skin texture with visible pores, no plastic/waxy/CGI skin, no beauty filter`)
2. Routes through Krea body → Klein face dual-pass render chain

**UI:** Frontend toggle on project settings page.
**Backend:** Prompt template injection that checks the toggle before building the prompt.

**Depends on:** None. Independent of auth work.

---

### Task C4-1: Frame Grid Validation

**Lane:** @ai-studio
**Estimate:** 0.5 day

**What:** Known valid H3 frame grid for 15s @ 24fps = 226/243/260/277. Frames 216 and 280 produce temporal glitches.

**UI:** Snap the duration slider in the generation form to values that produce valid frame counts.
**Backend:** Validate frame count in the enqueue endpoint before dispatching.

**Depends on:** None.

---

### Task C3-1: Character Consistency Toggle

**Lane:** @kiro (spec by @cto)
**Estimate:** 1 day

**What:** Per-project toggle: "Enforce character consistency" → backend locks all generation prompts to use the project's identity anchor block.

**Existing infra:** Identity-locking pipeline (identity anchor → Krea 2 Edit → H3 img2img), identity sheet concept.

**Wiring:**
1. Add `character_consistency_enabled` boolean to project settings model
2. When enabled, inject identity anchor block into every gen prompt
3. Frontend toggle on project settings

**Depends on:** Stream A completed (auth must be solid before we add more data-mutation surface).

---

### Task C5-1: Series Bible / Show Memory

**Lane:** @kiro (spec by @cto)
**Estimate:** 1-2 days

**What:** Surface "session memory" in the generation UI as an editable series bible — write key facts to the memory pool, inject into every gen prompt.

**Existing infra:** `brain_user_memory` table, `BrainConversationService`, summary compaction.

**Wiring:**
1. API endpoint to read/write series bible per project
2. UI textarea/dynamic list in project settings
3. Injection into gen prompt context for continuity

**Depends on:** C3-1 (shares identity/settings data model).

---

### Task C6-1: Brand Identity Template

**Lane:** @kiro (spec by @cto)
**Estimate:** 1-2 days

**What:** Store visual style guide, tone, format rules per project; inject into prompt templates.

**Existing infra:** Memory pool, project settings store.

**Wiring:**
1. Data model for brand identity fields per project (color palette, lighting style, aspect ratio, tone keywords)
2. Settings UI for brand fields
3. Injection into prompt templates for every gen of that project

**Depends on:** C5-1 (shares project settings data model).

---

## Execution Notes

### Commit discipline
- Each task = one commit. Don't bundle Phase 1 into a single commit.
- Commit message format: `cto-remediation/{phase}-{task}: short description`

### Phase ordering rules
- Phase 1 → Phase 2 → Phase 3: Must execute in this order because Phase 2 (AuthMiddleware) is a global safety net, but if it conflicts with route-level deps, having Phase 1 done first means the route-level deps cover you during the middle of Phase 2.
- Phase 4 (staging env) can be done at any time — it's prerequisite only for running the F8 acceptance tests.
- Stream B capabilities are independent of Stream A and each other, except C3→C5→C6 share a data model and are best done in sequence.

### Test before commit
- After each task, run: `cd backend && python -m pytest tests/unit/ -v --tb=short`
- The 133-test baseline must not regress.
- For F8 tasks, use `APP_ENV=staging` against the staging Supabase project.

### Rollback
- Each task is small enough that reverting a single commit is clean rollback.
- If a task touches `main.py`, keep the old routes commented out (not deleted) in the first pass so you can revert by uncommenting.