# User Acceptance Testing — Full Audit

**Date**: July 2026  
**Auditor**: AI Studio Development Team (13 specialists)  
**Scope**: All frontend pages, navigation, backend wiring, user journeys  
**Frontend**: Next.js 16, 14 route directories + root layout  
**Backend**: FastAPI, 16 mounted routers, 300+ endpoints  

---

## 1. Complete Page Inventory

| # | Route | Page Title | Purpose | Status |
|---|-------|-----------|---------|--------|
| 1 | `/` | Home | Dashboard with KPIs, quick actions, system status | Functional |
| 2 | `/brain` | AI Brain | Multi-mode LLM chat (6 modes), conversation history | Functional |
| 3 | `/create` | Create | Image/Video/Audio/Production generation | Functional |
| 4 | `/editor` | Editor | Storyboard + Quick Edit (FFmpeg) | Functional |
| 5 | `/training` | Training | LoRA training with image upload | Functional |
| 6 | `/talent` | Talent | AI persona management (CRUD, media, LoRAs) | Functional |
| 7 | `/assets` | Assets | Asset library with upload and filters | Functional |
| 8 | `/models` | Models | Model manager (upload, archive, deploy) | Functional |
| 9 | `/production` | Production | Job queue, workers, fleet metrics | Functional |
| 10 | `/publish` | Publish | Calendar, scheduling, OAuth platform connect | Functional |
| 11 | `/analytics` | Analytics | 5 views (Overview, Generation, Cost, Talent, Publishing) | Functional |
| 12 | `/admin` | Admin | Services, GPU control, toggles, output dir | Functional |
| 13 | `/settings` | Settings | Profile, Help, FAQ, About | Functional |
| 14 | `/story` | Story | Redirect to `/editor` | Functional |
| 15 | `/workflows` | Workflows | ComfyUI workflow visualization (read-only) | Functional |

### Sidebar Navigation (sidebar.tsx)

| Section | Items | Routes Match Pages |
|---------|-------|--------------------|
| (Top) | Home, Brain | Yes |
| Create | Create, Editor, Training | Yes |
| Manage | Talent, Assets, Models | Yes |
| Operate | Production, Publish, Analytics, Admin | Yes |

**Finding**: Sidebar does NOT include `/workflows` or `/settings`. Settings is accessible via user avatar link and admin gear icon. Workflows has no sidebar entry.

---

## 2. User Journey Mapping

### Journey A: New User Onboarding
1. User opens `/` (Home)
2. Sees greeting, quick actions, system status
3. Backend not connected → amber warning with start command shown
4. Quick action links to Create, Brain, Assets

**Issues Found**:
- No explicit onboarding wizard or first-time welcome modal
- Time-based greeting ("Good evening") is hardcoded, not dynamic
- Suggestion: Add a "Getting Started" checklist for new users

### Journey B: Create First Talent
1. Navigate to `/talent`
2. Click "New Talent" button
3. Fill name + bio in inline form
4. Click Create
5. Talent appears in grid
6. Click to select, edit details via Edit modal

**Issues Found**:
- Create form uses direct `fetch()` to legacy `/talent` endpoint (not the centralized API client `createTalent()` from api.ts)
- No validation feedback if name is empty (button is conditionally disabled but no error message)
- After creating talent, no success toast notification

### Journey C: Upload Training Photos + Train LoRA
1. Navigate to `/talent` → select talent
2. Upload photos via Media section
3. When 5+ photos uploaded, "Train LoRA" button appears
4. Click → redirects to `/training?talent_id=X`
5. On Training page, upload images, set config, click "Start Training"

**Issues Found**:
- Training page does NOT read `talent_id` query param to pre-associate
- No talent selector on Training page (user must manually associate later)
- Training page uses form data upload (correct approach)

### Journey D: Generate Image
1. Navigate to `/create`
2. Type prompt
3. Select model
4. Click Generate
5. Image appears below

