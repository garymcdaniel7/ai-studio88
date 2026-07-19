# AI Studio — Full UAT Red Team Report

> **Date:** July 2026
> **Tester:** Dev Team Red Team (30-year UX specialist persona)
> **Result:** 78/85 Playwright tests pass (92%). 24 defects found. 13 hidden gaps.

## Test Results Baseline

| File | Pass | Fail | Notes |
|------|------|------|-------|
| home.spec.ts | 0 | 5 | Onboarding blocks h1 |
| brain.spec.ts | 7 | 0 | All pass |
| create.spec.ts | 8 | 0 | All pass |
| talent.spec.ts | 5 | 0 | All pass |
| assets.spec.ts | 6 | 0 | All pass |
| models.spec.ts | 7 | 1 | Flaky beforeEach |
| training.spec.ts | 5 | 0 | All pass |
| settings.spec.ts | 4 | 0 | All pass |
| admin.spec.ts | 11 | 1 | Flaky cold load |
| publish.spec.ts | 4 | 0 | All pass |
| navigation.spec.ts | 23 | 0 | All pass |
| **TOTAL** | **78** | **7** | **92%** |

## Priority Fix Order

### Sprint 1 — Trust Builders
1. D1: Home h1 blocked by onboarding (move onboarding below greeting) ✅
2. D3: Generate button no GPU warning (pre-flight check) ✅ **FIXED** — Backend pre-validates model availability, frontend shows GPU status banner, auto-selects loaded models, Generate button disabled when offline
3. D4: Brain green dot lies (reflect actual LLM status) ✅
4. D5: Talent Import dead button (remove or implement) ✅
5. D11: Projects 404 — ALREADY FIXED ✅

### Sprint 2 — Core Loop
6. D2: Music generation dead (remove tab or add "Coming Soon")
7. D12: ControlNet image not uploaded (hide until implemented)
8. D6: No "Save to Library" button on results
9. G1: No auth gate (add middleware + login redirect)
10. G2: Railway fallback URL (change default to localhost:8000)

### Sprint 3 — Scale
11. G5/G6: No pagination (add limit/offset)
12. D13: Collections not persisted (fetch on mount)
13. G8: No training cancel button
14. D9: Publish doesn't actually publish
15. G3: No rate limiting (debounce + backend limit)

### Sprint 4 — Polish
16. D14: Hardcoded suggestions
17. D15: Asset tags
18. D18: Talent edit missing
19. D22: Sidebar green dot
20. D23: Training cost formula

## Enhanced Playwright Test Plan

### Current Coverage (12 test files, ~104 tests)
- Basic page load assertions
- Element visibility checks
- Simple interaction tests (click, type)
- **NEW: create-generation.spec.ts (19 tests)**
  - Model availability status indicators
  - GPU offline graceful degradation (banner + disabled button)
  - Auto-selection of loaded models
  - Pre-flight validation before generation
  - Mocked successful generation flow
  - Button redundancy audit (no duplicate Generate, no Quick Create in topbar)
  - Tab interaction integrity

### Needed Coverage (target: 200+ tests)

#### Cross-Page Flow Tests (NEW)
- [ ] Generate → Save → Find in Library
- [ ] Create Talent → Train LoRA → Generate with LoRA
- [ ] Create Project → Add Storyboard → Generate Shots
- [ ] Schedule Post → Verify in Calendar
- [ ] Brain Chat → Generate Image → See in Chat

#### Backend Connection Tests (ENHANCE)
- [ ] Every button that calls an API → verify response
- [x] GPU offline → graceful error on all generation pages ✅ (create-generation.spec.ts)
- [ ] Ollama offline → Brain shows warning
- [ ] Supabase offline → data persistence warning

#### Navigation Integrity (ENHANCE)
- [ ] Every nav item → correct page loads
- [ ] Back button behavior on all pages
- [ ] Breadcrumb navigation (projects/[id] → projects)
- [ ] Deep links work (share URL → same state)

#### Hidden Pages (ADD)
- [ ] /projects/[id] — workspace loads
- [ ] /admin/fleet — fleet page loads + metrics
- [ ] /admin/keys — keys page loads
- [ ] /admin/ise — ISE page loads
- [ ] /admin/knowledge — knowledge page loads
- [ ] /admin/downloads — downloads page loads
- [ ] /login — login page loads + form works
- [ ] /editor — editor page loads

#### Screenshot Comparison (ADD)
- [ ] Capture baseline screenshots for each page
- [ ] Compare on subsequent runs for visual regression
- [ ] Flag >5% pixel difference as potential regression

## Praise List (What Works Well)

1. Brain chat with generation detection + inline images
2. Create page multi-tab with talent injection + recipe presets
3. Admin GPU lifecycle (launch/stop/pause with live progress)
4. Training quality presets (Quick/Standard/Quality)
5. Onboarding persona selection
6. Models page full lifecycle (upload/cache/deploy/archive)
7. Publish calendar + queue dual view
8. BrainDock floating mini-chat
9. Feedback/learning system
10. Cost tracking everywhere

