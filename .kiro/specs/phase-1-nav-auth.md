# AI Studio — Phase 1: Navigation & Auth Layer

**Status:** Implementation spec for Kiro
**Source:** Derived from `.kiro/specs/ui-revamp-design.md` (product umbrella)
**Authored:** `[DATE]` by @hermes, @ai-studio, @cto with subteam audits
**Pre-requisite reading:** `.kiro/specs/deep-audit-report.md` (17 findings across all 7 workspace variants — the critical 5 must be fixed before any feature work)

---

## Scope

Phase 1 ships the **navigational foundation** and **auth migration** that every subsequent phase depends on. It does NOT include pipeline controls (P1-P11), BYO credentials, MCP expansion, publishing integrations, LoRA training, or deployment self-service — those are separate specs for later phases.

### What's IN
1. **🔴 Fix execution/tools.py org_id leak** (Brain executor bridge — P0 CRITICAL)
2. **🔴 Fix api_v1.py 19+ unscoped supabase queries** (P0 CRITICAL)
3. **🔴 Fix main.py native routes** (add auth + fix crash — P0 CRITICAL)
4. **🟡 Fix dashboard/api_client.py auth headers** (P0 CRITICAL — blocks Stream A)
5. **🟡 Worker `--org-id` required enforcement** (P0 CRITICAL)
6. **🟡 Fix auth_router on all 6 agent branches** (P1 HIGH)
7. **🟠 Story engine — 0 of 22 endpoints exist** (P1 HIGH — models/logic exist but no FastAPI router. Design doc claims "50+ endpoints" but only data models exist. Frontend story page calls return 404.)
8. 301 redirect layer (V1 → V2 routes) — **update for 33 actual routes**
9. Centralized `apiFetch()` replacing raw `fetch()` in 13+ confirmed components
10. Auth middleware + AuthGate integration
11. AppShell rewrite (sidebar → 5-step horizontal nav) with responsive breakpoints
12. START page (landing + project dashboard)
13. Route matrix with auth enforcement
14. Credential `expires_at` enforcement in `_find_active()`
15. **Fix frame grid** — update from 4 values to **11 valid values** (124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600)

### What's OUT (separate specs)
- CAST, WRITE, MAKE, PUBLISH page builds
- Pipeline controls (P1-P11)
- BYO API credential management
- MCP tool expansion
- Publishing platform integrations
- LoRA training

---

## 1. Route Migration (301 Redirect Layer)

### Redirect Map

| Old Route | New Route | Type | Notes |
|---|---|---|---|
| `/create` | `/make` | 301 | 90-day deprecation window |
| `/editor` | Interstitial at `/editor` → banner links to WRITE/MAKE | 301 + interstitial | 90 days, then 301 |
| `/production` | `/write` | 301 | 90d |
| `/training` | `/cast?tab=training` | 301 with query param passthrough | 90d |
| `/talent` | `/cast` | 301 | 90d |
| `/workflows` | `/make?tab=workflow` | 301 with query param | 90d |
| `/analytics` | `/publish?tab=analytics` | 301 with query param | 90d |
| `/projects` | `/start` | 301 | 90d |
| `/models` | `/cast` (character models) or `/admin/models` (gen models) | 301 + section anchor | 90d |
| `/jobs` | Inline queue in `/make` | 301 → /make | 60d |
| `/brain` | **Keep** | — | Forever |
| `/login` | **Keep** | — | Forever |
| `/assets` | `/publish` | 301 | 90d |
| `/pricing` | **Keep** | — | Forever |
| `/story` | **Keep** (becomes WRITE) | 301 → /write after Phase 2 | Phase 2 |

### Implementation
- Add to `frontend/next.config.js` `async redirects()` or a middleware redirect map
- All redirects are HTTP 301 permanent
- Deprecation interstitial: Phase 1 = redirect + console log. Phase 2 (90d) = direct 301
- Query param forwarding supported (e.g. `/training?talent_id=abc` → `/cast?tab=training&talent_id=abc`)

### Acceptance Criteria
- [ ] Every V1 route returns HTTP 301 or maps to a valid V2 page
- [ ] No V1 route returns 404 after deployment
- [ ] Bookmarks to old URLs resolve to correct new pages
- [ ] Deep links with query params preserve the context through the redirect

---

## 2. Frontend Auth Migration

### Problem
13+ components across the frontend use raw `fetch()` with **zero auth headers** (no Authorization, no X-API-Key, no X-Org-ID). They rely entirely on backend being open.

### Files to Fix

All paths relative to `frontend/src/`:

