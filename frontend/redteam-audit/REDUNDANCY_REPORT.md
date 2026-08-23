# Red Team Interactive Audit Report

**Generated:** 2026-08-23T14:40:47.397Z
**Pages audited:** 22
**Interactions captured:** See redteam-audit/interactions/

---

## Page Inventory

| Page | h1 | Buttons | Tabs | Generate? | Workers? | Costs? | Status? |
|------|-----|---------|------|-----------|----------|--------|--------|
| / | Your AITalent Agency | 3 | 0 | - | - | YES | YES |
| /brain | Welcome back | 4 | 0 | - | - | - | YES |
| /create | Welcome back | 4 | 0 | - | - | - | YES |
| /talent | Welcome back | 4 | 0 | - | - | - | YES |
| /assets | Welcome back | 4 | 0 | - | - | - | YES |
| /models | Welcome back | 4 | 0 | - | - | - | YES |
| /training | Welcome back | 4 | 0 | - | - | - | YES |
| /projects | Welcome back | 4 | 0 | - | - | - | YES |
| /publish | Welcome back | 4 | 0 | - | - | - | YES |
| /analytics | Welcome back | 4 | 0 | - | - | - | YES |
| /editor | Welcome back | 4 | 0 | - | - | - | YES |
| /workflows | Welcome back | 4 | 0 | - | - | - | YES |
| /production | Welcome back | 4 | 0 | - | - | - | YES |
| /settings | Welcome back | 4 | 0 | - | - | - | YES |
| /login | Welcome back | 4 | 0 | - | - | - | YES |
| /admin | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/fleet | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/downloads | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/health | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/ise | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/keys | Welcome back | 4 | 0 | - | - | - | YES |
| /admin/knowledge | Welcome back | 4 | 0 | - | - | - | YES |

## Redundancy Findings

### P2 — Service health status shown on 22 pages
**Pages:** /, /brain, /create, /talent, /assets, /models, /training, /projects, /publish, /analytics, /editor, /workflows, /production, /settings, /login, /admin, /admin/fleet, /admin/downloads, /admin/health, /admin/ise, /admin/keys, /admin/knowledge
**Issue:** Status information scattered — no single source of truth.
**Recommendation:** Show detailed status only on /admin/health. Other pages show a compact indicator.

### P1 — Duplicate h1 "Welcome back" on 21 pages
**Pages:** /brain, /create, /talent, /assets, /models, /training, /projects, /publish, /analytics, /editor, /workflows, /production, /settings, /login, /admin, /admin/fleet, /admin/downloads, /admin/health, /admin/ise, /admin/keys, /admin/knowledge
**Issue:** Two pages with the same heading creates identity confusion.
**Recommendation:** Rename one or merge the pages.

### P1 — 7 admin pages show service health
**Pages:** /admin, /admin/fleet, /admin/downloads, /admin/health, /admin/ise, /admin/keys, /admin/knowledge
**Issue:** Admin section has redundant health views.
**Recommendation:** Consolidate into single /admin health tab.

## Button Inventory (per page)

### /
- ✨Signature
- 📱Lifestyle
- 🌍Global

### /brain
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /create
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /talent
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /assets
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /models
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /training
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /projects
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /publish
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /analytics
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /editor
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /workflows
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /production
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /settings
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /login
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/fleet
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/downloads
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/health
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/ise
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/keys
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

### /admin/knowledge
- Continue with Google
- Sign In
- Sign up
- Skip login (dev mode only)

## Tab Inventory (per page)

