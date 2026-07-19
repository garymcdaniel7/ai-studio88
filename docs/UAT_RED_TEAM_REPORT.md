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
1. D1: Home h1 blocked by onboarding (move onboarding below greeting)
2. D3: Generate button no GPU warning (pre-flight check)
3. D4: Brain green dot lies (reflect actual LLM status)
4. D5: Talent Import dead button (remove or implement)
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

### Current Coverage (11 test files, ~85 tests)
- Basic page load assertions
- Element visibility checks
- Simple interaction tests (click, type)

### Needed Coverage (target: 200+ tests)

#### Cross-Page Flow Tests (NEW)
- [ ] Generate → Save → Find in Library
- [ ] Create Talent → Train LoRA → Generate with LoRA
- [ ] Create Project → Add Storyboard → Generate Shots
- [ ] Schedule Post → Verify in Calendar
- [ ] Brain Chat → Generate Image → See in Chat

#### Backend Connection Tests (ENHANCE)
- [ ] Every button that calls an API → verify response
- [ ] GPU offline → graceful error on all generation pages
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