| # | File | Endpoints Called | Fix |
|---|---|---|---|
| 1 | `components/brain-dock.tsx` | `/aios/v1/chat` POST | Replace with `api.post()` |
| 2 | `components/feedback-buttons.tsx` | `/api/v1/feedback/*` POST | Replace with `api.post()` |
| 3 | `components/topbar.tsx` | `/api/v1/search` GET, `/aios/v1/health/alerts` GET | Replace with `api.get()` |
| 4 | `app/story/page.tsx` | `/api/v1/universes`, `/api/v1/episodes/*` GET/POST | Replace with `api.get()/post()` |
| 5 | `app/talent/_components/talent-relationships-section.tsx` | `/api/v1/talent/*/relationships` GET/POST/DELETE | Replace with `api.get()/post()/delete()` |
| 6 | `app/talent/_components/talent-profile-image.tsx` | `/api/v1/talent/*/media` GET/POST | Replace with `api.get()/upload()` |
| 7 | `app/talent/_components/talent-media-section.tsx` | `/api/v1/talent/*/media`, `/api/v1/assets/*` GET/POST/PUT/DELETE | Replace with `api.*()` |
| 8 | `app/talent/_components/talent-lora-section.tsx` | `/api/v1/talent/*/loras`, `/api/v1/models` GET/POST/DELETE | Replace with `api.*()` |
| 9 | `app/talent/_components/talent-voice-section.tsx` | `/api/v1/voices/*` GET/POST/DELETE | Replace with `api.*()` |
| 10 | `app/create/_components/generation-result.tsx` | `/api/v1/generate/open-folder` POST | Replace with `api.post()` |
| 11 | `app/analytics/page.tsx` | `/api/v1/infrastructure/cost*`, `/api/v1/generation/history` GET | Replace with `api.get()` |
| 12 | `app/assets/page.tsx` | `/api/v1/assets` GET/POST/DELETE | Replace with `api.*()` |

### The `api` Object Pattern

```typescript
// RECOMMENDED — full typed API client with retries, timeout, error mapping
import { api } from "@/lib/api";

// GET with typed response
const data = await api.get<Talent[]>("/api/v1/talent");

// POST with body
const result = await api.post("/api/v1/models", { name: "Nova" });

// Multipart upload with progress
const uploaded = await api.upload("/api/v1/models/upload", formData, {
  onProgress: (pct) => console.log(pct),
  timeout: 600_000
});

// Streaming (SSE)
const stream = await api.stream("/api/v1/generate/stream", { prompt });

// Unauthenticated request (rare)
const health = await api.get("/", { noAuth: true });
```

**NEVER:**
```typescript
import { API_BASE } from "@/lib/api";
const res = await fetch(`${API_BASE}/api/v1/talent`); // SKIPS AUTH!
```

### Auth Enforcement Architecture
```
Request → AuthMiddleware (backend/middleware.ts or next.config.js)
  ├── Public routes: /login, /landing, /auth/google, /auth/callback
  │   → Pass through (no auth required)
  │
  └── Protected routes: everything else
      → Validate JWT session token
      → Attach user_id + org_id to request context
      → If invalid/expired → redirect to /login
```

### Acceptance Criteria
- [ ] All 13 components use `api.*()` methods from `@/lib/api`
- [ ] No raw `fetch()` calls remain in frontend source
- [ ] Unauthenticated users are redirected to `/login` on protected pages
- [ ] Expired JWT triggers auto-redirect, not a crash or blank page
- [ ] API 401 responses trigger session refresh or redirect

---

## 3. AppShell + 5-Step Nav

### Layout
```
┌─────────────────────────────────────────────────┐
│  [Logo]  START → CAST → WRITE → MAKE → PUBLISH  │
├─────────────────────────────────────────────────┤
│                                                   │
│           CONTENT AREA                            │
│                                                   │
└─────────────────────────────────────────────────┘
```

### Responsive Breakpoints
| Viewport | Nav Behavior |
|---|---|
| ≥1024px | Full horizontal 5-step nav bar |
| 768-1024px | Scrollable tabs (arrows on each side) |
| <768px | Hamburger dropdown with current step as label |

### Components (from existing codebase)
- **Frozen** (`frontend/src/components/` — Kiro must NOT modify):
  - `AppShell` layout wrapper
  - `AuthGate` route protection
- **Net-new** (Kiro builds):
  - `TopBar` with 5-step horizontal nav
  - `StepIndicator` (shows current/completed/future states)
  - `NavDropdown` (hamburger variant for mobile)

### Lane Ownership
Each page.tsx belongs to a specific lane (from `LANES.json`):

| Page | Lane | Owned Path |
|---|---|---|
| `/start` | growth | `src/app/page.tsx` |
| `/cast` | talent | `src/app/cast/**` |
| `/write` | creation | `src/app/write/**` |
| `/make` | creation | `src/app/make/**` |
| `/publish` | growth | `src/app/publish/**` |
| `/settings` | platform | `src/app/settings/**` |
| `/admin` | platform | `src/app/admin/**` |
| `/brain` | brain | `src/app/brain/**` |

**Kiro operates in the BACKEND lane only** (`backend/**`). Frontend page components are built by their respective lane agents.