---

## Red Team C-Suite Assessment — 2026-07-19 (Post-Sprint 2)

> **Board:** CFO, COO, CPO, CCO, CTO, CLO, CMO, CISO, CEO Advisor
> **Verdict:** ❌ NO SHIP (unanimous except CCO/CMO conditional)
> **Readiness:** Pre-Alpha / Dev Only — 2-3 sprints from beta-ready

### Executive Summary

The platform has strong bones — working generation pipeline, professional UI, thoughtful architecture. But it's a **developer tool masquerading as a product**. The gap between the polished frontend and the unguarded backend is the #1 risk. Fix auth, and the rest becomes manageable.

### P0 — SHOWSTOPPERS (Must fix before ANY external user)

| # | Finding | Owner | Impact |
|---|---------|-------|--------|
| P0-1 | **Zero auth enforcement** — all API endpoints publicly accessible, no JWT validation | CISO+CTO | Anyone can generate on our GPU for free |
| P0-2 | **No tenant isolation** — org_id never enforced in API layer | CISO+CFO | Cross-org data leakage possible |
| P0-3 | **Railway fallback URL** — frontend defaults to live production backend if env var missing | CISO | Uncontrolled GPU spend from any unconfig'd deploy |
| P0-4 | **`/open-folder` + `/set-output-dir`** — server-side command execution with no auth | CISO | Remote code execution vector |

### P1 — CRITICAL (Must fix before beta invite)

| # | Finding | Owner | Impact |
|---|---------|-------|--------|
| P1-5 | **Sync generation blocks event loop** — `time.sleep()` in thread pool, ~40 concurrent limit | CTO+COO | Server DOS at modest concurrency |
| P1-6 | **No rate limiting** — unlimited GPU generation requests | CFO+COO | Infinite cost exposure |
| P1-7 | **Music tab is dead** — full UI, but just returns static message | CPO+CCO | Erodes trust ("what else is fake?") |
| P1-8 | **Publish is pure simulation** — calendar/queue visible but nothing posts | CPO+CCO | Broken core loop promise |
| P1-9 | **Login page is fake** — localStorage only, no Supabase Auth SDK, no middleware redirect | CPO+CISO | Multi-tenant architecture meaningless |

### P2 — SERIOUS (Must fix before paid tier)

| # | Finding | Owner | Impact |
|---|---------|-------|--------|
| P2-10 | No "Save to Library" on generation results | CCO | Core loop incomplete |
| P2-11 | ControlNet UI present but non-functional (no image upload to ComfyUI) | CCO+CPO | Power users feel deceived |
| P2-12 | Duplicate `/available-models` route registration | CTO | Maintenance hazard |
| P2-13 | Home page greeting hardcoded to "Gary" | CCO | Multi-tenant UX broken |
| P2-14 | No error boundaries — backend down = infinite spinner | COO+CCO | Users abandoned during outages |

### P3 — NOTABLE

| # | Finding | Owner |
|---|---------|-------|
| P3-15 | No pagination on Talent/Assets lists (unbounded queries) | CTO |
| P3-16 | Brain suggestions are hardcoded strings, not AI-driven | CPO |
| P3-17 | Cost estimate always shows "~$0.003" regardless of model/resolution | CFO+CCO |
| P3-18 | No job cancellation for long-running video generation | CCO |
| P3-19 | CORS allows all methods/headers (overly permissive) | CISO |

### P4 — ASPIRATIONAL (Competitive Gaps)

| # | Gap | Competitor |
|---|-----|-----------|
| P4-20 | No real-time generation progress | Midjourney |
| P4-21 | No batch generation (4 variations) | Leonardo |
| P4-22 | No image editing / inpainting | Runway |
| P4-23 | No community gallery or sharing | Civitai |
| P4-24 | No mobile experience | All |

### Fix Priority Order (Red Team Recommended)

1. **Wire Supabase Auth end-to-end** (fixes P0-1, P0-2, P1-9)
2. **Change Railway fallback to localhost** (fixes P0-3)
3. **Guard/remove dangerous endpoints** (fixes P0-4)
4. **Make generation async** (fixes P1-5)
5. **Add rate limiting** (fixes P1-6)
6. **Remove/badge dead features** (fixes P1-7, P1-8, P2-11)
7. **Add "Save to Library"** (fixes P2-10)

### Metrics to Track

| KPI | Target |
|-----|--------|
| Auth rejection (unauth requests) | 100% blocked |
| Cross-tenant access blocked | 100% |
| Time to first generation (new user) | <120s |
| Concurrent generation capacity | 50+ |
| Cost per generation (actual) | <$0.01 SDXL, <$0.05 Flux |
| Dead feature exposure | 0% (badged or removed) |
| Generation → Save → Library | <3 clicks |
