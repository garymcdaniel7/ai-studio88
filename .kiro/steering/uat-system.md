---
inclusion: auto
---

# UAT System — Self-Learning Test Intelligence

This steering file is a **living document**. It is updated automatically by the Ise UAT agent after each test run. Hermes and all agents can read this to understand the current health of the UI.

## Current Test Status

**Last run:** 2026-07-11
**Pass rate:** 104/104 core tests (100%)
**Fleet tests:** 8/22 (14 depend on live GPU infrastructure)

## Page Health Map

| Page | Tests | Status | Notes |
|------|-------|--------|-------|
| / (Home) | 5 | healthy | Quick create, sidebar, activity |
| /brain | 7 | healthy | Chat, modes, send, history, health |
| /create | 8 | healthy | Prompt, model selector, generate, resolution |
| /editor | 3 | healthy | Tools, timeline, quick edit |
| /workflows | 3 | healthy | List, cards, detail view |
| /talent | 5 | healthy | List, create, photo upload, Train LoRA |
| /assets | 6 | healthy | Upload, grid, filter, expand, delete |
| /models | 8 | healthy | Upload zone, inventory, filters, archive |
| /production | 5 | healthy | Workers, launch, job queue, connections |
| /publish | 4 | healthy | Platforms, connect, schedule |
| /analytics | 5 | healthy | Stats, charts, time range, GPU cost |
| /admin | 13 | healthy | Services, toggles, health, sub-pages |
| /training | 5 | healthy | Form, start button, params, talent selector |
| /settings | 4 | healthy | Profile, save, text inputs |
| /admin/fleet | 22 | partial | UI passes, API tests need live infra |

## Known Patterns

### Pages that render h1 after data load
These pages were fixed to render header unconditionally:
- `/models` — was gating h1 behind loading state
- `/admin` — was gating h1 behind loading state

### API polling pages
These pages never reach `networkidle` due to continuous polling:
- `/` (Home) — polls recent activity
- `/admin` — polls service health every 15s
- `/admin/fleet` — polls worker status
- Tests use `domcontentloaded` instead of `networkidle`

### Playwright API notes
- Playwright 1.61: `locator.isAttached()` removed. Use `locator.count() > 0` or `expect(locator).toBeAttached()`
- File inputs with `className="hidden"` are attached but not visible. Use `count()` to detect.

## Test File Map

```
frontend/e2e/
  home.spec.ts          — 5 tests (Home page)
  navigation.spec.ts    — 23 tests (all routes + sidebar + refresh)
  brain.spec.ts         — 7 tests (Brain/chat page)
  create.spec.ts        — 8 tests (Image generation page)
  editor.spec.ts        — 3 tests (Video editor)
  workflows.spec.ts     — 3 tests (Workflow management)
  talent.spec.ts        — 5 tests (AI Talent management)
  assets.spec.ts        — 6 tests (Asset library)
  models.spec.ts        — 8 tests (Model manager)
  production.spec.ts    — 5 tests (Production pipeline)
  publish.spec.ts       — 4 tests (Social publishing)
  analytics.spec.ts     — 5 tests (Analytics dashboard)
  admin.spec.ts         — 13 tests (Admin + sub-pages)
  training.spec.ts      — 5 tests (LoRA training)
  settings.spec.ts      — 4 tests (User settings)
  fleet.spec.ts         — 22 tests (Fleet management + API)
  full-flow.spec.ts     — 8 tests (End-to-end user flows)
  responsive.spec.ts    — 35 tests (Mobile + desktop layout)
```

## How to Run

```bash
# All desktop tests (recommended)
cd frontend && npx playwright test --project=desktop --workers=1

# Single page
npx playwright test e2e/brain.spec.ts --project=desktop

# With filter
npx playwright test --project=desktop --grep="Brain"

# Via Ise API
curl -X POST http://localhost:8000/aios/v1/ise/uat/run -d '{"filter":"brain"}'
```

## Self-Learning Rules

When the Ise UAT agent runs tests:
1. Update the **Page Health Map** above with current pass/fail
2. If a NEW failure appears, add it to **Known Patterns** with root cause
3. If a fix is applied and tests pass, mark the pattern as "RESOLVED"
4. Update **Last run** timestamp
5. Feed summary to Hermes via `POST /aios/v1/hermes/chat`

## Enhancement Backlog (discovered by tests)

- [ ] Add e2e test for image generation end-to-end (prompt → result in assets)
- [ ] Add e2e test for brain conversation persistence (send → refresh → still there)
- [ ] Add e2e test for training submission (configure → submit → job appears)
- [ ] Add error state tests (backend down, generation fail, upload rejection)
- [ ] Add performance assertions (page load <3s, API response <2s)
- [ ] Add accessibility tests (keyboard nav, focus management, screen reader labels)
