---
inclusion: manual
---

# Skill: Red Team Visual Audit

Run an interactive Playwright audit that screenshots every page, clicks buttons, and generates a redundancy report. Used by @redteam for UX gap analysis, page consolidation planning, and visual regression detection.

## Prerequisites

- Frontend running on `localhost:3000` (`cd frontend && npm run dev`)
- Backend running on `localhost:8000` (`uv run uvicorn backend.main:app --reload`)
- Playwright installed (`cd frontend && npx playwright install chromium`)

## Quick Start

```bash
# Headless (fast, just screenshots + report)
./scripts/run-redteam-audit.sh

# Headed (opens browser window — watch it happen)
./scripts/run-redteam-audit.sh --headed

# Slow motion (500ms delay between actions — follow along)
./scripts/run-redteam-audit.sh --slow

# Debug (1000ms delay — step through carefully)
./scripts/run-redteam-audit.sh --debug
```

## What It Does

The audit has 3 phases:

### Phase 1 — Screenshot all 22 pages

Navigates to every route in the app, waits for React hydration, captures a full-page screenshot. Also collects structural data: h1 text, button inventory, tab inventory, cost displays, service status indicators, job queue presence, and model selectors.

**Pages audited:**
- Main: `/`, `/brain`, `/create`, `/talent`, `/assets`, `/models`, `/training`, `/projects`, `/publish`, `/analytics`, `/editor`, `/workflows`, `/production`, `/settings`, `/login`
- Admin: `/admin`, `/admin/fleet`, `/admin/downloads`, `/admin/health`, `/admin/ise`, `/admin/keys`, `/admin/knowledge`

### Phase 2 — Button interactions

On key interactive pages (`/create`, `/admin`, `/admin/fleet`, `/brain`, `/talent`, `/training`, `/production`, `/settings`), clicks up to 8 safe buttons per page and screenshots the result. Skips destructive buttons (delete, stop, destroy, logout).

### Phase 3 — Redundancy analysis

Automatically detects:
- "Launch Worker" button appearing on multiple pages
- Service status shown on 3+ pages
- Cost/spend data scattered across 3+ pages
- Job queue data on multiple pages
- Duplicate h1 headings (identity confusion)
- Admin sub-pages with overlapping health views

Generates `REDUNDANCY_REPORT.md` with all findings.

## Output

```
frontend/redteam-audit/
├── home.png                    — Full page screenshots (22 total)
├── brain.png
├── create.png
├── ...
├── admin-knowledge.png
├── interactions/
│   ├── brain-click1-New_Chat.png    — After-click screenshots
│   ├── create-click1-Image_Generation.png
│   └── ...
└── REDUNDANCY_REPORT.md        — Auto-generated findings
```

## How to Use with @redteam

### Option A: Automated analysis

After running the audit, invoke @redteam:

```
@redteam Review the redundancy report at frontend/redteam-audit/REDUNDANCY_REPORT.md.
Also review the screenshots for: layout alignment, color contrast, empty states,
loading states, button hierarchy, mobile responsiveness, visual consistency.
```

### Option B: Drag screenshots into chat

1. Run: `open frontend/redteam-audit/`
2. Drag specific page screenshots into the Kiro chat
3. Ask: "@redteam review these pages for UX issues and redundancies"

### Option C: Full C-Suite assessment

```
@redteam Full page redundancy audit. Read REDUNDANCY_REPORT.md and all page.tsx
files. Identify: dead pages, duplicate controls, navigation confusion, and
propose a consolidation map (which pages to merge/remove).
```

## Running Directly via Playwright

```bash
# From the frontend directory
cd frontend

# Headless
npx playwright test e2e/redteam-audit.spec.ts --project=desktop --workers=1

# Headed (visible browser)
npx playwright test e2e/redteam-audit.spec.ts --project=desktop --workers=1 --headed

# With slow motion
SLOW_MO=500 npx playwright test e2e/redteam-audit.spec.ts --project=desktop --workers=1 --headed

# Mobile viewport
npx playwright test e2e/redteam-audit.spec.ts --project=mobile --workers=1
```

## Interpreting the Report

### Page Inventory Table

The report includes a table showing what each page contains:

| Column | Meaning |
|--------|---------|
| Buttons | Total visible buttons on the page |
| Tabs | Tab-like navigation elements |
| Generate? | Has a "Generate" or "Create Image" button |
| Workers? | Has a "Launch Worker" button |
| Costs? | Shows cost/spend/price data |
| Status? | Shows service health status |

### Redundancy Findings

Findings are classified by severity:
- **P1** — Critical redundancy (confuses users, must fix)
- **P2** — Serious (users waste time checking multiple places)
- **P3** — Notable (navigation clutter, can consolidate)

### Known Redundancies (as of 2026-07-22)

| Finding | Pages Involved | Status |
|---------|---------------|--------|
| Settings h1 = "Admin" (identity crisis) | /settings, /admin, /admin/fleet | OPEN |
| Launch Worker on 3 pages | /production, /admin, /admin/fleet | OPEN |
| Cost data on 4 pages | /, /training, /analytics, /admin | OPEN |
| Job queue on 4 pages | /, /training, /production, /admin | OPEN |
| Admin/Health ≈ Admin/Ise | /admin/health, /admin/ise | OPEN |
| Workflows is developer-only | /workflows | OPEN |
| Admin/Downloads is static | /admin/downloads | OPEN |

### Consolidation Target

22 routes → 15 routes:
- Merge `/settings` into `/admin` (tab)
- Merge `/admin/health` + `/admin/ise` → single health tab
- Merge `/admin/downloads` into admin section
- Move `/workflows` to admin (developer tool)
- Rename `/production` → `/jobs`
- Remove Create "Full Production" dead tab

## When to Re-Run

- After any page component restructuring
- After merging/removing pages from the consolidation plan
- Before marking a major feature as "complete"
- As part of the Red Team pre-ship review
- When @redteam or @dev_team requests a fresh audit

## Script Location

- **Playwright spec:** `frontend/e2e/redteam-audit.spec.ts`
- **Source (canonical):** `scripts/redteam-interactive-audit.ts`
- **Shell runner:** `scripts/run-redteam-audit.sh`
