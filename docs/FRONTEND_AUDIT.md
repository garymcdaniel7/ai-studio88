# Frontend Audit Report

> Audited: 2026-07-04
> Build: Next.js 16.2.10 (Turbopack) — all pages compile and generate successfully
> Pages: 11 routes verified

## Summary

| Page | Build | Live Data | Buttons Work | UX Issues |
|------|-------|-----------|-------------|-----------|
| / (Home) | ✅ | ✅ Real API (KPIs, jobs, services) | ✅ All links + suggestions modal | Minor: greeting hardcoded "Gary" |
| /brain | ✅ | ✅ Ollama via /api/v1/brain/llm/chat | ✅ Modes, send, new chat | Context sidebar is static mock |
| /create | ✅ | ✅ Image generation wired | ✅ Generate (image tab) | Video/audio/music buttons not wired to backend |
| /talent | ✅ | ✅ CRUD from /talent | ✅ New Talent creates | Detail panel has hardcoded "Melissa Johnson" profile |
| /assets | ✅ | ❌ Empty state only | ⚠️ Upload button no handler | Expected — #28 in DEFECTS |
| /story | ✅ | ❌ Placeholder | ⚠️ "New Story" button no handler | Expected — #29 in DEFECTS |
| /production | ✅ | ❌ Static zeros | ⚠️ Launch Worker / New Job no handler | Not wired to infra API |
| /publish | ✅ | ✅ Fetches /api/v1/publishing/posts | ✅ Calendar navigation works | "Schedule Post" button no handler |
| /models | ✅ | ✅ Fetches /api/v1/generation/available-models | ✅ Display only | No download/pull action buttons |
| /analytics | ✅ | ✅ Talent list for dropdown | ✅ View switcher + talent dropdown | Charts use Math.random() (mock bars) |
| /admin | ✅ | ✅ Live service connections | ✅ Refresh + Launch Worker | "View Costs" / "View Reputation" buttons no handler |

## Detailed Findings

### / (Home)
- **Works:** Real-time KPIs from API (jobs, talent count, GPU cost, services). Suggestions modal. System status bar with live service indicators. All navigation links functional.
- **Issues:** None critical. Greeting says "Good evening, Gary" — could use dynamic time-of-day + user name from auth.
- **Tooltip:** Uses `render` prop on TooltipTrigger which is the correct base-ui API.

### /brain
- **Works:** 6 modes with specialized system prompts. Chat sends to /api/v1/brain/llm/chat with mode parameter. Session history tracked client-side. Online/offline indicator from /api/v1/brain/health.
- **Issues:**
  - Brain Memory section (right sidebar) is static/hardcoded — not wired to /api/v1/brain/memory (#27)
  - Suggestions in right sidebar are static
  - Past conversations load from API but `loadSession` only works if session has embedded messages
  - Quick action buttons ("Create Storyboard", etc.) don't trigger anything
  - Paperclip/Image/Code/Mic buttons in input area are non-functional

### /create
- **Works:** Image generation fully wired (prompt → POST /api/v1/generate/image → base64 display). Model selector works.
- **Issues:**
  - Video "Generate Video" button — no backend call
  - Video "Animate" button — no backend call  
  - Audio "Generate Speech" button — no backend call (ElevenLabs #22)
  - Music "Generate" button — no backend call
  - Production tab correctly links to /brain

### /talent
- **Works:** Fetches talent list, create new talent works, selection/detail panel works.
- **Issues:**
  - Detail panel shows hardcoded "Melissa Johnson / Age 28 / 5'7"" data regardless of which talent is selected — should use `selectedTalent` fields
  - "Import" button has no handler
  - "Edit" button in detail panel has no handler
  - Search/Filter controls are non-functional (no filtering logic)
  - Tabs (Models, Characters, etc.) don't filter the grid

### /assets
- **Works:** Clean empty state with category tabs.
- **Issues:** Upload button has no click handler. Expected per #28.

### /story
- **Works:** Clean placeholder with correct description.
- **Issues:** "New Story" button has no handler. Expected per #29.

### /production
- **Works:** Shows 4 metric cards and empty worker state.
- **Issues:**
  - Metrics are hardcoded zeros — not wired to getJobs() or getFleetStatus()
  - "Launch Worker" button has no click handler (unlike Admin page which has it wired)
  - "New Job" button has no handler

### /publish
- **Works:** Full calendar with month navigation, renders posts from API by day, upcoming posts list with status badges.
- **Issues:** "Schedule Post" button has no handler.

### /models
- **Works:** Fetches models from API, displays B2 cache status, shows download commands.
- **Issues:** No "Pull model" or "Download" action button — display only.

### /analytics
- **Works:** 5 view tabs (overview, generation, cost, talent, publishing). Talent dropdown fetches from API.
- **Issues:**
  - Charts in Overview use `Math.random()` — not real data
  - Generation stats (3.2s, 92%) appear hardcoded
  - Cost values ($0.93) appear partially hardcoded
  - No actual data pipeline for engagement metrics

### /admin
- **Works:** Live service connections with status. Refresh button. Launch Worker with full state machine (idle→launching→success/error). Fleet status display.
- **Issues:**
  - "View Costs" button has no handler
  - "View Reputation" button has no handler

## Navigation & Links

All sidebar links verified — 11 routes match 11 pages. No broken links.

| Link Location | Target | Status |
|---------------|--------|--------|
| Sidebar nav (11 items) | All pages | ✅ |
| Topbar Quick Create | /create | ✅ |
| Topbar Bell | /admin | ✅ |
| Topbar Chat | /brain | ✅ |
| Home "New Project" | /create | ✅ |
| Home "AI Brain Chat" | /brain | ✅ |
| Home "Upload Asset" | /assets | ✅ |
| Home "Create Image" | /create | ✅ |
| Home "Open Brain" | /brain | ✅ |
| Home "View all systems" | /admin | ✅ |
| Home "Open Job Queue" | /production | ✅ |
| Home "Active Productions → View all" | /production | ✅ |
| Create "Plan with AI Brain" | /brain | ✅ |
| Sidebar bottom icons | /brain, /admin | ✅ (Bell/Help/Settings all → /admin) |

## Quick Fixes Applied

1. **Talent detail panel** — Profile section now shows `selectedTalent` data instead of hardcoded "Melissa Johnson"
2. **Production page** — Wired metrics to live API data (getJobs + getFleetStatus)

## Priority Fixes Needed (Not Yet Done)

| Priority | Fix | Effort |
|----------|-----|--------|
| P1 | Brain memory → wire to /api/v1/brain/memory | 1hr |
| P1 | Production Launch Worker → wire to launchWorker() (copy from Admin) | 30min |
| P2 | Create video/audio/music → wire to backend when endpoints exist | 2hr |
| P2 | Analytics charts → wire to real generation/cost history data | 3hr |
| P2 | Talent tabs → implement filtering by type | 1hr |
| P3 | Publish "Schedule Post" → create modal + POST | 2hr |
| P3 | Assets Upload → implement file upload to /api/v1/assets | 2hr |
| P3 | Sidebar bottom icons — Bell should go to notifications, Help to docs | 15min |