**Issues Found**:
- Works when ComfyUI worker is active
- Clear error message when worker is offline
- "Open Folder" button calls backend to open Finder (desktop-specific, won't work in cloud)

### Journey E: Generate Video
1. Navigate to `/create` → Video tab
2. Type prompt, select model, duration
3. Click Generate
4. Wait for result

**Issues Found**:
- Long generation times (5-50 min) with no progress indicator other than spinner
- No websocket/polling for progress updates on this page (SSE exists on backend but not wired here)

### Journey F: Use AI Brain
1. Navigate to `/brain` or click "Chat with Brain" in sidebar dock
2. Select mode
3. Type message
4. Receive response

**Issues Found**:
- Brain health check polls every 10s (good)
- `useEffect` has unreachable code after the `return () => clearInterval(interval)` statement (lines after the cleanup function are dead code)
- "Use as Prompt" button on brain responses navigates to Create with prompt injected (works)
- Model shown as "llama3.2" in header but health endpoint reports "llama3.1:8b" — inconsistency

### Journey G: Schedule + Publish Content
1. Navigate to `/publish`
2. Click "Schedule Post"
3. Fill form (title, platform, date, content)
4. Post appears on calendar

**Issues Found**:
- OAuth platform connect section works (fetches from backend)
- Delete button on scheduled posts is functional
- Calendar is well-implemented with correct month navigation

---

## 3. UI/UX Issues Found

### Critical (Blocks User)

| # | Page | Issue | Severity |
|---|------|-------|----------|
| C1 | Brain | Dead code in useEffect — localStorage load + session fetch + collection fetch are unreachable (placed after `return` cleanup) | Bug |
| C2 | Talent | Create form uses raw `fetch()` instead of `createTalent()` from api.ts — inconsistent auth handling | Bug |
| C3 | Training | `talent_id` query param not consumed — talent→training flow is broken | Bug |

### High (Confusing UX)

| # | Page | Issue | Severity |
|---|------|-------|----------|
| H1 | Home | "Good evening" greeting is hardcoded, not time-aware | UX |
| H2 | Brain | Model label says "llama3.2" but backend reports "llama3.1:8b" | Inconsistency |
| H3 | Sidebar | No route to `/workflows` page — only accessible via direct URL | Navigation |
| H4 | Sidebar | No route to `/settings` page from main nav (only via user avatar) | Navigation |
| H5 | Create | "Open Folder" button is desktop-only (Finder), doesn't work in web/cloud | UX |
| H6 | Analytics | Talent/Social view shows all "—" with "Not connected" — no guidance on what to do | Empty State |
| H7 | Admin | "View Costs", "View Reputation", "Configure" buttons in Quick Actions are dead (no navigation) | Dead Buttons |
| H8 | Admin | `/admin/fleet` and `/admin/keys` links use `<a>` tags instead of Next.js `<Link>` — full page reload | Performance |

### Medium (Polish)

| # | Page | Issue | Severity |
|---|------|-------|----------|
| M1 | All | Loading states use generic `Loader2` spinner — no skeleton screens | UX |
| M2 | Talent | Characters/Voices/Influencers/Wardrobe metrics always show "0" (hardcoded, not counted from data) | Display Bug |
| M3 | Create | Favorites bar only shows when prompts exist — discovery is low | UX |
| M4 | Editor | Storyboard "Assemble Video" requires 2+ completed shots but no tooltip explaining this | UX |
| M5 | Production | "Launch Worker" button has confirm() dialog but no cost estimate shown | UX |
| M6 | Models | Archive/Hard Delete have proper confirms, but no toast on success | Feedback |
| M7 | Assets | No loading state shown while assets are being fetched | UX |
| M8 | Analytics | "Last 7/30/90 days" time range selector does nothing (state not used in queries) | Dead Control |
| M9 | Publish | "Connected Platforms" section invisible when no platforms configured | Empty State |
| M10 | Settings | Profile stats show "—" for Total Generations and Models Trained (not wired to API) | Incomplete |

### Low (Cosmetic)

| # | Page | Issue | Severity |
|---|------|-------|----------|
| L1 | Home | MetricCard tooltip uses `render` prop on TooltipTrigger — non-standard API | Code Quality |
| L2 | Talent | Detail panel tabs (Wardrobe, LoRAs) both render `TalentLoraSection` | Redundant |
| L3 | Brain | `eslint-disable` comments for react-hooks rules — indicates architectural smell | Code Quality |
| L4 | Create | `mounted` state is set but never used for rendering guards | Dead Code |
| L5 | Editor | Default shots are example data (Dubai marina) — should be empty for new storyboards | UX |

---

## 4. Backend Endpoint Wiring Audit

### Pages with Direct `fetch()` Instead of Centralized API Client

| Page | Direct fetch calls | Should use api.ts? |
|------|-------------------|-------------------|
| Talent | `POST /talent` (create), media upload, LoRA endpoints | Yes — `createTalent` exists but unused |
| Brain | `/api/v1/brain/llm/chat`, `/api/v1/brain/memory`, `/api/v1/brain/conversations` | Yes — `getBrainHealth`/`getBrainSessions` exist for some |
| Create | `/api/v1/generate/image`, `/api/v1/generate/video`, voice/music endpoints | Should add to api.ts |
| Training | `/api/v1/training/jobs` | Should add to api.ts |
| Assets | `/api/v1/assets` | `getAssets` exists but not used |
| Models | Uses api.ts functions correctly | Good |
| Production | Uses api.ts functions correctly | Good |
| Analytics | Direct fetch for cost/history | Should add to api.ts |
| Admin | Mix of api.ts + direct fetch | Partially good |
| Publish | `getPublishingPosts` from api.ts + direct fetch for scheduling | Mixed |
| Workflows | Direct fetch | Should add to api.ts |

### Missing API Client Functions

Functions that should exist in `api.ts` but don't:
- `generateImage(params)` 
- `generateVideo(params)`
- `generateVoice(params)`
- `generateMusic(params)`
- `getTrainingJobs()`
- `createTrainingJob(formData)`
- `getCostHistory(days)`
- `getWorkflows()`
- `getWorkflowDetail(id)`

---

## 5. KPI Dashboard Cards (Home Page)

| Card | Data Source | Live? | Accuracy |
|------|------------|-------|----------|
| Active Projects | `jobs.filter(status=running)` | Yes | Correct |
| Jobs | `jobs.length` | Yes | Correct |
| GPU Spend (today) | `infrastructure/cost` | Yes | Correct |
| Talent | `getTalent().length` | Yes | Correct |
| Services Online | `admin/services.summary` | Yes | Correct |
| Worker | `infrastructure/status.worker` | Yes | Correct |

**Assessment**: All 6 KPI cards are wired to live data. No mock/hardcoded values.

---

## 6. Destructive Actions Audit

| Action | Page | Confirmation? | Reversible? |
|--------|------|--------------|-------------|
| Delete Talent | Talent | `confirm()` dialog | No (hard delete) |
| Delete Model (archive) | Models | `confirm()` dialog | Yes (restore available) |
| Hard Delete Model | Models | Double `confirm()` | No |
| Stop GPU Worker | Admin | `confirm()` dialog | Yes (can relaunch) |
| Pause GPU Worker | Admin | `confirm()` dialog | Yes (can resume) |
| Clear Completed Jobs | Production | No confirmation | No |
| Delete Scheduled Post | Publish | `confirm()` dialog | No |
| Launch Worker | Production | `confirm()` dialog with cost info | Billable action |

**Issue Found**: "Clear Completed Jobs" on Production page has NO confirmation dialog but deletes multiple records.

---

## 7. Empty States Audit

| Page | Has Empty State? | Quality |
|------|-----------------|---------|
| Home / Active Productions | Yes | Good (icon + text + suggestion) |
| Home / Jobs Overview | Partial (shows 0 in donut) | Acceptable |
| Talent | Partial (loading spinner but no "no talent" state) | Needs empty state |
| Assets | Yes | Good (icon + text) |
| Models | Yes | Good (with upload CTA) |
| Training | Yes | Good (history section) |
| Production / Jobs | Yes | Good (icon + text) |
| Publish / Calendar | Implicit (empty days) | Acceptable |
| Analytics / Talent | Yes | Good (explanation text) |
| Analytics / Publishing | Yes | Good (icon + text) |
| Brain / Chat | Yes | Good (icon + connection status) |
| Workflows | No | Needs empty state |

---

## 8. Accessibility Quick Check

| Concern | Status |
|---------|--------|
| Color contrast (text on dark bg) | Good — gray-400/500 text on dark navy |
| Focus indicators | Partial — most inputs have focus:border-purple |
| Keyboard navigation | Partial — buttons are focusable, custom cards are not |
| Screen reader labels | Poor — no aria-labels on icon-only buttons |
| Alt text on images | Present on most `<img>` tags |
| Form labels | Partial — some inputs lack associated `<label>` elements |
| Motion/animation | Moderate — spinners and pulses, no reduced-motion support |

---

## 9. Performance Observations

| Concern | Finding |
|---------|---------|
| API calls on mount | Most pages fire 1-5 API calls on mount — acceptable |
| Polling | Home (none), Brain (10s health), Admin (15s refresh), Production (10s jobs) |
| Re-renders | Brain page has multiple useEffect chains that could cascade |
| Bundle size | All pages use 'use client' — no server components leveraged |
| Image optimization | Uses `<img>` not Next.js `<Image>` — noted with eslint-disable |
| No SWR/React Query | Every page refetches from scratch on navigation — no cache |

---

## 10. Summary of Findings

### By Severity

| Severity | Count |
|----------|-------|
| Critical (blocks user) | 3 |
| High (confusing UX) | 8 |
| Medium (polish) | 10 |
| Low (cosmetic) | 5 |
| **Total** | **26** |

### Top 5 Recommendations (Immediate)

1. **Fix Brain page dead code** — Move localStorage/session loading before the `return` cleanup in useEffect
2. **Wire talent_id param in Training** — Complete the talent→training flow
3. **Add confirmation to "Clear Completed Jobs"** — Prevent accidental data loss
4. **Fix Home greeting** — Use `new Date().getHours()` for time-aware greeting
5. **Add Workflows to sidebar** — Users can't discover this page

### Architecture Notes

- The split between legacy endpoints (`/talent`, `/projects`) and v1 API (`/api/v1/...`) creates inconsistency in auth handling
- Brain page has the most complex state management — candidate for refactoring into smaller components
- Create page is ~700 lines — could be split into tab-specific components
- No global error boundary exists — unhandled errors show React error screen