### Acceptance Criteria
- [ ] 5-step nav renders correctly at all 3 breakpoints
- [ ] Active step is highlighted with accent color
- [ ] Completed steps show checkmark
- [ ] Future steps are visually distinct (muted)
- [ ] Nav persists across all pages
- [ ] Mobile hamburger shows current step as label

---

## 4. Route Matrix (Public vs Protected)

| Route | Auth Required | Notes |
|---|---|---|
| `/` (landing) | ❌ No | Public landing page |
| `/login` | ❌ No | Auth entry point |
| `/auth/google` | ❌ No | OAuth redirect |
| `/auth/callback` | ❌ No | OAuth callback |
| `/auth/logout` | ❌ No | Session clear |
| `/pricing` | ❌ No | Public pricing page |
| `/start` | ✅ Yes | Dashboard |
| `/cast` | ✅ Yes | Talent studio |
| `/write` | ✅ Yes | Story/storyboard |
| `/make` | ✅ Yes | Generation studio |
| `/publish` | ✅ Yes | Library + calendar |
| `/settings` | ✅ Yes | User config |
| `/admin` | ✅ Yes | Admin dashboard |
| `/brain` | ✅ Yes | AI chat |
| All `/api/v1/*` | ✅ Yes (except auth endpoints) | API routes |
| All `/aios/*` | ✅ Yes | MCP + AIOS routes |

---

## 5. Worker `--org-id` Required Enforcement

### Current Problem
`backend/worker.py` line 142:
```python
self.org_id = org_id or os.getenv("WORKER_ORG_ID", "c7dc65c0-a0b1-4980-9f60-884d024a19ca")
```

The hardcoded UUID `c7dc65c0-...` is a dev tenant ID. In production, if `WORKER_ORG_ID` is unset, ALL jobs silently go to this dev org.

### Fix
1. Make `--org-id` required in argparse: `parser.add_argument("--org-id", required=True)`
2. Remove the default value entirely
3. Change line 142 to: `self.org_id = org_id or os.getenv("WORKER_ORG_ID")`
4. Add assertion: `if not self.org_id: raise ValueError("WORKER_ORG_ID or --org-id is required")`
5. Clean up test scripts referencing the hardcoded UUID

### Files to Fix
- `backend/worker.py` (primary)
- `backend/scripts/reprobe_video.py`
- `backend/scripts/aios_scale_test.py`
- Same files in all 7 workspace variants

---

## 6. Credential `expires_at` Enforcement

### Files
`backend/credentials.py` across all 7 workspace variants.

### Changes Needed
1. Add `expires_at: str | None = None` to `CredentialRecord` dataclass
2. Update `_find_active()` (line ~442) to check expiry:
   ```python
   and (record.expires_at is None or datetime.now(UTC).isoformat() < record.expires_at)
   ```
3. Add `ProviderType.USER_API_KEY = "user_api_key"` to `ProviderType` enum

### Out of Phase 1 Scope
- DB migration 034 (Supabase `workspace_credentials` table) — Phase 2
- Rotation automation — Phase 3
- Full RBAC — Phase 3

---

## 7. Error/Loading/Empty State Patterns (All Pages)

### Every page MUST implement:

**Loading State**
- Skeleton UI matching page layout (NOT a spinner)
- Content appears progressively as data resolves
- No full-page blank while waiting

**Error State**
- Specific error message per failure type (GPU OOM / network / auth / validation)
- `X-Request-ID` logged for debugging
- Retry button for recoverable errors
- "Contact support" link for unrecoverable errors
- Never crashes the browser or shows raw error trace

**Empty State**
- CTA button for first action ("Create your first project")
- Example or template pre-filled where applicable
- Never shows broken layout or "No items" without next step

---

## 8. Phase 1 Delivery Checklist

- [ ] **🔴 execution/tools.py** — Thread `org_id` through ALL 6 executors across all 7 variants
- [ ] **🔴 api_v1.py** — Add `.eq("org_id", org_id)` to all 19+ unscoped queries
- [ ] **🔴 main.py native routes** — Add `Depends(require_auth)` + fix TypeError crashes
- [ ] **🔴 dashboard/api_client.py** — Add `Authorization: Bearer <token>` to all requests
- [ ] **🔴 worker.py** — Make `--org-id` required, remove hardcoded UUID
- [ ] **🟡 auth_router** — Re-include on all 6 agent worktree branches
- [ ] All 13 frontend components migrated to `api.*()` calls
- [ ] Auth middleware enforcing public/protected route matrix
- [ ] AppShell with 5-step nav at all 3 breakpoints
- [ ] START page renders with project dashboard
- [ ] Worker `--org-id` required enforcement
- [ ] Credential `expires_at` enforcement in `_find_active()`
- [ ] Route matrix documented in code (public vs protected)
- [ ] Error/loading/empty state patterns applied to START page
- [ ] No regression in existing functionality